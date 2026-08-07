"""取一个 OSS 上传器,不依赖任何一台机器的目录结构。

VPS 上有 Stagehand 仓库就直接用它里面那份(已有测试);别的机器(本机执行时)没有,
就用下面这份等价实现。两者行为一致:STS 换临时凭证 → 缓存到快过期 → put_object。

环境变量:
    STAGEHAND_PY   Stagehand 的 python 包目录,默认 /home/ubuntu/Stagehand/python
    OSS_STS_URL    换临时凭证的网关(公司内网)
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

STS_URL = os.environ.get("OSS_STS_URL", "http://api-ai.modianinc.com:8080/oss/get_sts")
BUCKET = "mdfile"
REGION = "cn-beijing"
DOMAIN = "https://mdfile.oss-cn-beijing.aliyuncs.com"
REFRESH_SKEW = 300


def make_uploader(dir_prefix: str) -> Callable[[str, str], str]:
    stagehand_py = os.environ.get("STAGEHAND_PY", "/home/ubuntu/Stagehand/python")
    if (Path(stagehand_py) / "stagehand" / "storage" / "oss_upload.py").is_file():
        if stagehand_py not in sys.path:
            sys.path.insert(0, stagehand_py)
        from stagehand.storage.oss_upload import make_default_uploader
        return make_default_uploader(sts_url=STS_URL, bucket=BUCKET, region=REGION,
                                     domain=DOMAIN, dir_prefix=dir_prefix)
    return _standalone_uploader(dir_prefix)


def _standalone_uploader(dir_prefix: str) -> Callable[[str, str], str]:
    import alibabacloud_oss_v2 as oss  # 缺就报错,让人去装,别静默降级

    cache: dict = {}

    def credentials() -> dict:
        exp = cache.get("expiration")
        if exp and (exp - datetime.now(timezone.utc)).total_seconds() > REFRESH_SKEW:
            return cache["cred"]
        with urllib.request.urlopen(urllib.request.Request(STS_URL), timeout=10) as r:
            payload = json.loads(r.read().decode("utf-8"))
        if payload.get("code") != 0 or not isinstance(payload.get("data"), dict):
            raise RuntimeError(f"STS 网关返回异常(内网才能调): {str(payload)[:200]}")
        d = payload["data"]
        for f in ("access_key_id", "access_key_secret", "security_token", "expiration"):
            if not d.get(f):
                raise RuntimeError(f"STS 返回缺字段 {f}")
        cache["cred"] = d
        cache["expiration"] = datetime.fromisoformat(d["expiration"].replace("Z", "+00:00"))
        return d

    def upload(local_path: str, object_key: str) -> str:
        c = credentials()
        cfg = oss.config.load_default()
        cfg.credentials_provider = oss.credentials.StaticCredentialsProvider(
            access_key_id=c["access_key_id"], access_key_secret=c["access_key_secret"],
            security_token=c["security_token"])
        cfg.region = REGION
        key = "/".join(p for p in f"{dir_prefix}/{object_key}".split("/") if p and p != "..")
        oss.Client(cfg).put_object(
            oss.PutObjectRequest(bucket=BUCKET, key=key, body=Path(local_path).read_bytes()))
        return f"{DOMAIN}/{key}"

    return upload
