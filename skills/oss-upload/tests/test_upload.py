"""oss-upload:对象名规则 / 类型分桶 / 幂等 / 签名。不联网。"""
import hashlib
import os
import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import upload  # noqa: E402

FIXED_NOW = datetime(2026, 8, 12, 15, 30, tzinfo=upload.CST)


def write(tmp, name, data=b"hello"):
    path = os.path.join(tmp, name)
    with open(path, "wb") as f:
        f.write(data)
    return path


class ObjectKeyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = self.enterContext(__import__("tempfile").TemporaryDirectory())

    def test_key_is_type_year_month_hash(self):
        path = write(self.tmp, "a.jpg", b"pixels")
        expected = hashlib.sha256(b"pixels").hexdigest()[:12]

        self.assertEqual(upload.object_key(path, FIXED_NOW), f"images/2026/08/{expected}.jpg")

    def test_same_content_same_key_regardless_of_filename(self):
        """内容一样就该落到同一个 key —— 幂等和去重全靠这条。"""
        first = write(self.tmp, "微信图片 2026.jpg", b"same")
        second = write(self.tmp, "cover.jpg", b"same")

        self.assertEqual(upload.object_key(first, FIXED_NOW),
                         upload.object_key(second, FIXED_NOW))

    def test_different_content_different_key(self):
        first = write(self.tmp, "a.jpg", b"one")
        second = write(self.tmp, "b.jpg", b"two")

        self.assertNotEqual(upload.object_key(first, FIXED_NOW),
                            upload.object_key(second, FIXED_NOW))

    def test_video_and_other_go_to_their_own_buckets(self):
        clip = write(self.tmp, "成片.mp4", b"v")
        note = write(self.tmp, "note.md", b"t")

        self.assertTrue(upload.object_key(clip, FIXED_NOW).startswith("videos/2026/08/"))
        self.assertTrue(upload.object_key(note, FIXED_NOW).startswith("files/2026/08/"))

    def test_unknown_extension_falls_back_to_files(self):
        weird = write(self.tmp, "dump.bin", b"x")

        self.assertTrue(upload.object_key(weird, FIXED_NOW).startswith("files/"))

    def test_uppercase_and_jpeg_normalise(self):
        """同一张图不能因为写成 .JPEG 就在桶里存两份。"""
        one = write(self.tmp, "a.JPEG", b"same")
        two = write(self.tmp, "a.jpg", b"same")

        self.assertEqual(upload.object_key(one, FIXED_NOW), upload.object_key(two, FIXED_NOW))

    def test_caller_cannot_influence_key(self):
        """key 是我们按内容算的,调用方给什么路径都爬不出类型桶。"""
        nested = os.path.join(self.tmp, "sub")
        os.makedirs(nested)
        path = os.path.join(nested, "..", "sub", "evil.jpg")
        write(nested, "evil.jpg", b"x")

        key = upload.object_key(path, FIXED_NOW)

        self.assertNotIn("..", key)
        self.assertTrue(key.startswith("images/2026/08/"))


class UploadTest(unittest.TestCase):
    def setUp(self):
        self.tmp = self.enterContext(__import__("tempfile").TemporaryDirectory())

    def test_skips_put_when_object_already_there(self):
        """已存在就不重传 —— 上行慢的机器上这条省的是几十分钟。"""
        path = write(self.tmp, "a.jpg", b"x")
        with mock.patch.object(upload, "exists", return_value=True), \
                mock.patch.object(upload, "_put_object") as put:
            result = upload.upload(path, FIXED_NOW)

        put.assert_not_called()
        self.assertTrue(result["existed"])

    def test_force_reuploads(self):
        path = write(self.tmp, "a.jpg", b"x")
        with mock.patch.object(upload, "exists", return_value=True), \
                mock.patch.object(upload, "_put_object") as put:
            upload.upload(path, FIXED_NOW, skip_existing=False)

        put.assert_called_once()

    def test_sends_real_content_type(self):
        path = write(self.tmp, "clip.mp4", b"x")
        with mock.patch.object(upload, "exists", return_value=False), \
                mock.patch.object(upload, "_put_object") as put:
            upload.upload(path, FIXED_NOW)

        self.assertEqual(put.call_args[0][2], "video/mp4")

    def test_missing_and_empty_files_raise(self):
        with self.assertRaises(upload.OssError):
            upload.upload(os.path.join(self.tmp, "nope.jpg"))
        with self.assertRaises(upload.OssError):
            upload.upload(write(self.tmp, "empty.jpg", b""))

    def test_url_uses_bound_domain(self):
        """默认 endpoint 会被阿里云强加 attachment 头,链接只能下载不能预览。"""
        url = upload.public_url("images/2026/08/abc.jpg")

        self.assertEqual(url, "https://vd.moimg.net/images/2026/08/abc.jpg")
        self.assertNotIn("aliyuncs.com", url)


class SigningTest(unittest.TestCase):
    FAKE = {"access_key_id": "AK", "access_key_secret": "SK", "security_token": "TOKEN",
            "expiration": "2099-01-01T00:00:00Z"}

    def test_authorization_header_shape(self):
        captured = {}

        def fake_urlopen(request, timeout=None):
            captured["headers"] = dict(request.headers)
            captured["url"] = request.full_url
            return mock.MagicMock(__enter__=lambda s: s, __exit__=lambda *a: False)

        with mock.patch.object(upload, "credentials", return_value=self.FAKE), \
                mock.patch.object(upload.urllib.request, "urlopen", fake_urlopen):
            upload._put_object("images/2026/08/abc.jpg", b"body", "image/jpeg")

        auth = captured["headers"]["Authorization"]
        self.assertTrue(auth.startswith("OSS4-HMAC-SHA256 Credential=AK/"))
        self.assertIn("/cn-beijing/oss/aliyun_v4_request,Signature=", auth)
        self.assertEqual(captured["headers"]["X-oss-security-token"], "TOKEN")
        self.assertEqual(captured["headers"]["X-oss-content-sha256"], "UNSIGNED-PAYLOAD")
        self.assertEqual(captured["url"],
                         "https://mdfile.oss-cn-beijing.aliyuncs.com/images/2026/08/abc.jpg")

    def test_credentials_are_cached_until_near_expiry(self):
        upload._cache.clear()
        calls = []

        def fake_urlopen(url, timeout=None):
            calls.append(url)
            payload = b'{"code":0,"data":{"access_key_id":"AK","access_key_secret":"SK",' \
                      b'"security_token":"T","expiration":"2099-01-01T00:00:00Z"}}'
            return mock.MagicMock(__enter__=lambda s: mock.Mock(read=lambda: payload),
                                  __exit__=lambda *a: False)

        with mock.patch.object(upload.urllib.request, "urlopen", fake_urlopen):
            upload.credentials()
            upload.credentials()

        self.assertEqual(len(calls), 1)
        upload._cache.clear()


if __name__ == "__main__":
    unittest.main()
