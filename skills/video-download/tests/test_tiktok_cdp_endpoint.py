import importlib.util
import os
from pathlib import Path
import unittest
from unittest.mock import patch


spec = importlib.util.spec_from_file_location(
    "video_download_tiktok_cdp",
    Path(__file__).parents[1] / "scripts" / "download.py",
)
video_download = importlib.util.module_from_spec(spec)
spec.loader.exec_module(video_download)


class _FailingChromium:
    def __init__(self, attempts):
        self.attempts = attempts

    def connect_over_cdp(self, endpoint):
        self.attempts.append(endpoint)
        raise RuntimeError("unavailable")


class _PlaywrightContext:
    def __init__(self, attempts):
        self.chromium = _FailingChromium(attempts)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False


class TikTokCdpEndpointTests(unittest.TestCase):
    def test_explicit_endpoint_is_the_only_cdp_target(self):
        attempts = []
        endpoint = "http://127.0.0.1:9225"
        with patch.dict(
            os.environ,
            {"VIDEO_DOWNLOAD_TIKTOK_CDP_ENDPOINT": endpoint},
            clear=False,
        ), patch(
            "playwright.sync_api.sync_playwright",
            return_value=_PlaywrightContext(attempts),
        ):
            with self.assertRaises(RuntimeError):
                video_download.download_tiktok_cdp(
                    "https://www.tiktok.com/@popmartglobal/video/7688626002200907038"
                )

        self.assertEqual(attempts, [endpoint])

    def test_default_endpoint_does_not_fall_back_to_another_browser(self):
        attempts = []
        with patch.dict(
            os.environ,
            {},
            clear=True,
        ), patch(
            "playwright.sync_api.sync_playwright",
            return_value=_PlaywrightContext(attempts),
        ):
            with self.assertRaises(RuntimeError):
                video_download.download_tiktok_cdp(
                    "https://www.tiktok.com/@popmartglobal/video/7688626002200907038"
                )

        self.assertEqual(attempts, ["http://127.0.0.1:9225"])


if __name__ == "__main__":
    unittest.main()
