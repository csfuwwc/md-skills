#!/usr/bin/env python3
"""素材库 OSS 上传 CLI:复用 Stagehand storage.oss_upload(STS 缓存刷新 + put_object)。

用法:
    oss_up.py <local_path> <object_key> [--prefix creator-assets]
返回:可访问 URL(https://vd.moimg.net/<key>)打到 stdout。
"""
import argparse
import sys

sys.path.insert(0, "/home/ubuntu/Stagehand/python")
from stagehand.storage.oss_upload import make_default_uploader  # noqa: E402

DEFAULT_PREFIX = "creator-assets"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("local_path")
    ap.add_argument("object_key", help="前缀下的相对 key,如 raw/xhs/<达人>/<笔记ID>/img_01.jpg")
    ap.add_argument("--prefix", default=DEFAULT_PREFIX)
    args = ap.parse_args()

    upload = make_default_uploader(dir_prefix=args.prefix)
    print(upload(args.local_path, args.object_key))
    return 0


if __name__ == "__main__":
    sys.exit(main())
