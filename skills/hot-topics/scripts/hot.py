#!/usr/bin/env python3
"""拉平台热榜:微博热搜、B站热门。

只用标准库,走各平台的公开接口,**不需要登录、不碰账号**。
每个源一个 fetcher,加新平台就往 SOURCES 里加一个 —— 别在调用方分支判断。

用法:
  python3 hot.py                     全部源,人读格式
  python3 hot.py weibo --limit 20    单个源
  python3 hot.py --json              给机器读
退出码:0 至少一个源成功;1 全挂。
"""
import argparse
import json
import sys
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
TIMEOUT = 15

WEIBO_HOT_URL = "https://weibo.com/ajax/side/hotSearch"
BILIBILI_POPULAR_URL = "https://api.bilibili.com/x/web-interface/popular?ps={limit}"


class HotError(Exception):
    pass


def _get_json(url, opener=None, referer=None):
    """referer 按源给:B 站接口收到微博的 Referer 会直接 403。"""
    headers = {"User-Agent": UA, "Accept": "application/json"}
    if referer:
        headers["Referer"] = referer
    request = urllib.request.Request(url, headers=headers)
    open_fn = opener.open if opener else urllib.request.urlopen
    with open_fn(request, timeout=TIMEOUT) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_weibo(limit=20, get_json=None):
    """微博热搜榜。裸调 403 —— 先访问 weibo.com 拿访客 cookie,带着同一 jar 再调接口。"""
    if get_json is None:
        jar = CookieJar()
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
        try:
            opener.open(urllib.request.Request("https://weibo.com/", headers={"User-Agent": UA}),
                        timeout=TIMEOUT).read(16)
        except Exception as error:
            raise HotError(f"微博访客 cookie 预热失败: {error}") from error
        get_json = lambda url: _get_json(url, opener, referer="https://weibo.com/")  # noqa: E731

    try:
        items = get_json(WEIBO_HOT_URL)["data"]["realtime"]
    except Exception as error:
        raise HotError(f"微博热搜抓取失败: {error}") from error
    topics = [{"source": "weibo", "title": str(item.get("word", "")).strip(),
               "heat": item.get("num"), "url": _weibo_search_url(item.get("word", "")),
               "extra": {"label": item.get("label_name") or "", "rank": index}}
              for index, item in enumerate(items[:limit], 1)
              if str(item.get("word", "")).strip()]
    if not topics:
        raise HotError("微博热搜返回为空")
    return topics


def _weibo_search_url(word):
    return "https://s.weibo.com/weibo?q=" + urllib.parse.quote(f"#{word}#")


def fetch_bilibili(limit=20, get_json=None):
    """B站热门视频榜(公开 API,无需登录)。"""
    get_json = get_json or _get_json
    try:
        payload = get_json(BILIBILI_POPULAR_URL.format(limit=limit))
        if payload.get("code") != 0:
            raise HotError(f"B站热门接口 code={payload.get('code')}")
        items = payload["data"]["list"]
    except HotError:
        raise
    except Exception as error:
        raise HotError(f"B站热门抓取失败: {error}") from error
    topics = [{"source": "bilibili", "title": str(item.get("title", "")).strip(),
               "heat": (item.get("stat") or {}).get("view"),
               "url": item.get("short_link_v2") or f"https://www.bilibili.com/video/{item.get('bvid', '')}",
               "extra": {"desc": str(item.get("desc") or "")[:200],
                         "author": (item.get("owner") or {}).get("name", ""),
                         "rank": index}}
              for index, item in enumerate(items[:limit], 1)
              if str(item.get("title", "")).strip()]
    if not topics:
        raise HotError("B站热门返回为空")
    return topics


SOURCES = {"weibo": fetch_weibo, "bilibili": fetch_bilibili}


def fetch(source, limit=20):
    fetcher = SOURCES.get(source)
    if fetcher is None:
        raise HotError(f"未知热点源 {source}(可用: {', '.join(sorted(SOURCES))})")
    return fetcher(limit=limit)


def main(argv=None):
    parser = argparse.ArgumentParser(description="拉平台热榜")
    parser.add_argument("sources", nargs="*", default=[],
                        help=f"要拉的源,留空 = 全部({', '.join(sorted(SOURCES))})")
    parser.add_argument("--limit", type=int, default=20, help="每个源取前 N 条")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    wanted = args.sources or sorted(SOURCES)
    results, failures = [], []
    for source in wanted:
        try:
            results.extend(fetch(source, args.limit))
        except HotError as error:
            failures.append({"source": source, "error": str(error)})
            if not args.json:
                print(f"[{source}] 失败: {error}", file=sys.stderr)

    if args.json:
        print(json.dumps({"ok": not failures, "topics": results, "failed": failures},
                         ensure_ascii=False))
    else:
        current = None
        for topic in results:
            if topic["source"] != current:
                current = topic["source"]
                print(f"\n── {current} ──")
            heat = f"{topic['heat']:,}" if isinstance(topic["heat"], int) else "-"
            print(f"{topic['extra']['rank']:>3}. {topic['title']}  ({heat})")
            print(f"     {topic['url']}")
    return 1 if len(failures) == len(wanted) else 0


if __name__ == "__main__":
    sys.exit(main())
