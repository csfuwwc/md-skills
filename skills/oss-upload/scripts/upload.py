#!/usr/bin/env python3
"""把本地文件传进阿里云 OSS,返回可访问链接。只做这一件事。

只用标准库:STS 临时凭证靠内网网关,签名是手写的 OSS V4(见 `_put_object`),
所以 clone 下来就能跑,不用 pip install 任何东西。

对象名由内容决定,不由调用方决定:
    {images|videos|files}/{年}/{月}/{内容sha256前12位}{后缀}
同一个文件传多少次都落到同一个 key —— 天然幂等、自动去重、永不误覆盖。
传之前会先探一下,已经存在就直接返回链接不重传(上行慢的机器上省的是几十分钟)。

用法:
  python3 upload.py a.jpg b.mp4        每行一个 URL,顺序与传入一致
  python3 upload.py a.jpg --json       给机器读:url / key / bytes / existed
  python3 upload.py --check            自检:网关通不通、能不能真写进去
退出码:0 全成功,1 有失败。
"""
import argparse
import hashlib
import hmac
import json
import os
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

# ---- 部署坐标。STS 网关是公司内网服务,外网打不通,所以写在公开仓里也调不动。----
STS_URL = os.getenv("OSS_STS_URL", "http://api-ai.modianinc.com:8080/oss/get_sts")
BUCKET = os.getenv("OSS_BUCKET", "mdfile")
REGION = os.getenv("OSS_REGION", "cn-beijing")
OSS_HOST = f"{BUCKET}.oss-{REGION}.aliyuncs.com"
# 读取域名必须用 bucket 绑的自定义域名:走默认 endpoint 阿里云会强加
# `Content-Disposition: attachment` + `x-oss-force-download`,链接点开只能下载不能预览,
# 而且这个头在上传侧覆盖不掉。
PUBLIC_BASE = os.getenv("OSS_PUBLIC_BASE", "https://vd.moimg.net")

CST = timezone(timedelta(hours=8))
UPLOAD_TIMEOUT = int(os.getenv("OSS_UPLOAD_TIMEOUT", "1800"))  # 上行慢的机器上大视频很久
HASH_LEN = 12

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".heic", ".bmp", ".avif"}
VIDEO_EXT = {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi"}
CONTENT_TYPES = {
    ".jpg": "image/jpeg", ".png": "image/png", ".webp": "image/webp", ".gif": "image/gif",
    ".heic": "image/heic", ".bmp": "image/bmp", ".avif": "image/avif",
    ".mp4": "video/mp4", ".mov": "video/quicktime", ".m4v": "video/x-m4v",
    ".webm": "video/webm", ".mkv": "video/x-matroska", ".avi": "video/x-msvideo",
    ".md": "text/markdown", ".txt": "text/plain", ".json": "application/json",
    ".csv": "text/csv", ".html": "text/html", ".pdf": "application/pdf",
    ".srt": "text/plain", ".vtt": "text/vtt",
}


class OssError(Exception):
    pass


# ---------- 对象名 ----------

def normalized_ext(path):
    """后缀统一小写;.jpeg 归到 .jpg,免得同一张图因为后缀写法不同存两份。"""
    ext = os.path.splitext(path)[1].lower()
    return ".jpg" if ext == ".jpeg" else ext


def type_dir(ext):
    if ext in IMAGE_EXT:
        return "images"
    if ext in VIDEO_EXT:
        return "videos"
    return "files"


def content_hash(path, length=HASH_LEN):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()[:length]


def object_key(path, now=None):
    """key 完全由「文件类型 + 入库年月 + 内容哈希」决定,调用方无从干预。"""
    ext = normalized_ext(path)
    moment = now or datetime.now(CST)
    return f"{type_dir(ext)}/{moment:%Y}/{moment:%m}/{content_hash(path)}{ext}"


def public_url(key):
    return f"{PUBLIC_BASE.rstrip('/')}/{key}"


def content_type(ext):
    return CONTENT_TYPES.get(ext, "application/octet-stream")


# ---------- STS 凭证 ----------

_cache = {}


def credentials(refresh_skew_seconds=300):
    """按 expiration 复用,不每传一个文件就打一次网关。"""
    cached = _cache.get("creds")
    if cached:
        left = (_expires_at(cached["expiration"]) - datetime.now(timezone.utc)).total_seconds()
        if left > refresh_skew_seconds:
            return cached
    try:
        with urllib.request.urlopen(STS_URL, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as error:
        raise OssError(f"取不到 STS 凭证:{error}。这个网关是公司内网服务,"
                       "不在内网就用不了(不要试图绕过)。") from error
    if payload.get("code") != 0:
        raise OssError(f"STS 网关拒绝了请求: {str(payload)[:200]}")
    data = payload.get("data") or {}
    missing = [f for f in ("access_key_id", "access_key_secret", "security_token", "expiration")
               if not data.get(f)]
    if missing:
        raise OssError(f"STS 返回缺字段: {', '.join(missing)}")
    _cache["creds"] = data
    return data


def _expires_at(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


# ---------- 上传 ----------

def exists(key):
    """bucket 是公共读,探一下不用签名。探不动就当不存在,顶多白传一次。"""
    request = urllib.request.Request(f"https://{OSS_HOST}/{key}", method="HEAD")
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return response.status == 200
    except Exception:
        return False


def upload(path, now=None, skip_existing=True):
    """传一个文件,返回 {path, key, url, bytes, existed}。"""
    if not os.path.isfile(path):
        raise OssError(f"文件不存在: {path}")
    size = os.path.getsize(path)
    if size == 0:
        raise OssError(f"空文件不传: {path}")
    key = object_key(path, now)
    if skip_existing and exists(key):
        return {"path": path, "key": key, "url": public_url(key), "bytes": size, "existed": True}
    with open(path, "rb") as f:
        body = f.read()
    _put_object(key, body, content_type(normalized_ext(path)))
    return {"path": path, "key": key, "url": public_url(key), "bytes": size, "existed": False}


def _put_object(key, body, ctype):
    """OSS V4 签名的 PUT。手写签名是为了不依赖 alibabacloud-oss-v2,保持本 skill 自包含。"""
    creds = credentials()
    now = datetime.now(timezone.utc)
    stamp, date = now.strftime("%Y%m%dT%H%M%SZ"), now.strftime("%Y%m%d")
    headers = {"host": OSS_HOST, "content-type": ctype,
               "x-oss-content-sha256": "UNSIGNED-PAYLOAD", "x-oss-date": stamp,
               "x-oss-security-token": creds["security_token"]}
    signed = sorted(k for k in headers if k == "content-type" or k.startswith("x-oss-"))
    canonical = "\n".join([
        "PUT", "/" + BUCKET + "/" + urllib.parse.quote(key, safe="/"), "",
        "".join(f"{k}:{headers[k].strip()}\n" for k in signed), "", "UNSIGNED-PAYLOAD"])
    scope = f"{date}/{REGION}/oss/aliyun_v4_request"
    to_sign = "\n".join(["OSS4-HMAC-SHA256", stamp, scope,
                         hashlib.sha256(canonical.encode()).hexdigest()])
    signing_key = _hmac(("aliyun_v4" + creds["access_key_secret"]).encode(), date)
    for part in (REGION, "oss", "aliyun_v4_request"):
        signing_key = _hmac(signing_key, part)
    signature = hmac.new(signing_key, to_sign.encode(), hashlib.sha256).hexdigest()
    headers["authorization"] = (f"OSS4-HMAC-SHA256 Credential={creds['access_key_id']}/{scope},"
                                f"Signature={signature}")
    request = urllib.request.Request(f"https://{OSS_HOST}/{key}", data=body, method="PUT",
                                     headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=UPLOAD_TIMEOUT):
            return
    except urllib.error.HTTPError as error:
        raise OssError(f"OSS 拒绝写入({key}): "
                       f"{error.read().decode('utf-8', 'replace')[:300]}") from error
    except Exception as error:
        raise OssError(f"OSS 上传失败({key}): {error}") from error


def _hmac(key, message):
    return hmac.new(key, message.encode(), hashlib.sha256).digest()


# ---------- 命令行 ----------

def check():
    """自检:网关 → 上传 → 回读,三段都真跑一遍。"""
    print("oss-upload 自检")
    try:
        creds = credentials()
        print(f"  ✅ STS 网关      凭证有效期至 {creds['expiration']}")
    except OssError as error:
        print(f"  ❌ STS 网关      {error}")
        return 1
    tmpdir = tempfile.mkdtemp(prefix="oss-check-")
    try:
        probe = os.path.join(tmpdir, "selfcheck.txt")
        with open(probe, "w", encoding="utf-8") as f:
            f.write("oss-upload self check\n")
        result = upload(probe, skip_existing=False)
        print(f"  ✅ 上传          {result['key']}")
        # 回读用 http:自定义域名的 HTTPS 证书由运维维护,这里不该因证书失败误报。
        with urllib.request.urlopen(result["url"].replace("https://", "http://"),
                                    timeout=20) as response:
            forced = "attachment" in (response.headers.get("Content-Disposition") or "")
            if response.status != 200:
                print(f"  ❌ 回读          HTTP {response.status}")
                return 1
            if forced:
                print("  ❌ 回读          返回强制下载头 —— 读取域名配成默认 endpoint 了")
                return 1
        print(f"  ✅ 回读          {result['url']}")
    except Exception as error:
        print(f"  ❌ {error}")
        return 1
    finally:
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)
    print("全绿。")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="传文件进 OSS,返回链接")
    parser.add_argument("files", nargs="*", help="本地文件路径,可多个")
    parser.add_argument("--json", action="store_true", help="输出 JSON 给机器读")
    parser.add_argument("--force", action="store_true", help="即使已存在也重传")
    parser.add_argument("--check", action="store_true", help="自检后退出")
    args = parser.parse_args(argv)

    if args.check:
        return check()
    if not args.files:
        parser.error("要传的文件呢?(自检用 --check)")

    results, failures = [], []
    for path in args.files:
        try:
            results.append(upload(path, skip_existing=not args.force))
        except OssError as error:
            failures.append({"path": path, "error": str(error)})
            if not args.json:
                print(f"失败 {path}: {error}", file=sys.stderr)

    if args.json:
        print(json.dumps({"ok": not failures, "files": results, "failed": failures},
                         ensure_ascii=False))
    else:
        for item in results:
            print(item["url"])
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
