#!/usr/bin/env python3
"""流 B:小红书存量笔记抓取归档(文案 + 互动数据 + 参考图/视频)。

抓来的图带小红书水印和达人自己的中文大字,**只能内部参考**,不能直接对外发布,
所以本脚本一律把「可用范围」写成「仅参考」。要能对外用的干净素材走 ingest.py --delivery。

文本/图片:直接解析 H5 页面的 __INITIAL_STATE__(无需登录)。
视频文件:调 video-download skill(团队唯一下载入口),不自己写下载器。

用法:
    scrape_xhs.py                     # 跑全表「待归档」的记录
    scrape_xhs.py --limit 3           # 先跑 3 条试水
    scrape_xhs.py --asset-id xhslink_xxx [...]   # 指定记录
    scrape_xhs.py --dry-run           # 只抓不下载、不传 OSS、不写表
可选:--redo(连已归档的也重跑) --with-video(顺带归档视频文件) --delay 秒(默认 6)

视频默认不归档:本机在东京,传阿里云北京 OSS 只有 ~18KB/s,一个 18MB 的视频要十几分钟。
文案/数据/封面才是流 B 的价值所在;真要留视频文件,挑几条 `--asset-id ... --with-video` 单跑。
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
import urllib.request
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ingest  # noqa: E402  复用 lark()/上传器/常量

def _find_video_dl() -> Path | None:
    """video-download skill 的位置各机器不同,按常见落点找一遍。"""
    env = os.environ.get("VIDEO_DOWNLOAD_SKILL")
    cands = [Path(env) / "scripts/download.py"] if env else []
    cands += [Path(p).expanduser() / "video-download/scripts/download.py"
              for p in ("~/md-skills/skills", "~/.claude/skills", "~/.codex/skills", "~/.agents/skills")]
    return next((c for c in cands if c.is_file()), None)


VIDEO_DL = _find_video_dl()
UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
      "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1")
NOTE_RE = re.compile(r"window\.__INITIAL_STATE__\s*=\s*(\{.*?\})\s*</script>", re.S)


class ScrapeError(Exception):
    pass


# ---------- 抓取 ----------

def http_get(url: str, referer: str | None = None) -> tuple[str, bytes]:
    headers = {"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9"}
    if referer:
        headers["Referer"] = referer
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=45) as r:
        raw = r.read()
        if r.headers.get("Content-Encoding") == "gzip":
            raw = gzip.decompress(raw)
        return r.geturl(), raw


def fetch_note(url: str) -> tuple[str, dict]:
    """返回 (跳转后的真实链接, noteData)。"""
    final, raw = http_get(url)
    html = raw.decode("utf-8", "replace")
    m = NOTE_RE.search(html)
    if not m:
        raise ScrapeError("页面没有 __INITIAL_STATE__(可能已删除/需登录)")
    # 页面里的 JS 字面量含 undefined,JSON 解析不了
    state = json.loads(re.sub(r"\bundefined\b", "null", m.group(1)))
    note = (state.get("noteData") or {}).get("data", {}).get("noteData")
    if not note:
        raise ScrapeError("拿不到笔记正文(内容不可见或已下架)")
    return final, note


def pick_image_urls(note: dict) -> list[str]:
    """每张图取最大的可用渲染版本(H5_DTL 优于 H5_PRV)。"""
    urls = []
    for img in note.get("imageList") or []:
        info = {i.get("imageScene"): i.get("url") for i in (img.get("infoList") or [])}
        u = info.get("H5_DTL") or info.get("H5_PRV") or img.get("url")
        if u:
            urls.append(u)
    return urls


def to_int(v) -> int | None:
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return None


def clean_desc(desc: str) -> str:
    return re.sub(r"\[话题\]#", "#", desc or "").strip()


# ---------- 下载 ----------

def download_images(urls: list[str], workdir: Path, referer: str) -> list[Path]:
    out = []
    for n, u in enumerate(urls, 1):
        try:
            _, blob = http_get(u, referer="https://www.xiaohongshu.com/")
        except Exception as e:  # 单张图失败不拖垮整条
            print(f"    图 {n} 下载失败: {e}")
            continue
        ext = ".png" if blob[:4] == b"\x89PNG" else ".webp" if blob[8:12] == b"WEBP" else ".jpg"
        p = workdir / f"img_{n:02d}{ext}"
        p.write_bytes(blob)
        out.append(p)
    return out


def download_video(url: str, workdir: Path) -> Path | None:
    if VIDEO_DL is None:
        print("    找不到 video-download skill,跳过视频(设 VIDEO_DOWNLOAD_SKILL 指到它的目录)")
        return None
    env = dict(os.environ, VIDEO_DOWNLOAD_OUTPUT_DIR=str(workdir))
    # 必须用系统 python3:playwright 装在系统站点包里,本脚本的 venv 没有
    r = subprocess.run(["python3", str(VIDEO_DL), url, "video.mp4"],
                       cwd=str(VIDEO_DL.parent.parent), env=env,
                       capture_output=True, text=True, timeout=600)
    p = workdir / "video.mp4"
    if p.is_file() and p.stat().st_size > 0:
        return p
    tail = (r.stdout or "")[-300:] + (r.stderr or "")[-300:]
    print(f"    视频下载失败(rc={r.returncode}): {tail.strip()[:300]}")
    return None


# ---------- 主流程 ----------

def list_records(args) -> list[dict]:
    base = f"/open-apis/bitable/v1/apps/{ingest.APP_TOKEN}/tables/{ingest.TABLE_ID}/records"
    body = {"page_size": 100,
            "field_names": ["素材ID", "达人昵称", "原笔记链接", "状态", "点赞", "收藏", "评论", "备注"]}
    items, token = [], None
    while True:
        path = f"{base}/search?page_size=100" + (f"&page_token={token}" if token else "")
        data = ingest.lark("POST", path, body)
        items += data.get("items") or []
        token = data.get("page_token")
        if not data.get("has_more"):
            break

    def plain(v):
        if isinstance(v, list):
            return "".join(x.get("text", "") for x in v)
        return v or ""

    out = []
    for it in items:
        f = it["fields"]
        rec = {"record_id": it["record_id"],
               "asset_id": plain(f.get("素材ID")),
               "url": (f.get("原笔记链接") or {}).get("link"),
               "status": f.get("状态"),
               "old": (to_int(f.get("点赞")), to_int(f.get("收藏")), to_int(f.get("评论")))}
        if not rec["url"]:
            continue
        if args.asset_id and rec["asset_id"] not in args.asset_id:
            continue
        if not args.asset_id and not args.redo and rec["status"] != "待归档":
            continue
        out.append(rec)
    return out[: args.limit] if args.limit else out


def process(rec: dict, args, workroot: Path) -> str:
    print(f"\n[{rec['asset_id']}] {rec['url']}")
    final, note = fetch_note(rec["url"])
    note_id = re.search(r"/(?:explore|discovery/item)/([0-9a-f]+)", final)
    is_video = (note.get("type") or "").lower() == "video"
    title = (note.get("title") or "").strip()
    desc = clean_desc(note.get("desc") or "")
    ii = note.get("interactInfo") or {}
    likes, collects, comments = (to_int(ii.get("likedCount")), to_int(ii.get("collectedCount")),
                                to_int(ii.get("commentCount")))
    print(f"    {'视频' if is_video else '图文'} | {title[:30]} | 赞{likes} 藏{collects} 评{comments}")

    img_urls = pick_image_urls(note)
    if args.dry_run:
        print(f"    dry-run:{len(img_urls)} 图" + (" + 视频" if is_video and args.with_video else ""))
        return "dry-run"

    workdir = workroot / rec["asset_id"]
    workdir.mkdir(parents=True, exist_ok=True)
    files: list[Path] = download_images(img_urls, workdir, final)
    if is_video and args.with_video:
        v = download_video(final, workdir)
        if v:
            files.append(v)
    body = "\n\n".join(x for x in (title, desc) if x)
    if body:
        note_md = workdir / "note.md"
        note_md.write_text(f"{body}\n\n---\n来源:{final}\n抓取:{datetime.now(ingest.CST):%Y-%m-%d %H:%M}\n",
                           encoding="utf-8")
        files.append(note_md)
    if not files:
        raise ScrapeError("正文和媒体都没抓到")

    now = datetime.now(ingest.CST)
    key_dir = f"{now:%Y}/{now:%m}/{rec['asset_id']}"
    upload = make_uploader()
    urls, cover_url = [], None
    for p in files:
        upload(str(p), f"{key_dir}/{p.name}")
        u = f"{ingest.PUBLIC_BASE}/{ingest.OSS_PREFIX}/{key_dir}/{p.name}"
        urls.append(u)
        if cover_url is None and p.name.startswith("img_01"):
            cover_url = u
    print(f"    已传 {len(files)} 个文件 → {ingest.OSS_PREFIX}/{key_dir}/")

    fields = {
        "素材类型": "视频" if is_video else "图文",
        "素材URL": "\n".join(urls),
        "状态": "已归档",
        "可用范围": "仅参考",
        "快照时间": int(time.time() * 1000),
        "备注": remark(rec, note_id.group(1) if note_id else None, likes, collects, comments,
                       is_video, any(p.name == "video.mp4" for p in files)),
    }
    if title:
        fields["标题"] = title[:500]
    if body:
        fields["文案快照"] = body[:8000]
    if cover_url:
        fields["封面URL"] = {"link": cover_url, "text": cover_url}
    for k, v in (("点赞", likes), ("收藏", collects), ("评论", comments)):
        if v is not None:
            fields[k] = v
    if note.get("time"):
        fields["发布时间"] = int(note["time"])

    ingest.lark("PUT", f"/open-apis/bitable/v1/apps/{ingest.APP_TOKEN}/tables/{ingest.TABLE_ID}"
                       f"/records/{rec['record_id']}", {"fields": fields})
    return "ok"


def remark(rec, note_id, likes, collects, comments, is_video, got_video) -> str:
    bits = ["抓取归档;图片含小红书水印及达人字幕,仅供内部参考"]
    if is_video and not got_video:
        bits.append("视频文件未归档,看原链接")
    if note_id:
        bits.append(f"noteId={note_id}")
    old = rec.get("old")
    now = (likes, collects, comments)
    if old and any(o is not None for o in old) and old != now:
        bits.append(f"建联表原互动 赞{old[0]}/藏{old[1]}/评{old[2]},已按抓取值更新")
    return ";".join(bits)


_uploader = None


def make_uploader():
    global _uploader
    if _uploader is None:
        _uploader = ingest.make_uploader(ingest.OSS_PREFIX)
    return _uploader


def mark_failed(rec: dict, reason: str) -> None:
    try:
        ingest.lark("PUT", f"/open-apis/bitable/v1/apps/{ingest.APP_TOKEN}/tables/{ingest.TABLE_ID}"
                           f"/records/{rec['record_id']}",
                    {"fields": {"状态": "源已失效",
                                "快照时间": int(time.time() * 1000),
                                "备注": f"抓取失败:{reason[:150]}"}})
    except Exception as e:
        print(f"    (标记失败态也失败了: {e})")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int)
    ap.add_argument("--asset-id", nargs="*", default=[])
    ap.add_argument("--redo", action="store_true")
    ap.add_argument("--with-video", action="store_true", help="顺带下载并归档视频文件(慢:上行 ~18KB/s)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--delay", type=float, default=6.0)
    args = ap.parse_args()

    workroot = Path(tempfile.mkdtemp(prefix="xhs-scrape-"))
    os.chdir(workroot)  # lark-cli 只收当前目录下的相对路径 --data
    recs = list_records(args)
    print(f"待处理 {len(recs)} 条,工作目录 {workroot}")
    ok = failed = 0
    try:
        for n, rec in enumerate(recs, 1):
            print(f"--- {n}/{len(recs)}", end="")
            try:
                process(rec, args, workroot)
                ok += 1
            except ScrapeError as e:
                failed += 1
                print(f"    跳过: {e}")
                if not args.dry_run:
                    mark_failed(rec, str(e))
            except Exception as e:
                failed += 1
                print(f"    异常: {e}\n{traceback.format_exc()[-500:]}")
                if not args.dry_run:
                    mark_failed(rec, f"{type(e).__name__}: {e}")
            finally:
                shutil.rmtree(workroot / rec["asset_id"], ignore_errors=True)
            if n < len(recs):
                time.sleep(args.delay)
    finally:
        os.chdir("/")
        shutil.rmtree(workroot, ignore_errors=True)
    print(f"\n完成:成功 {ok},失败 {failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
