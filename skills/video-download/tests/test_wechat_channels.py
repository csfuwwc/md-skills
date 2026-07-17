import importlib.util
import json
import os
import sys
import tempfile
import unittest
from unittest import mock


SCRIPT = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "scripts", "download.py"
)
SPEC = importlib.util.spec_from_file_location("video_download", SCRIPT)
video_download = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(video_download)


class FakeResponse:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode("utf-8")

    def read(self):
        return self.payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class WeChatChannelsTests(unittest.TestCase):
    def test_detects_share_and_preview_urls(self):
        cases = [
            (
                "看看这个 https://weixin.qq.com/sph/ARebDCbPGy",
                "https://weixin.qq.com/sph/ARebDCbPGy",
            ),
            (
                "https://channels.weixin.qq.com/finder-preview/pages/sph?id=ARebDCbPGy",
                "https://channels.weixin.qq.com/finder-preview/pages/sph?id=ARebDCbPGy",
            ),
        ]
        for text, expected_url in cases:
            with self.subTest(text=text):
                self.assertEqual(
                    video_download.detect_platform(text),
                    ("wechat_channels", expected_url),
                )

    def test_parses_reference_resolver_shape_and_prefers_h264(self):
        payload = {
            "code": 0,
            "msg": "成功",
            "data": {
                "data": {
                    "authorInfo": {"nickname": "饼干哥哥AGI"},
                    "feedInfo": {
                        "description": "AI稳定生视频",
                        "videoUrl": "https://cdn.example/default.mp4",
                        "originVideoUrl": "https://cdn.example/original.mp4",
                        "h264VideoInfo": {
                            "videoUrl": "https://cdn.example/h264.mp4"
                        },
                        "coverUrl": "https://cdn.example/cover.jpg",
                        "createtime": 1784172001,
                        "likeCountFmt": "5",
                    },
                },
                "errCode": 0,
                "errMsg": "",
            },
        }

        result = video_download.parse_wechat_channels_resolver_response(payload)

        self.assertEqual(result["video_url"], "https://cdn.example/h264.mp4")
        self.assertEqual(result["author"], "饼干哥哥AGI")
        self.assertEqual(result["description"], "AI稳定生视频")
        self.assertEqual(result["cover_url"], "https://cdn.example/cover.jpg")
        self.assertEqual(result["metrics"]["like"], "5")

    def test_resolver_uses_query_and_api_key_without_cookie(self):
        payload = {
            "code": 0,
            "data": {
                "data": {
                    "authorInfo": {"nickname": "作者"},
                    "feedInfo": {"videoUrl": "https://cdn.example/video.mp4"},
                }
            },
        }
        captured = {}

        def fake_urlopen(request, timeout):
            captured["url"] = request.full_url
            captured["headers"] = dict(request.header_items())
            captured["timeout"] = timeout
            return FakeResponse(payload)

        with mock.patch.object(video_download.urllib.request, "urlopen", fake_urlopen):
            result = video_download.resolve_wechat_channels(
                "https://weixin.qq.com/sph/ARebDCbPGy",
                resolver_url="http://api.example.test/api/channels/parse_sph",
                api_key="test-api-key-value",
            )

        query = video_download.urllib.parse.parse_qs(
            video_download.urllib.parse.urlparse(captured["url"]).query
        )
        self.assertEqual(
            query["url"], ["https://weixin.qq.com/sph/ARebDCbPGy"]
        )
        self.assertEqual(captured["headers"]["X-api-key"], "test-api-key-value")
        self.assertNotIn("Cookie", captured["headers"])
        self.assertEqual(result["video_url"], "https://cdn.example/video.mp4")

    def test_missing_resolver_configuration_is_actionable(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(
                RuntimeError, "WECHAT_CHANNELS_RESOLVER_URL"
            ):
                video_download.resolve_wechat_channels(
                    "https://weixin.qq.com/sph/ARebDCbPGy"
                )

    def test_rejects_encrypted_or_missing_media(self):
        with self.assertRaisesRegex(RuntimeError, "加密"):
            video_download.parse_wechat_channels_resolver_response(
                {
                    "code": 0,
                    "data": {
                        "videoUrl": "https://cdn.example/encrypted.mp4",
                        "decryptKey": "123456",
                    },
                }
            )

        with self.assertRaisesRegex(RuntimeError, "视频地址"):
            video_download.parse_wechat_channels_resolver_response(
                {"code": 0, "data": {"data": {"feedInfo": {}}}}
            )

    def test_download_writes_video_and_sanitized_metadata(self):
        resolved = {
            "video_url": "https://cdn.example/video.mp4?token=short-lived",
            "author": "作者/名字",
            "description": "一条视频描述",
            "cover_url": "https://cdn.example/cover.jpg",
            "created_at": 1784172001,
            "metrics": {"like": "5"},
        }

        def fake_download(url, output_path, referer, extra_headers=None):
            with open(output_path, "wb") as handle:
                handle.write(b"fake-mp4")
            return 8

        with tempfile.TemporaryDirectory() as out_dir:
            with mock.patch.object(
                video_download, "resolve_wechat_channels", return_value=resolved
            ), mock.patch.object(
                video_download, "download_file", side_effect=fake_download
            ), mock.patch.object(
                video_download, "validate_video_file", return_value=True
            ), mock.patch.dict(
                os.environ, {"VIDEO_DOWNLOAD_OUTPUT_DIR": out_dir}, clear=False
            ):
                output_path = video_download.download_wechat_channels(
                    "https://weixin.qq.com/sph/ARebDCbPGy"
                )

            self.assertTrue(os.path.exists(output_path))
            self.assertNotIn("/", os.path.basename(output_path))
            with open(output_path + ".meta.json", encoding="utf-8") as handle:
                metadata = json.load(handle)
            self.assertEqual(metadata["platform"], "wechat_channels")
            self.assertEqual(metadata["source_url"], "https://weixin.qq.com/sph/ARebDCbPGy")
            self.assertNotIn("video_url", metadata)
            self.assertNotIn("token=short-lived", json.dumps(metadata))


if __name__ == "__main__":
    unittest.main()
