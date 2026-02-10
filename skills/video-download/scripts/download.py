#!/usr/bin/env python3
"""
抖音 / 小红书 / B站 视频无头下载脚本
用法: python3 download.py <分享链接或文本> [输出文件名]

支持平台:
  - 抖音: v.douyin.com 短链 / www.douyin.com/video/xxx
  - 小红书: www.xiaohongshu.com/discovery/item/xxx / explore/xxx / xhslink.com 短链
  - B站: www.bilibili.com/video/BVxxx / b23.tv 短链
"""
import sys
import re
import os
import ssl
import json
import subprocess
import urllib.request

ssl._create_default_https_context = ssl._create_unverified_context

UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'

# ── 平台识别 ──────────────────────────────────────────────

def detect_platform(text):
    """返回 ('platform', url) 或 (None, None)"""
    # 抖音短链
    m = re.search(r'https?://v\.douyin\.com/[A-Za-z0-9_\-/]+', text)
    if m:
        return 'douyin', m.group(0)
    # 抖音完整链接
    m = re.search(r'https?://www\.douyin\.com/video/\d+', text)
    if m:
        return 'douyin', m.group(0)
    # 小红书完整链接
    m = re.search(r'https?://www\.xiaohongshu\.com/(?:discovery/item|explore)/[a-f0-9]+[^\s"\']*', text)
    if m:
        return 'xiaohongshu', m.group(0)
    # 小红书短链
    m = re.search(r'https?://xhslink\.com/[A-Za-z0-9/]+', text)
    if m:
        return 'xiaohongshu', m.group(0)
    # B站完整链接
    m = re.search(r'https?://www\.bilibili\.com/video/[A-Za-z0-9]+[^\s"\']*', text)
    if m:
        return 'bilibili', m.group(0)
    # B站短链
    m = re.search(r'https?://b23\.tv/[A-Za-z0-9]+', text)
    if m:
        return 'bilibili', m.group(0)
    return None, None

# ── 通用工具 ──────────────────────────────────────────────

def resolve_redirect(url):
    """跟踪重定向获取最终 URL"""
    req = urllib.request.Request(url)
    req.add_header('User-Agent', UA)
    resp = urllib.request.urlopen(req)
    return resp.url

def clean_filename(title, fallback='video'):
    """清理字符串为安全文件名"""
    title = re.sub(r'[#@\s]+', '_', title)
    title = re.sub(r'[/\\:*?"<>|]', '', title)
    title = title.strip('_')
    # 截断过长文件名
    if len(title.encode('utf-8')) > 200:
        title = title[:60]
    return title or fallback

def download_file(cdn_url, output_path, referer, extra_headers=None):
    """下载文件到本地，支持大文件流式写入"""
    req = urllib.request.Request(cdn_url)
    req.add_header('Referer', referer)
    req.add_header('User-Agent', UA)
    if extra_headers:
        for k, v in extra_headers.items():
            req.add_header(k, v)
    with urllib.request.urlopen(req) as resp:
        with open(output_path, 'wb') as f:
            while True:
                chunk = resp.read(1024 * 1024)
                if not chunk:
                    break
                f.write(chunk)
    return os.path.getsize(output_path)

def launch_browser_and_capture(page_url, video_filter_fn, wait_s=10, extra_wait_s=5):
    """
    无头浏览器访问页面，通过 video_filter_fn 过滤网络请求捕获视频 CDN URL。
    返回 (video_cdn_url, page_title)
    """
    from playwright.sync_api import sync_playwright

    video_cdn_url = None

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent=UA, viewport={'width': 1280, 'height': 720})
        page = context.new_page()

        def on_response(response):
            nonlocal video_cdn_url
            if video_cdn_url is None and video_filter_fn(response):
                video_cdn_url = response.url

        page.on('response', on_response)

        try:
            page.goto(page_url, wait_until='domcontentloaded', timeout=30000)
            page.wait_for_timeout(wait_s * 1000)
        except Exception as e:
            print(f"  警告: 页面加载异常: {e}")

        if not video_cdn_url:
            print("  等待视频流加载...")
            page.wait_for_timeout(extra_wait_s * 1000)

        page_title = ""
        try:
            page_title = page.title()
        except:
            pass

        browser.close()

    return video_cdn_url, page_title

def launch_browser_and_eval(page_url, js_code, wait_s=5):
    """无头浏览器访问页面并执行 JS，返回 (result, page_title)"""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent=UA, viewport={'width': 1280, 'height': 720})
        page = context.new_page()

        try:
            page.goto(page_url, wait_until='domcontentloaded', timeout=30000)
            page.wait_for_timeout(wait_s * 1000)
        except Exception as e:
            print(f"  警告: 页面加载异常: {e}")

        result = page.evaluate(js_code)
        page_title = ""
        try:
            page_title = page.title()
        except:
            pass

        browser.close()

    return result, page_title

# ── 抖音下载 ──────────────────────────────────────────────

def download_douyin(url, output_name=None):
    print(f"[1/4] 解析抖音链接: {url}")

    m = re.search(r'/video/(\d+)', url)
    if m:
        video_id = m.group(1)
    else:
        final = resolve_redirect(url)
        m = re.search(r'/video/(\d+)', final)
        if not m:
            print(f"错误: 无法解析视频ID, 最终URL: {final}")
            sys.exit(1)
        video_id = m.group(1)

    page_url = f"https://www.douyin.com/video/{video_id}"
    print(f"[2/4] 视频ID: {video_id}, 启动无头浏览器...")

    def is_douyin_video(resp):
        u = resp.url
        return 'douyinvod.com' in u and 'video_mp4' in u

    cdn_url, page_title = launch_browser_and_capture(page_url, is_douyin_video)

    if not cdn_url:
        print("错误: 未能捕获到视频CDN地址")
        sys.exit(1)

    print(f"[3/4] 捕获到视频地址，开始下载...")

    if not output_name:
        title = page_title.replace(' - 抖音', '').strip()
        output_name = clean_filename(title, f"douyin_{video_id}") + '.mp4'

    output_path = os.path.join(os.path.expanduser('~/Downloads'), output_name)
    size = download_file(cdn_url, output_path, 'https://www.douyin.com/')
    print(f"[4/4] 下载完成: {output_path} ({size / 1048576:.1f}MB)")

# ── 小红书下载 ────────────────────────────────────────────

def download_xiaohongshu(url, output_name=None):
    print(f"[1/4] 解析小红书链接: {url}")

    if 'xhslink.com' in url:
        url = resolve_redirect(url)
        print(f"  跳转到: {url}")

    m = re.search(r'/(?:discovery/item|explore)/([a-f0-9]+)', url)
    note_id = m.group(1) if m else 'unknown'

    print(f"[2/4] 笔记ID: {note_id}, 启动无头浏览器...")

    def is_xhs_video(resp):
        u = resp.url
        ct = resp.headers.get('content-type', '')
        if 'video' in ct and 'xhscdn.com' in u:
            return True
        if re.search(r'sns-(video|bak)[^.]*\.xhscdn\.com.*\.mp4', u):
            return True
        return False

    cdn_url, page_title = launch_browser_and_capture(url, is_xhs_video)

    if not cdn_url:
        print("错误: 未能捕获到视频CDN地址（可能是图文笔记而非视频）")
        sys.exit(1)

    print(f"[3/4] 捕获到视频地址，开始下载...")

    if not output_name:
        title = page_title.replace(' - 小红书', '').strip()
        title = re.sub(r'小红书\s*[-–—]\s*你的生活兴趣社区', '', title).strip()
        output_name = clean_filename(title, f"xiaohongshu_{note_id}") + '.mp4'

    output_path = os.path.join(os.path.expanduser('~/Downloads'), output_name)
    size = download_file(cdn_url, output_path, 'https://www.xiaohongshu.com/')
    print(f"[4/4] 下载完成: {output_path} ({size / 1048576:.1f}MB)")

# ── B站下载 ───────────────────────────────────────────────

def download_bilibili(url, output_name=None):
    print(f"[1/5] 解析B站链接: {url}")

    # 短链跳转
    if 'b23.tv' in url:
        url = resolve_redirect(url)
        print(f"  跳转到: {url}")

    m = re.search(r'/video/([A-Za-z0-9]+)', url)
    bvid = m.group(1) if m else 'unknown'

    # 清理 URL 参数，只保留 BV 号
    page_url = f"https://www.bilibili.com/video/{bvid}/"
    print(f"[2/5] BV号: {bvid}, 启动无头浏览器...")

    # B站视频信息嵌在 window.__playinfo__ 中
    js_code = '''() => {
        const info = window.__playinfo__;
        if (!info) return null;
        const title = document.title;
        return JSON.stringify({ playinfo: info, title: title });
    }'''

    result, page_title = launch_browser_and_eval(page_url, js_code)

    if not result:
        print("错误: 未找到 __playinfo__，可能是番剧/付费内容")
        sys.exit(1)

    data = json.loads(result)
    playinfo = data['playinfo']
    page_title = data.get('title', page_title)

    dash = playinfo.get('data', {}).get('dash')
    if not dash:
        # 尝试 durl 格式（老视频）
        durl = playinfo.get('data', {}).get('durl', [])
        if durl:
            print(f"[3/5] 检测到非 DASH 格式，直接下载...")
            video_url = durl[0]['url']
            if not output_name:
                title = page_title.replace('_哔哩哔哩_bilibili', '').strip()
                output_name = clean_filename(title, f"bilibili_{bvid}") + '.mp4'
            output_path = os.path.join(os.path.expanduser('~/Downloads'), output_name)
            size = download_file(video_url, output_path, 'https://www.bilibili.com/',
                                 {'Origin': 'https://www.bilibili.com'})
            print(f"[5/5] 下载完成: {output_path} ({size / 1048576:.1f}MB)")
            return
        print("错误: 无法解析视频流信息")
        sys.exit(1)

    # DASH 格式: 选最高画质视频和音频
    videos = sorted(dash['video'], key=lambda x: x['bandwidth'], reverse=True)
    audios = sorted(dash['audio'], key=lambda x: x['bandwidth'], reverse=True)
    best_video = videos[0]
    best_audio = audios[0]

    print(f"[3/5] 视频: {best_video.get('width','?')}x{best_video.get('height','?')} {best_video['codecs']}")
    print(f"       音频: {best_audio['codecs']}")

    # 下载视频流和音频流到临时目录
    tmp_dir = '/tmp/bili_dl'
    os.makedirs(tmp_dir, exist_ok=True)
    video_path = os.path.join(tmp_dir, 'video.m4s')
    audio_path = os.path.join(tmp_dir, 'audio.m4s')

    referer = 'https://www.bilibili.com/'
    headers = {'Origin': 'https://www.bilibili.com'}

    print(f"[3/5] 下载视频流...")
    vs = download_file(best_video['baseUrl'], video_path, referer, headers)
    print(f"       视频: {vs / 1048576:.1f}MB")

    print(f"[4/5] 下载音频流...")
    aus = download_file(best_audio['baseUrl'], audio_path, referer, headers)
    print(f"       音频: {aus / 1048576:.1f}MB")

    # 确定输出文件名
    if not output_name:
        title = page_title.replace('_哔哩哔哩_bilibili', '').strip()
        output_name = clean_filename(title, f"bilibili_{bvid}") + '.mp4'

    output_path = os.path.join(os.path.expanduser('~/Downloads'), output_name)

    # ffmpeg 合并
    print(f"[5/5] ffmpeg 合并音视频...")
    result = subprocess.run(
        ['ffmpeg', '-y', '-i', video_path, '-i', audio_path,
         '-c:v', 'copy', '-c:a', 'copy', output_path],
        capture_output=True, text=True
    )

    # 清理临时文件
    try:
        os.remove(video_path)
        os.remove(audio_path)
        os.rmdir(tmp_dir)
    except:
        pass

    if result.returncode != 0:
        print(f"ffmpeg 合并失败: {result.stderr[:300]}")
        print("提示: 请确保已安装 ffmpeg (brew install ffmpeg)")
        sys.exit(1)

    size = os.path.getsize(output_path) / 1048576
    print(f"下载完成: {output_path} ({size:.1f}MB)")

# ── 入口 ──────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print("用法: python3 download.py <分享链接或文本> [输出文件名]")
        print("支持: 抖音 / 小红书 / B站")
        sys.exit(1)

    share_text = sys.argv[1]
    output_name = sys.argv[2] if len(sys.argv) > 2 else None

    platform, url = detect_platform(share_text)

    if platform == 'douyin':
        download_douyin(url, output_name)
    elif platform == 'xiaohongshu':
        download_xiaohongshu(url, output_name)
    elif platform == 'bilibili':
        download_bilibili(url, output_name)
    else:
        print(f"错误: 无法识别平台")
        print(f"支持: 抖音(v.douyin.com) / 小红书(xiaohongshu.com) / B站(bilibili.com)")
        sys.exit(1)

if __name__ == '__main__':
    main()
