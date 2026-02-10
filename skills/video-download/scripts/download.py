#!/usr/bin/env python3
"""
抖音 / 小红书 / B站 视频无头下载脚本
用法:
  python3 download.py <分享链接或文本> [输出文件名]
  python3 download.py login <平台>    # 登录并保存 cookie（bilibili/douyin/xiaohongshu）

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
COOKIE_DIR = os.path.expanduser('~/.config/video-download')

# ── Cookie 管理 ─────────────────────────────────────────

def get_cookie_path(platform):
    """获取平台 cookie 文件路径"""
    return os.path.join(COOKIE_DIR, f'{platform}_cookies.json')

def load_cookies(platform):
    """加载已保存的 cookie，返回 list 或 None"""
    path = get_cookie_path(platform)
    if os.path.exists(path):
        try:
            with open(path, 'r') as f:
                cookies = json.load(f)
            # 检查关键 cookie 是否过期
            if cookies_expired(platform, cookies):
                print(f"  {platform} cookie 已过期")
                return None
            print(f"  已加载 {platform} 登录态 ({len(cookies)} cookies)")
            return cookies
        except Exception:
            return None
    return None

def cookies_expired(platform, cookies):
    """检查平台关键 cookie 是否过期"""
    import time
    now = time.time()
    # 各平台的关键 cookie 名
    key_cookies = {
        'bilibili': ['SESSDATA', 'bili_jct'],
        'douyin': ['sessionid', 'sessionid_ss'],
        'xiaohongshu': ['web_session'],
    }
    keys = key_cookies.get(platform, [])
    if not keys:
        return False
    for c in cookies:
        if c.get('name') in keys:
            expires = c.get('expires', 0)
            # expires=-1 表示会话 cookie（不过期）; expires>0 检查是否过期
            if expires > 0 and expires < now:
                return True
            return False  # 找到关键 cookie 且未过期
    return True  # 没找到关键 cookie，视为过期/未登录

def check_login_required(platform):
    """检查是否需要登录。返回 True 表示需要登录。
    B站必须登录才能获取高清，其他平台可选。"""
    # B站: 没有有效 cookie 时提示登录
    if platform == 'bilibili':
        path = get_cookie_path(platform)
        if not os.path.exists(path):
            return True
        cookies = None
        try:
            with open(path, 'r') as f:
                cookies = json.load(f)
        except Exception:
            return True
        if cookies_expired(platform, cookies):
            return True
    return False

def save_cookies(platform, cookies):
    """保存 cookie 到文件"""
    os.makedirs(COOKIE_DIR, exist_ok=True)
    path = get_cookie_path(platform)
    with open(path, 'w') as f:
        json.dump(cookies, f, indent=2, ensure_ascii=False)
    print(f"  已保存 {len(cookies)} 个 cookie 到 {path}")

def do_login(platform, signal_file=None):
    """打开可见浏览器让用户登录，完成后保存 cookie。
    
    signal_file: 如果指定，除了监听浏览器关闭外，也轮询此文件是否存在。
                 文件出现时立即保存 cookie 并关闭浏览器。
                 用于 Agent 交互式登录流程（用户点击确认按钮触发）。
    """
    from playwright.sync_api import sync_playwright
    import time

    login_urls = {
        'bilibili': 'https://passport.bilibili.com/login',
        'douyin': 'https://www.douyin.com/',
        'xiaohongshu': 'https://www.xiaohongshu.com/',
    }

    if platform not in login_urls:
        print(f"错误: 不支持的平台 '{platform}'")
        print(f"支持: {', '.join(login_urls.keys())}")
        sys.exit(1)

    url = login_urls[platform]
    print(f"正在打开 {platform} 登录页面...")
    if signal_file:
        print("请在浏览器中完成登录，然后点击会话中的确认按钮，或关闭浏览器窗口。")
    else:
        print("请在浏览器中完成登录，登录成功后关闭浏览器窗口即可。")
    print()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)  # 可见浏览器
        context = browser.new_context(user_agent=UA, viewport={'width': 1280, 'height': 800})
        page = context.new_page()
        page.goto(url, wait_until='domcontentloaded', timeout=60000)

        if signal_file:
            # 轮询模式: 检查 signal_file 或浏览器关闭
            # 清理可能残留的信号文件
            if os.path.exists(signal_file):
                os.remove(signal_file)
            
            deadline = time.time() + 300  # 最多 5 分钟
            while time.time() < deadline:
                # 检查信号文件
                if os.path.exists(signal_file):
                    print("  收到确认信号，正在保存 cookie...")
                    try:
                        os.remove(signal_file)
                    except OSError:
                        pass
                    break
                # 检查浏览器是否被关闭
                try:
                    page.title()  # 如果页面已关闭会抛异常
                except Exception:
                    print("  检测到浏览器关闭，正在保存 cookie...")
                    break
                time.sleep(1)
        else:
            # 原始模式: 只等浏览器关闭
            try:
                page.wait_for_event('close', timeout=300000)
            except Exception:
                pass

        cookies = context.cookies()
        try:
            browser.close()
        except Exception:
            pass

    if cookies:
        save_cookies(platform, cookies)
        print(f"\n{platform} 登录成功！后续下载将自动使用登录态。")
    else:
        print("\n未获取到 cookie，请确认已完成登录。")

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
    # 抖音精选/推荐页 modal_id 格式
    m = re.search(r'https?://www\.douyin\.com/[^\s]*[?&]modal_id=(\d+)', text)
    if m:
        return 'douyin', f'https://www.douyin.com/video/{m.group(1)}'
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

def launch_browser_and_capture(page_url, video_filter_fn, wait_s=10, extra_wait_s=5, platform=None):
    """
    无头浏览器访问页面，通过 video_filter_fn 过滤网络请求捕获视频 CDN URL。
    返回 (video_cdn_url, page_title)
    """
    from playwright.sync_api import sync_playwright

    video_cdn_url = None
    cookies = load_cookies(platform) if platform else None

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent=UA, viewport={'width': 1280, 'height': 720})
        if cookies:
            context.add_cookies(cookies)
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

def launch_browser_and_eval(page_url, js_code, wait_s=5, platform=None):
    """无头浏览器访问页面并执行 JS，返回 (result, page_title)"""
    from playwright.sync_api import sync_playwright
    cookies = load_cookies(platform) if platform else None

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent=UA, viewport={'width': 1280, 'height': 720})
        if cookies:
            context.add_cookies(cookies)
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

    cdn_url, page_title = launch_browser_and_capture(page_url, is_douyin_video, platform='douyin')

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

    cdn_url, page_title = launch_browser_and_capture(url, is_xhs_video, platform='xiaohongshu')

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

    result, page_title = launch_browser_and_eval(page_url, js_code, platform='bilibili')

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
        print("用法:")
        print("  python3 download.py <分享链接或文本> [输出文件名]  # 下载视频")
        print("  python3 download.py login <平台> [--signal-file F] # 登录保存cookie")
        print("  python3 download.py check-login <平台>             # 检查登录状态")
        print()
        print("支持平台: 抖音 / 小红书 / B站")
        print("登录平台: bilibili / douyin / xiaohongshu")
        sys.exit(1)

    # check-login 子命令: 退出码 0=已登录, 2=需要登录
    if sys.argv[1] == 'check-login':
        if len(sys.argv) < 3:
            print("用法: python3 download.py check-login <平台>")
            sys.exit(1)
        platform = sys.argv[2]
        if check_login_required(platform):
            print(f"LOGIN_REQUIRED:{platform}")
            sys.exit(2)
        else:
            print(f"LOGIN_OK:{platform}")
            sys.exit(0)

    # login 子命令
    if sys.argv[1] == 'login':
        if len(sys.argv) < 3:
            print("用法: python3 download.py login <平台> [--signal-file <path>]")
            print("平台: bilibili / douyin / xiaohongshu")
            sys.exit(1)
        platform = sys.argv[2]
        signal_file = None
        if '--signal-file' in sys.argv:
            idx = sys.argv.index('--signal-file')
            if idx + 1 < len(sys.argv):
                signal_file = sys.argv[idx + 1]
        do_login(platform, signal_file=signal_file)
        return

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
