#!/usr/bin/env python3
"""素材入库:本地文件 → OSS 归档 → 回写「达人·素材」表。

路径规则(脚本拼,人不碰):
    assets/{入库年}/{入库月}/{素材ID}/{规范文件名}

素材ID 三种来历:
    xhs_<noteid> / xhslink_<code>   从笔记链接提取
    c_<日期>_<随机>                 达人直接交付、无链接
    g_<日期>_<随机>                 我们自己生成/加工

用法:
    ingest.py --url <笔记链接> <文件...>                  # 有链接:匹配已有记录并归档
    ingest.py --delivery --creator "达人昵称" <文件...>    # 达人交付原片
    ingest.py --generated --title "标题" <文件...>         # 自产素材
可选:--cover <文件>  --note <文本或文件>  --dry-run
"""
from __future__ import annotations

import argparse
import json
import random
import re
import string
import subprocess
import sys
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from oss_client import make_uploader  # noqa: E402

APP_TOKEN = "BkRCb9uKjaN8VzsgGDZciqRxnDc"
TABLE_ID = "tblxpajEH9CoNcQa"
LARK_PROFILE = "personal-li-shoushou"
OSS_PREFIX = "assets"
PUBLIC_BASE = "https://mdfile.oss-cn-beijing.aliyuncs.com"
CST = timezone(timedelta(hours=8))

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".heic"}
VIDEO_EXT = {".mp4", ".mov", ".m4v", ".webm"}
TEXT_EXT = {".md", ".txt"}


class IngestError(Exception):
    pass


# ---------- 素材ID ----------

def asset_id_from_url(url: str) -> str:
    m = re.search(r"/(?:explore|discovery/item)/([0-9a-f]{16,32})", url)
    if m:
        return "xhs_" + m.group(1)
    m = re.search(r"xhslink\.com/o/(\w+)", url)
    if m:
        return "xhslink_" + m.group(1)
    raise IngestError(f"无法从链接提取素材ID,请改用 --delivery/--generated: {url}")


def minted_id(kind: str) -> str:
    stamp = datetime.now(CST).strftime("%Y%m%d")
    rand = "".join(random.choices(string.ascii_lowercase + string.digits, k=6))
    return f"{kind}_{stamp}_{rand}"


# ---------- 文件命名 ----------

def canonical_names(paths: list[Path], cover: Path | None) -> list[tuple[Path, str]]:
    """原始文件名不可信(中文/空格/重名),统一改名;顺序=用户给定顺序。"""
    pairs: list[tuple[Path, str]] = []
    img_n = vid_n = 0
    for p in paths:
        ext = p.suffix.lower()
        if cover is not None and p.resolve() == cover.resolve():
            pairs.append((p, f"cover{ext}"))
        elif ext in IMAGE_EXT:
            img_n += 1
            pairs.append((p, f"img_{img_n:02d}{ext}"))
        elif ext in VIDEO_EXT:
            vid_n += 1
            pairs.append((p, f"video{ext}" if vid_n == 1 else f"video_{vid_n:02d}{ext}"))
        elif ext in TEXT_EXT:
            pairs.append((p, p.name))
        else:
            raise IngestError(f"不认识的文件类型 {ext}({p});支持图/视频/md/txt")
    return pairs


def guess_asset_type(names: list[str]) -> str:
    has_v = any(Path(n).suffix.lower() in VIDEO_EXT for n in names)
    has_i = any(Path(n).suffix.lower() in IMAGE_EXT for n in names)
    if has_v and has_i:
        return "混合"
    return "视频" if has_v else "图文"


# ---------- 飞书 ----------

def lark(method: str, path: str, data: dict | None = None) -> dict:
    cmd = ["lark-cli", "api", method, path, "--profile", LARK_PROFILE, "--as", "user"]
    if data is not None:
        with tempfile.NamedTemporaryFile("w", suffix=".json", dir=".", delete=False,
                                         encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False)
            tmp = Path(fh.name)
        cmd += ["--data", f"@./{tmp.name}"]
    else:
        tmp = None
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=60, cwd=".")
    finally:
        if tmp is not None:
            tmp.unlink(missing_ok=True)
    body = out.stdout[out.stdout.index("{"):] if "{" in out.stdout else out.stdout
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise IngestError(f"lark-cli 返回无法解析: {out.stdout[:300]} {out.stderr[:300]}")
    if payload.get("code") != 0:
        raise IngestError(f"飞书 API 失败: {json.dumps(payload, ensure_ascii=False)[:400]}")
    return payload["data"]


def find_record(asset_id: str) -> str | None:
    data = lark("POST", f"/open-apis/bitable/v1/apps/{APP_TOKEN}/tables/{TABLE_ID}/records/search",
                {"filter": {"conjunction": "and", "conditions": [
                    {"field_name": "素材ID", "operator": "is", "value": [asset_id]}]},
                 "page_size": 2})
    items = data.get("items") or []
    return items[0]["record_id"] if items else None


# ---------- 主流程 ----------

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+", type=Path)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--url", help="小红书笔记链接(素材ID从中提取)")
    g.add_argument("--delivery", action="store_true", help="达人直接交付,发 c_ 号")
    g.add_argument("--generated", action="store_true", help="自产/加工素材,发 g_ 号")
    ap.add_argument("--creator", help="达人昵称")
    ap.add_argument("--title")
    ap.add_argument("--platform", default="小红书")
    ap.add_argument("--cover", type=Path, help="指定其中一个文件作封面")
    ap.add_argument("--note", help="文案:直接给文本,或给一个 .md/.txt 路径")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    paths = [p for p in args.files]
    for p in paths:
        if not p.is_file():
            raise IngestError(f"文件不存在: {p}")

    if args.url:
        asset_id = asset_id_from_url(args.url)
    else:
        asset_id = minted_id("c" if args.delivery else "g")

    # 文案:文本或文件都归一成 note.md 一起传
    note_text = None
    if args.note:
        np = Path(args.note)
        note_text = np.read_text(encoding="utf-8") if np.is_file() else args.note

    pairs = canonical_names(paths, args.cover)
    now = datetime.now(CST)
    key_dir = f"{now:%Y}/{now:%m}/{asset_id}"

    print(f"素材ID : {asset_id}")
    print(f"OSS    : {OSS_PREFIX}/{key_dir}/")
    for src, name in pairs:
        print(f"  {src.name}  →  {name}")
    if note_text:
        print("  (文案)  →  note.md")
    if args.dry_run:
        print("\n--dry-run,未上传未写表")
        return 0

    upload = make_uploader(OSS_PREFIX)
    urls, cover_url, original_names = [], None, []
    tmpdir = None
    try:
        for src, name in pairs:
            upload(str(src), f"{key_dir}/{name}")
            url = f"{PUBLIC_BASE}/{OSS_PREFIX}/{key_dir}/{name}"
            urls.append(url)
            original_names.append(f"{name}={src.name}")
            if name.startswith("cover"):
                cover_url = url
        if note_text:
            tmpdir = tempfile.mkdtemp()
            note_path = Path(tmpdir) / "note.md"
            note_path.write_text(note_text, encoding="utf-8")
            upload(str(note_path), f"{key_dir}/note.md")
            urls.append(f"{PUBLIC_BASE}/{OSS_PREFIX}/{key_dir}/note.md")
    finally:
        if tmpdir:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)

    fields: dict = {
        "素材ID": asset_id,
        "平台": args.platform,
        "素材URL": "\n".join(urls),
        "状态": "已归档",
        "素材类型": guess_asset_type([n for _, n in pairs]),
        "备注": "原文件名 " + "; ".join(original_names),
    }
    if cover_url:
        fields["封面URL"] = {"link": cover_url, "text": cover_url}
    if args.creator:
        fields["达人昵称"] = args.creator
    if args.title:
        fields["标题"] = args.title
    if note_text:
        fields["文案快照"] = note_text[:8000]
    if args.url:
        fields["原笔记链接"] = {"link": args.url, "text": args.url}

    existing = find_record(asset_id)
    base = f"/open-apis/bitable/v1/apps/{APP_TOKEN}/tables/{TABLE_ID}/records"
    if existing:
        # 已有行(如回灌的种子):只覆盖本次提供的字段,其余(达人/互动数据/授权)原样保留
        lark("PUT", f"{base}/{existing}", {"fields": fields})
        print(f"\n已更新记录 {existing}")
    else:
        rid = lark("POST", base, {"fields": fields})["record"]["record_id"]
        print(f"\n已新建记录 {rid}")
    print(f"素材URL:\n" + "\n".join("  " + u for u in urls))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except IngestError as e:
        print(f"错误: {e}", file=sys.stderr)
        sys.exit(1)
