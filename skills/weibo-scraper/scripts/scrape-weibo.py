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
import urllib.request
from pathlib import Path

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
ssl._create_default_https_context = ssl._create_unverified_context


def parse_args():
    parser = argparse.ArgumentParser(description="Scrape public Weibo post metadata as JSONL.")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--json-input", action="store_true")
    parser.add_argument("--between-ms", type=int, default=6000)
    parser.add_argument("--page-wait-ms", type=int, default=12000)
    parser.add_argument("--chrome-executable-path", default="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    parser.add_argument("--cdp-url", default="")
    parser.add_argument("--new-tab", action="store_true")
    parser.add_argument("--worker-tab-name", default="codex-weibo-worker")
    parser.add_argument("--comment", action="store_true")
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--work-dir", default="/tmp/weibo-scraper")
    parser.add_argument("--stop-after-consecutive-failures", type=int, default=5)
    return parser.parse_args()


def extract_url(text):
    text = str(text or "").replace("&amp;", "&")
    markdown = re.search(r"\((https?://[^)\s]+)", text)
    if markdown:
        return markdown.group(1)
    raw = re.search(r"https?://\S+", text)
    return raw.group(0).rstrip(")],，。") if raw else ""


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


def normalize_count(value):
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return int(value)
    text = str(value).strip().replace(",", "")
    if not text or text in {"赞", "评论", "转发"}:
        return 0 if text == "赞" else None
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


def clean_lines(text):
    return [line.strip().replace("\u200b", "") for line in (text or "").splitlines() if line.strip().replace("\u200b", "")]


def parse_visible_text(page_title, text):
    lines = clean_lines(text)
    publish_index = -1
    for index, line in enumerate(lines):
        if re.search(r"\d{2,4}-\d{1,2}-\d{1,2}\s+\d{1,2}:\d{2}|今天\s*\d{1,2}:\d{2}|昨天\s*\d{1,2}:\d{2}", line):
            publish_index = index
            break

    body_lines = []
    if publish_index >= 0:
        index = publish_index + 1
        while index < len(lines) and (lines[index].startswith("发布于") or lines[index].startswith("来自") or lines[index] == "关注"):
            index += 1
        stop_set = {"播放视频", "转发", "评论", "赞", "分享这条博文", "同时转发"}
        while index < len(lines):
            line = lines[index]
            if line in stop_set or re.fullmatch(r"\d{1,2}:\d{2}", line) or re.search(r"\d+次观看", line):
                break
            if line.startswith("还没有人评论") or line == "随时随地发现新鲜事":
                break
            body_lines.append(line)
            index += 1

    body = "\n".join(body_lines).strip()
    if not body:
        body = re.sub(r"\s*-\s*微博\s*$", "", page_title or "").strip()

    liked = None
    for index, line in enumerate(lines):
        if line == "赞":
            if index > 0:
                liked = normalize_count(lines[index - 1])
                if liked is not None and lines[index - 1] not in {"转发", "评论"}:
                    break
            liked = 0
            break
        match = re.fullmatch(r"赞\s*(\d+(?:\.\d+)?[万亿]?)", line)
        if match:
            liked = normalize_count(match.group(1))
            break

    return {
        "body": body,
        "likedCount": liked if liked is not None else 0,
        "collectedCount": 0,
    }


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
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", video_path,
        "-vf", "fps=1/3,scale=360:-1,tile=3x3",
        "-frames:v", "1", sheet_path,
    ], check=True)


def describe_sheet(sheet_path):
    prompt = "请基于这张微博视频抽帧拼图，提取可见字幕、画面主体、人物/产品/场景、以及适合写入表格正文的内容摘要。不要声称听到了音频。"
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


def analyze_video(item, video_url, work_dir):
    if not item.get("analyzeVideo") or not video_url:
        return ""
    seq = item.get("seq") or re.sub(r"\W+", "_", item.get("url", ""))[-24:] or "unknown"
    folder = Path(work_dir) / f"seq_{seq}"
    folder.mkdir(parents=True, exist_ok=True)
    video_path = str(folder / "video.mp4")
    sheet_path = str(folder / "sheet.jpg")
    try:
        download_file(video_url, video_path, "https://weibo.com/")
        make_contact_sheet(video_path, sheet_path)
        return describe_sheet(sheet_path)
    except Exception:
        return ""


def first_video_url(page_data, captured_urls):
    for item in page_data.get("videos", []):
        for key in ("currentSrc", "src"):
            value = item.get(key)
            if isinstance(value, str) and value.startswith("http"):
                return value
    for value in page_data.get("sources", []):
        if isinstance(value, str) and value.startswith("http"):
            return value
    for value in captured_urls:
        if value.startswith("http"):
            return value
    return ""


def build_result(item, page_url, page_title, page_data, captured_video_urls, work_dir):
    risk_text = f"{page_title}\n{page_data.get('text', '')}"
    if re.search(r"验证码|异常访问|访问过于频繁|安全验证|captcha|verify|risk", risk_text, re.I):
        return {"ok": False, "url": item["url"], "error": "platform risk detected"}
    if re.search(r"登录后查看|内容不存在|微博不存在|404|not found", risk_text, re.I):
        return {"ok": False, "url": item["url"], "error": "post not found or login required"}

    visible = parse_visible_text(page_title, page_data.get("text", ""))
    video_url = first_video_url(page_data, captured_video_urls)
    analysis = analyze_video(item, video_url, work_dir)
    body = visible.get("body") or ""
    if analysis:
        body = "\n\n".join([body, "【视频内容解析】\n" + analysis]) if body else "【视频内容解析】\n" + analysis

    return {
        "ok": bool(body),
        "url": item["url"],
        "resolvedUrl": page_url,
        "body": body,
        "likedCount": visible.get("likedCount"),
        "collectedCount": visible.get("collectedCount"),
        "videoUrlFound": bool(video_url),
        "videoAnalyzed": bool(analysis),
        "error": "" if body else "empty body",
    }


def scrape_one(page, item, args):
    captured_video_urls = []

    def on_response(response):
        url = response.url
        if (".mp4" in url or ".m3u8" in url) and url not in captured_video_urls:
            captured_video_urls.append(url)

    page.on("response", on_response)
    try:
        page.goto(item["url"], wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(args.page_wait_ms)
        page_data = page.evaluate(
            """() => ({
                title: document.title,
                url: location.href,
                text: document.body ? document.body.innerText.slice(0, 5000) : '',
                videos: Array.from(document.querySelectorAll('video')).map(v => ({src: v.src || '', currentSrc: v.currentSrc || '', poster: v.poster || ''})),
                sources: Array.from(document.querySelectorAll('source')).map(s => s.src || '')
            })"""
        )
        return build_result(item, page.url, page_data.get("title", ""), page_data, captured_video_urls, args.work_dir)
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


def post_comment(page, comment_text):
    text = str(comment_text or "").strip()
    if not text:
        return {"attempted": False}
    normalized_text = re.sub(r"https?://\S+", "网页链接", text).strip()
    excerpt = normalized_text[:12] or text[:12]
    body_text = page.locator("body").inner_text(timeout=5000)
    if re.search(r"验证码|异常访问|访问过于频繁|安全验证|captcha|verify|risk|登录后", body_text, re.I):
        return {"attempted": True, "ok": False, "error": "login or platform risk detected before comment"}
    textarea = page.locator('textarea[placeholder="发布你的评论"]').first
    button = page.locator('button:has-text("评论")').first
    try:
        textarea.wait_for(state="visible", timeout=10000)
        textarea.fill(text, timeout=5000)
        page.wait_for_timeout(500)
        if button.count() == 0:
            return {"attempted": True, "ok": False, "error": "comment submit button not found"}
        button.click(timeout=5000)
        page.wait_for_timeout(3000)
        current = page.locator("body").inner_text(timeout=5000)
        textarea_value = textarea.input_value(timeout=2000)
        if text in current or normalized_text in current or (excerpt and excerpt in current) or textarea_value == "":
            return {"attempted": True, "ok": True}
        return {"attempted": True, "ok": False, "error": "comment not visible after submit"}
    except Exception as exc:
        return {"attempted": True, "ok": False, "error": str(exc)}


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
        else:
            browser = playwright.chromium.launch(headless=not args.headed, executable_path=args.chrome_executable_path)
            context = browser.new_context(user_agent=UA, viewport={"width": 1280, "height": 800})

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
            if result.get("ok") and args.comment and item.get("commentText"):
                comment_result = post_comment(page, item.get("commentText"))
                result["commentAttempted"] = bool(comment_result.get("attempted"))
                if comment_result.get("attempted"):
                    result["commentOk"] = bool(comment_result.get("ok"))
                    if comment_result.get("error"):
                        result["commentError"] = comment_result.get("error")
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
            browser.close()


if __name__ == "__main__":
    main()
