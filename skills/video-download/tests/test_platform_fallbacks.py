import importlib.util
import json
import os
import stat
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock


SCRIPT = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "scripts", "download.py"
)
SPEC = importlib.util.spec_from_file_location("video_download_fallbacks", SCRIPT)
video_download = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(video_download)


class PlatformFallbackTests(unittest.TestCase):
    def test_douyin_falls_back_to_ytdlp_with_platform_cookies(self):
        with mock.patch.object(
            video_download,
            "launch_browser_and_capture",
            return_value=(None, ""),
        ), mock.patch.object(
            video_download,
            "download_ytdlp",
            return_value="fallback-result",
        ) as fallback:
            try:
                result = video_download.download_douyin(
                    "https://www.douyin.com/video/7625857786269715752",
                    "douyin.mp4",
                )
            except SystemExit:
                self.fail("抖音 Playwright 失败后应回退 yt-dlp，而不是直接退出")

        self.assertEqual(result, "fallback-result")
        fallback.assert_called_once_with(
            "https://www.douyin.com/video/7625857786269715752",
            "douyin.mp4",
            platform="douyin",
        )

    def test_xiaohongshu_falls_back_to_ytdlp_with_platform_cookies(self):
        url = "https://www.xiaohongshu.com/explore/6411cf99000000001300b6d9"
        with mock.patch.object(
            video_download,
            "launch_browser_and_capture",
            return_value=(None, ""),
        ), mock.patch.object(
            video_download,
            "download_ytdlp",
            return_value="fallback-result",
        ) as fallback:
            try:
                result = video_download.download_xiaohongshu(url, "xhs.mp4")
            except SystemExit:
                self.fail("小红书 Playwright 失败后应回退 yt-dlp，而不是直接退出")

        self.assertEqual(result, "fallback-result")
        fallback.assert_called_once_with(
            url,
            "xhs.mp4",
            platform="xiaohongshu",
        )

    def test_bilibili_uses_ytdlp_before_playwright(self):
        url = "https://www.bilibili.com/video/BV1xx411c7mD"
        with mock.patch.object(
            video_download,
            "download_ytdlp",
            return_value="ytdlp-result",
        ) as primary, mock.patch.object(
            video_download,
            "launch_browser_and_eval",
            side_effect=AssertionError("不应先启动 Playwright"),
        ):
            try:
                result = video_download.download_bilibili(url, "bili.mp4")
            except AssertionError as exc:
                self.fail(str(exc))

        self.assertEqual(result, "ytdlp-result")
        primary.assert_called_once_with(
            url,
            "bili.mp4",
            platform="bilibili",
        )

    def test_bilibili_falls_back_to_playwright_when_ytdlp_fails(self):
        url = "https://www.bilibili.com/video/BV1xx411c7mD"
        with mock.patch.object(
            video_download,
            "download_ytdlp",
            side_effect=RuntimeError("yt-dlp failed"),
        ), mock.patch.object(
            video_download,
            "download_bilibili_playwright",
            return_value="playwright-result",
            create=True,
        ) as fallback, mock.patch.object(
            video_download,
            "launch_browser_and_eval",
            side_effect=AssertionError("应通过独立 Playwright 兜底函数执行"),
        ):
            try:
                result = video_download.download_bilibili(url, "bili.mp4")
            except AssertionError as exc:
                self.fail(str(exc))

        self.assertEqual(result, "playwright-result")
        fallback.assert_called_once_with(url, "bili.mp4")

    def test_ytdlp_uses_scoped_cookie_file_and_removes_it(self):
        cookie = {
            "name": "sessionid",
            "value": "secret-value",
            "domain": ".douyin.com",
            "path": "/",
            "expires": -1,
            "secure": True,
        }
        captured = {}

        def fake_run(command, text):
            cookie_path = command[command.index("--cookies") + 1]
            captured["command"] = command
            captured["cookie_path"] = cookie_path
            captured["mode"] = stat.S_IMODE(os.stat(cookie_path).st_mode)
            with open(cookie_path, encoding="utf-8") as handle:
                captured["cookie_text"] = handle.read()
            return SimpleNamespace(returncode=0)

        with tempfile.TemporaryDirectory() as config_dir, tempfile.TemporaryDirectory() as output_dir:
            with open(
                os.path.join(config_dir, "douyin_cookies.json"),
                "w",
                encoding="utf-8",
            ) as handle:
                json.dump([cookie], handle)

            with mock.patch.object(video_download, "COOKIE_DIR", config_dir), mock.patch.object(
                video_download, "get_ytdlp_command", return_value=["yt-dlp"]
            ), mock.patch.object(
                video_download.subprocess, "run", side_effect=fake_run
            ), mock.patch.dict(
                os.environ, {"VIDEO_DOWNLOAD_OUTPUT_DIR": output_dir}, clear=False
            ):
                try:
                    video_download.download_ytdlp(
                        "https://www.douyin.com/video/1",
                        "video.mp4",
                        platform="douyin",
                    )
                except TypeError:
                    self.fail("download_ytdlp 应接受 platform 并使用对应平台 Cookie")

        self.assertIn("--cookies", captured["command"])
        self.assertEqual(captured["mode"], 0o600)
        self.assertIn(".douyin.com", captured["cookie_text"])
        self.assertIn("\t0\tsessionid\t", captured["cookie_text"])
        self.assertNotIn("secret-value", " ".join(captured["command"]))
        self.assertFalse(os.path.exists(captured["cookie_path"]))


if __name__ == "__main__":
    unittest.main()
