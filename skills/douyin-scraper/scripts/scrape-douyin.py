#!/usr/bin/env python3
import argparse
import asyncio
import json
import os
import re
import ssl
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
DOUYIN_COOKIE_PATH = os.path.expanduser("~/.config/video-download/douyin_cookies.json")
ssl._create_default_https_context = ssl._create_unverified_context


def parse_args():
    parser = argparse.ArgumentParser(description="Scrape public Douyin note/video metadata as JSONL.")
    parser.add_argument("--json", action="store_true", help="Output JSON lines.")
    parser.add_argument("--json-input", action="store_true", help="Read JSONL rows with url/mode/analyzeVideo.")
    parser.add_argument("--between-ms", type=int, default=6000)
    parser.add_argument("--page-wait-ms", type=int, default=12000)
    parser.add_argument("--chrome-user-data-dir", default="")
    parser.add_argument("--chrome-executable-path", default="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    parser.add_argument("--cdp-url", default="", help="Connect to an already-open Chrome via CDP and leave it open.")
    parser.add_argument("--new-tab", action="store_true", help="When using CDP, open a dedicated tab instead of reusing the first existing page.")
    parser.add_argument("--worker-tab-name", default="codex-douyin-worker", help="Stable window.name for the reusable CDP worker tab.")
    parser.add_argument("--comment", action="store_true", help="Post commentText from JSON input using the live logged-in browser.")
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--work-dir", default="/tmp/douyin-scraper")
    parser.add_argument("--stop-after-consecutive-failures", type=int, default=5)
    return parser.parse_args()


def read_items(args):
    items = []
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        if args.json_input:
            item = json.loads(line)
            item["url"] = extract_url(item.get("url", ""))
            items.append(item)
        else:
            items.append({"url": extract_url(line), "mode": "initial", "analyzeVideo": False})
    return [item for item in items if item.get("url")]


def load_saved_cookies():
    if not os.path.exists(DOUYIN_COOKIE_PATH):
        return []
    try:
        with open(DOUYIN_COOKIE_PATH, "r", encoding="utf-8") as file:
            cookies = json.load(file)
    except Exception:
        return []
    if not isinstance(cookies, list):
        return []
    return cookies


def extract_url(text):
    text = str(text or "").replace("&amp;", "&")
    markdown = re.search(r"\((https?://[^)\s]+)", text)
    if markdown:
        return markdown.group(1)
    raw = re.search(r"https?://\S+", text)
    return raw.group(0).rstrip(")],，。") if raw else ""


def normalize_count(value):
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return int(value)
    text = str(value).strip().replace(",", "")
    if not text:
        return None
    multiplier = 1
    if text.endswith("万"):
        multiplier = 10000
        text = text[:-1]
    elif text.endswith("亿"):
        multiplier = 100000000
        text = text[:-1]
    try:
        return int(float(text) * multiplier)
    except ValueError:
        return None


def walk(value):
    yield value
    if isinstance(value, dict):
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def is_aweme_candidate(node):
    return isinstance(node, dict) and any(key in node for key in ("desc", "description", "statistics", "stats", "video"))


def iter_aweme_candidates(*values):
    for value in values:
        for node in walk(value):
            if not isinstance(node, dict):
                continue
            detail = node.get("aweme_detail")
            if is_aweme_candidate(detail):
                yield detail
            if ("awemeId" in node or "aweme_id" in node) and is_aweme_candidate(node):
                yield node
            child = node.get("aweme")
            if is_aweme_candidate(child):
                yield child


def node_aweme_id(node):
    if not isinstance(node, dict):
        return ""
    for key in ("aweme_id", "awemeId", "awemeIdStr", "id"):
        value = node.get(key)
        if value is not None and str(value).isdigit():
            return str(value)
    return ""


def current_video_id_from_url(url):
    match = re.search(r"/video/(\d+)", url or "")
    return match.group(1) if match else ""


def parse_publish_time_from_text(text):
    raw = str(text or "")
    match = re.search(r"发布时间[:：]\s*([0-9]{4}-[0-9]{2}-[0-9]{2}\s+[0-9]{2}:[0-9]{2})", raw)
    if match:
        return match.group(1)
    match = re.search(r"发布时间[:：]\s*([0-9]{4}-[0-9]{2}-[0-9]{2})", raw)
    if match:
        return match.group(1)
    return ""


def format_publish_time(epoch_value):
    if epoch_value is None:
        return ""
    try:
        ts = int(epoch_value)
        if ts <= 0:
            return ""
        return time.strftime("%Y-%m-%d %H:%M", time.localtime(ts))
    except Exception:
        return ""


def find_aweme(*values):
    candidates = []
    for candidate in iter_aweme_candidates(*values):
        candidates.append(candidate)
    candidates.sort(key=lambda item: len(json.dumps(item, ensure_ascii=False, default=str)), reverse=True)
    return candidates[0] if candidates else None


def find_aweme_by_id(aweme_id, *values):
    if not aweme_id:
        return None
    target = str(aweme_id)
    candidates = []
    for candidate in iter_aweme_candidates(*values):
        if node_aweme_id(candidate) == target:
            candidates.append(candidate)
    candidates.sort(key=lambda item: len(json.dumps(item, ensure_ascii=False, default=str)), reverse=True)
    return candidates[0] if candidates else None


def decode_render_data(raw):
    if not raw:
        return None
    for candidate in (raw, urllib.parse.unquote(raw)):
        try:
            return json.loads(candidate)
        except Exception:
            pass
    return None


def first_string(*values):
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def clean_title(title):
    return re.sub(r"\s*-\s*抖音\s*$", "", title or "").strip()


def strip_visible_metrics_tail(section):
    lines = [line.strip() for line in str(section or "").splitlines()]
    tail_stop = len(lines)
    for index, line in enumerate(lines):
        if line == "分享" or line.startswith("分享") or line.startswith("举报") or "发布时间" in line:
            tail_stop = index
            break
    body_lines = lines[:tail_stop]
    metric_start = len(body_lines)
    while metric_start > 0:
        line = body_lines[metric_start - 1]
        if re.fullmatch(r"\d+(?:\.\d+)?[万亿]?", line) or line in {"抢首评", "赞", "收藏", "评论"}:
            metric_start -= 1
            continue
        break
    return "\n".join(line for line in body_lines[:metric_start] if line).strip()


def parse_visible_current(page_title, visible_text):
    title = clean_title(page_title)
    text = visible_text or ""
    body = ""
    marker = "展开\n"
    if marker in text:
        after = text.split(marker, 1)[1]
        body = after.split("\n发布时间：", 1)[0]
        # Engagement lines are appended after the caption. Keep the caption but
        # strip the mutable metrics tail so refreshes do not pollute 正文.
        body = re.sub(r"\n抢首评.*$", "", body, flags=re.S).strip()
        body = re.sub(r"\n分享.*$", "", body, flags=re.S).strip()
        body = re.sub(r"\n举报.*$", "", body, flags=re.S).strip()
        body = re.sub(r"\n赞\s*$", "", body).strip()
        body = re.sub(r"\n\d+(?:\.\d+)?[万亿]?\s*$", "", body).strip()
        body = strip_visible_metrics_tail(body) or body
    if not body:
        body = title

    liked = None
    comments = None
    collected = None
    # 在展开后的区域找数字。当前抖音视频页的顺序通常是:
    # 点赞数 / 评论数 / 收藏数 / 分享；评论为 0 时可能显示“抢首评”。
    if marker in text:
        metrics_section = text.split(marker, 1)[1].split("\n发布时间：", 1)[0]
        lines = [line.strip() for line in metrics_section.splitlines() if line.strip()]
        numbers = []
        saw_first_comment = False
        saw_share = False
        for line in lines:
            if line == "抢首评":
                saw_first_comment = True
                continue
            if line == "分享" or line.startswith("分享"):
                saw_share = True
                break
            if "发布时间" in line or line.startswith("举报"):
                break
            if re.fullmatch(r"\d+(?:\.\d+)?[万亿]?", line):
                numbers.append(normalize_count(line))
        if numbers:
            liked = numbers[0]
            if len(numbers) >= 2:
                comments = numbers[1]
            if len(numbers) >= 3:
                collected = numbers[2]
            elif len(numbers) >= 2 and saw_first_comment:
                collected = numbers[1]
        if liked is None and any(line == "赞" for line in lines):
            liked = 0
        if collected is None and any(line == "收藏" for line in lines):
            collected = 0
        if collected is None and saw_share and len(numbers) == 2 and not saw_first_comment:
            collected = None

    return {
        "title": title,
        "body": body,
        "likedCount": liked,
        "commentCount": comments,
        "collectedCount": collected,
    }


def parse_visible_dom_metrics(metrics):
    if not isinstance(metrics, list):
        return {}
    cleaned = [str(value or "").strip() for value in metrics if str(value or "").strip()]
    numbers = [normalize_count(text) for text in cleaned if re.fullmatch(r"\d+(?:\.\d+)?[万亿]?", text)]
    result = {}
    if numbers:
        result["likedCount"] = numbers[0]
    if len(numbers) >= 2:
        result["commentCount"] = numbers[1]
    if len(numbers) >= 3:
        result["collectedCount"] = numbers[2]
    elif len(numbers) >= 2 and "抢首评" in cleaned:
        result["collectedCount"] = numbers[1]
    if "赞" in cleaned and "likedCount" not in result:
        result["likedCount"] = 0
    if "收藏" in cleaned and "collectedCount" not in result:
        result["collectedCount"] = 0
    return result


def merge_metric(primary, fallback):
    return primary if primary is not None else fallback


def post_comment(page, comment_text):
    text = str(comment_text or "").strip()
    if not text:
        return {"attempted": False}
    risk_text = page.locator("body").inner_text(timeout=5000)
    if re.search(r"验证码|异常访问|访问过于频繁|安全验证|captcha|verify|risk|登录后即可", risk_text, re.I):
        return {"attempted": True, "ok": False, "error": "login or platform risk detected before comment"}

    container = page.locator("#comment-input-container").first
    editor = page.locator("#comment-input-container .public-DraftEditor-content[contenteditable=true]").first
    try:
        container.wait_for(state="visible", timeout=10000)
        container.click(timeout=5000)
        editor.wait_for(state="visible", timeout=10000)
        editor.click(timeout=5000)
        page.keyboard.insert_text(text)
        page.wait_for_timeout(500)

        submit = page.locator("#comment-input-container .WFB7wUOX.NUzvFSPe").first
        if submit.count() == 0:
            submit = page.locator("#comment-input-container .WFB7wUOX").first
        if submit.count() == 0:
            return {"attempted": True, "ok": False, "error": "comment submit button not found"}
        submit.click(timeout=5000)
        page.wait_for_timeout(3000)
        body_text = page.locator("body").inner_text(timeout=5000)
        if text in body_text:
            return {"attempted": True, "ok": True}
        return {"attempted": True, "ok": False, "error": "comment not visible after submit"}
    except Exception as exc:
        return {"attempted": True, "ok": False, "error": str(exc)}


def collect_video_urls(value):
    urls = []
    seen = set()
    for node in walk(value):
        if isinstance(node, str) and node.startswith("http") and ("douyinvod.com" in node or "byteimg.com" in node):
            if node not in seen:
                seen.add(node)
                urls.append(node)
        elif isinstance(node, dict):
            for key in ("url_list", "bit_rate", "play_addr", "download_addr"):
                child = node.get(key)
                if child:
                    for grandchild in walk(child):
                        if isinstance(grandchild, str) and grandchild.startswith("http") and grandchild not in seen:
                            seen.add(grandchild)
                            urls.append(grandchild)
    return urls


def choose_video_url(aweme):
    video = aweme.get("video") if isinstance(aweme, dict) else None
    if not isinstance(video, dict):
        return ""
    for url in collect_video_urls(video):
        if "douyinvod.com" in url or "aweme/v1/play" in url or "video" in url:
            return url
    return ""


def download_file(url, output_path, referer):
    req = urllib.request.Request(url)
    req.add_header("User-Agent", UA)
    req.add_header("Referer", referer)
    with urllib.request.urlopen(req, timeout=60) as resp:
        with open(output_path, "wb") as file:
            while True:
                chunk = resp.read(1024 * 1024)
                if not chunk:
                    break
                file.write(chunk)
    return os.path.getsize(output_path)


def make_contact_sheet(video_path, sheet_path):
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        video_path,
        "-vf",
        "fps=1/3,scale=360:-1,tile=3x3",
        "-frames:v",
        "1",
        sheet_path,
    ]
    subprocess.run(cmd, check=True)


def describe_sheet(sheet_path):
    prompt = "请基于这张抖音视频抽帧拼图，提取可见字幕、画面主体、人物/产品/场景、以及适合写入表格正文的内容摘要。不要声称听到了音频。"
    result = subprocess.run(
        ["mmx", "vision", "describe", "--region", "global", "--image", sheet_path, "--prompt", prompt],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        return ""
    text = result.stdout.strip()
    try:
        data = json.loads(text)
        if isinstance(data, dict) and isinstance(data.get("content"), str):
            return data["content"].strip()
    except Exception:
        pass
    return text


def analyze_video(url, item, video_url, work_dir):
    if not item.get("analyzeVideo") or not video_url:
        return ""
    seq = item.get("seq") or re.sub(r"\W+", "_", item.get("url", ""))[-24:] or "unknown"
    folder = Path(work_dir) / f"seq_{seq}"
    folder.mkdir(parents=True, exist_ok=True)
    video_path = str(folder / "video.mp4")
    sheet_path = str(folder / "sheet.jpg")
    try:
        download_file(video_url, video_path, "https://www.douyin.com/")
        make_contact_sheet(video_path, sheet_path)
        return describe_sheet(sheet_path)
    except Exception as exc:
        return ""


def build_result(item, page_url, page_title, page_data, response_data, captured_video_url, work_dir):
    risk_text = f"{page_title}\n{page_data.get('text', '')}"
    if "发布时间：" not in risk_text and re.search(r"验证码|异常访问|访问过于频繁|安全验证|captcha|verify|risk", risk_text, re.I):
        return {"ok": False, "url": item["url"], "error": "platform risk detected"}

    current_aweme_id = current_video_id_from_url(page_url)
    expected_aweme_id = current_video_id_from_url(item.get("url", ""))
    if expected_aweme_id and current_aweme_id and expected_aweme_id != current_aweme_id:
        return {
            "ok": False,
            "url": item["url"],
            "resolvedUrl": page_url,
            "error": f"resolved video mismatch expected={expected_aweme_id} actual={current_aweme_id}",
        }
    current_aweme = find_aweme_by_id(current_aweme_id, page_data, *response_data)
    aweme = current_aweme or find_aweme(page_data, *response_data)
    visible = parse_visible_current(page_title, page_data.get("text", ""))
    dom_metrics = parse_visible_dom_metrics(page_data.get("metrics"))
    publish_time = parse_publish_time_from_text(page_data.get("text", ""))
    visible_body = visible.get("body") or ""
    preferred_aweme = current_aweme or aweme
    preferred_stats = preferred_aweme.get("statistics") if isinstance(preferred_aweme, dict) else None
    if not isinstance(preferred_stats, dict) and isinstance(preferred_aweme, dict):
        preferred_stats = preferred_aweme.get("stats")
    preferred_stats = preferred_stats or {}
    liked_struct = normalize_count(
        preferred_stats.get("digg_count") or preferred_stats.get("diggCount")
        or (preferred_aweme.get("digg_count") if isinstance(preferred_aweme, dict) else None)
    )
    comment_struct = normalize_count(
        preferred_stats.get("comment_count") or preferred_stats.get("commentCount")
        or (preferred_aweme.get("comment_count") if isinstance(preferred_aweme, dict) else None)
    )
    collect_struct = normalize_count(
        preferred_stats.get("collect_count") or preferred_stats.get("collectCount")
        or (preferred_aweme.get("collect_count") if isinstance(preferred_aweme, dict) else None)
    )
    if visible_body and "/video/" in page_url:
        video_url = choose_video_url(current_aweme or {})
        analysis = analyze_video(page_url, item, video_url, work_dir)
        body = visible_body
        if analysis:
            body = "\n\n".join([part for part in [visible_body, "【视频内容解析】\n" + analysis] if part])
        return {
            "ok": True,
            "url": item["url"],
            "resolvedUrl": page_url,
            "awemeId": current_aweme_id,
            "title": visible.get("title") or clean_title(page_title),
            "body": body,
            "publishTime": publish_time,
            "likedCount": merge_metric(liked_struct, merge_metric(visible.get("likedCount"), dom_metrics.get("likedCount"))),
            "commentCount": merge_metric(comment_struct, merge_metric(visible.get("commentCount"), dom_metrics.get("commentCount"))),
            "collectedCount": merge_metric(collect_struct, merge_metric(visible.get("collectedCount"), dom_metrics.get("collectedCount"))),
            "videoUrlFound": bool(video_url),
            "videoAnalyzed": bool(analysis),
            "videoBoundToCurrentAweme": bool(current_aweme and video_url),
            "capturedVideoSeen": bool(captured_video_url),
        }

    if not aweme:
        text = json.dumps(page_data, ensure_ascii=False)[:1000]
        if re.search(r"不存在|已删除|下架|404|not found", page_title + text, re.I):
            return {"ok": False, "url": item["url"], "error": "video not found or deleted"}
        return {"ok": False, "url": item["url"], "error": f"no aweme state: {page_title or 'empty page'}"}

    statistics = aweme.get("statistics") or aweme.get("stats") or {}
    if not publish_time:
        publish_time = format_publish_time(
            aweme.get("create_time")
            or aweme.get("createTime")
            or statistics.get("create_time")
            or statistics.get("createTime")
        )
    desc = first_string(aweme.get("desc"), aweme.get("description"), page_title.replace(" - 抖音", ""))
    liked = merge_metric(
        normalize_count(statistics.get("digg_count") or statistics.get("diggCount") or aweme.get("digg_count")),
        merge_metric(visible.get("likedCount"), dom_metrics.get("likedCount")),
    )
    collected = merge_metric(
        normalize_count(statistics.get("collect_count") or statistics.get("collectCount") or aweme.get("collect_count")),
        merge_metric(visible.get("collectedCount"), dom_metrics.get("collectedCount")),
    )
    comments = merge_metric(
        normalize_count(statistics.get("comment_count") or statistics.get("commentCount") or aweme.get("comment_count")),
        merge_metric(visible.get("commentCount"), dom_metrics.get("commentCount")),
    )
    video_url = choose_video_url(current_aweme or aweme)
    analysis = analyze_video(page_url, item, video_url, work_dir)
    body = desc
    if analysis:
        body = "\n\n".join([part for part in [desc, "【视频内容解析】\n" + analysis] if part])

    return {
        "ok": True,
        "url": item["url"],
        "resolvedUrl": page_url,
        "awemeId": aweme.get("aweme_id") or aweme.get("awemeId"),
        "title": clean_title(page_title),
        "body": body,
        "publishTime": publish_time,
        "likedCount": liked,
        "commentCount": comments,
        "collectedCount": collected,
        "videoUrlFound": bool(video_url),
        "videoAnalyzed": bool(analysis),
        "videoBoundToCurrentAweme": bool(current_aweme and video_url),
        "capturedVideoSeen": bool(captured_video_url),
    }


def scrape_one(page, item, args):
    response_data = []
    captured_video_url = ""

    def on_response(response):
        nonlocal captured_video_url
        url = response.url
        content_type = response.headers.get("content-type", "")
        if not captured_video_url and "douyinvod.com" in url and ("video_mp4" in url or ".mp4" in url):
            captured_video_url = url
        if "json" not in content_type and "aweme" not in url:
            return
        try:
            text = response.text()
            if len(text) > 5_000_000:
                return
            response_data.append(json.loads(text))
        except (Exception, asyncio.CancelledError):
            return

    page.on("response", on_response)
    try:
        expected_aweme_id = current_video_id_from_url(item.get("url", ""))
        page.goto(item["url"], wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(args.page_wait_ms)
        if expected_aweme_id and current_video_id_from_url(page.url) != expected_aweme_id:
            # Retry once with canonical URL to avoid stale/reused feed page capture.
            page.goto(f"https://www.douyin.com/video/{expected_aweme_id}", wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(args.page_wait_ms)
        try:
            page.wait_for_function(
                "() => document.title.includes(' - 抖音') && document.body && document.body.innerText.includes('发布时间：')",
                timeout=15000,
            )
        except Exception:
            pass
        page_data = page.evaluate(
            """() => {
                const render = document.querySelector('#RENDER_DATA')?.textContent || '';
                const initial = window.__INITIAL_STATE__ || window._ROUTER_DATA || null;
                const metas = {};
                for (const meta of Array.from(document.querySelectorAll('meta'))) {
                    const key = meta.getAttribute('name') || meta.getAttribute('property');
                    if (key) metas[key] = meta.getAttribute('content');
                }
                return {
                    title: document.title,
                    url: location.href,
                    render,
                    initial,
                    metas,
                    metrics: Array.from(document.querySelectorAll('[aria-label], [title], button, [role="button"], span, div'))
                        .map((el) => {
                            const label = el.getAttribute('aria-label') || el.getAttribute('title') || '';
                            const text = (el.innerText || el.textContent || '').trim();
                            return (label || text).trim();
                        })
                        .filter(Boolean)
                        .filter((value, index, array) => array.indexOf(value) === index)
                        .slice(0, 500),
                    text: document.body ? document.body.innerText.slice(0, 3000) : ''
                };
            }"""
        )
        render_data = decode_render_data(page_data.get("render"))
        if render_data:
            page_data["renderDecoded"] = render_data
        result = build_result(item, page.url, page_data.get("title", ""), page_data, response_data, captured_video_url, args.work_dir)
        if result.get("ok") and args.comment and item.get("commentText"):
            comment_result = post_comment(page, item.get("commentText"))
            result["commentAttempted"] = bool(comment_result.get("attempted"))
            if comment_result.get("attempted"):
                result["commentOk"] = bool(comment_result.get("ok"))
                if comment_result.get("error"):
                    result["commentError"] = comment_result.get("error")
        return result
    except Exception as exc:
        return {"ok": False, "url": item["url"], "error": str(exc)}
    finally:
        try:
            page.remove_listener("response", on_response)
        except Exception:
            pass


def get_window_name(page):
    try:
        return page.evaluate("() => window.name || ''")
    except Exception:
        return ""


def set_window_name(page, name):
    try:
        page.evaluate("(value) => { window.name = value; }", name)
    except Exception:
        pass


def get_worker_page(context, worker_tab_name):
    for page in context.pages:
        if get_window_name(page) == worker_tab_name:
            return page
    page = context.new_page()
    set_window_name(page, worker_tab_name)
    return page


def main():
    args = parse_args()
    items = read_items(args)
    if not items:
        return

    from playwright.sync_api import sync_playwright

    consecutive_failures = 0
    with sync_playwright() as playwright:
        leave_open = False
        if args.cdp_url:
            browser = playwright.chromium.connect_over_cdp(args.cdp_url)
            context = browser.contexts[0] if browser.contexts else browser.new_context(user_agent=UA, viewport={"width": 1280, "height": 800})
            leave_open = True
        elif args.chrome_user_data_dir:
            context = playwright.chromium.launch_persistent_context(
                args.chrome_user_data_dir,
                headless=not args.headed,
                executable_path=args.chrome_executable_path,
                user_agent=UA,
                viewport={"width": 1280, "height": 800},
            )
            browser = None
        else:
            browser = playwright.chromium.launch(headless=not args.headed, executable_path=args.chrome_executable_path)
            context = browser.new_context(user_agent=UA, viewport={"width": 1280, "height": 800})
            cookies = load_saved_cookies()
            if cookies:
                context.add_cookies(cookies)

        if leave_open and args.new_tab:
            page = get_worker_page(context, args.worker_tab_name)
        else:
            page = context.pages[0] if leave_open and context.pages else context.new_page()
            if leave_open:
                set_window_name(page, args.worker_tab_name)
        for index, item in enumerate(items):
            if index:
                time.sleep(max(args.between_ms, 0) / 1000)
            result = scrape_one(page, item, args)
            if result.get("ok"):
                consecutive_failures = 0
            else:
                consecutive_failures += 1
            print(json.dumps(result, ensure_ascii=False), flush=True)
            if re.search(r"platform risk|captcha|verify|异常访问|安全验证", str(result.get("error", "")), re.I):
                break
            if consecutive_failures >= args.stop_after_consecutive_failures:
                break

        if not leave_open:
            context.close()
            if browser:
                browser.close()


if __name__ == "__main__":
    main()
