"""hot-topics:解析 / 失败姿态 / 源隔离。不联网。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import hot  # noqa: E402

WEIBO_PAYLOAD = {"data": {"realtime": [
    {"word": "C罗宣布结婚", "num": 1160078, "label_name": "热"},
    {"word": "", "num": 1},                      # 空词要被丢掉
    {"word": "武大靖出任主教练", "num": 858727},
]}}
BILI_PAYLOAD = {"code": 0, "data": {"list": [
    {"title": "《影之刃零》预购开启", "bvid": "BV1Hmuv68EWW", "short_link_v2": "https://b23.tv/x",
     "desc": "实机预告", "stat": {"view": 2526863}, "owner": {"name": "官方"}},
]}}


class WeiboTest(unittest.TestCase):
    def test_parses_and_ranks(self):
        topics = hot.fetch_weibo(limit=10, get_json=lambda url: WEIBO_PAYLOAD)

        self.assertEqual([t["title"] for t in topics], ["C罗宣布结婚", "武大靖出任主教练"])
        self.assertEqual(topics[0]["heat"], 1160078)
        # rank = 平台原始位次:丢掉不可用条目后**不重排号**,否则报出来的名次和平台对不上
        self.assertEqual([t["extra"]["rank"] for t in topics], [1, 3])

    def test_search_url_wraps_in_topic_marks(self):
        topics = hot.fetch_weibo(limit=1, get_json=lambda url: WEIBO_PAYLOAD)

        self.assertIn("%23", topics[0]["url"])  # #话题# 的 # 被编码

    def test_limit_applies_before_filtering(self):
        topics = hot.fetch_weibo(limit=2, get_json=lambda url: WEIBO_PAYLOAD)

        self.assertEqual(len(topics), 1)  # 前 2 条里有 1 条是空词

    def test_empty_result_is_an_error_not_silence(self):
        with self.assertRaises(hot.HotError):
            hot.fetch_weibo(get_json=lambda url: {"data": {"realtime": []}})

    def test_upstream_failure_wraps(self):
        def boom(url):
            raise OSError("connection reset")

        with self.assertRaises(hot.HotError):
            hot.fetch_weibo(get_json=boom)


class BilibiliTest(unittest.TestCase):
    def test_parses(self):
        topics = hot.fetch_bilibili(get_json=lambda url: BILI_PAYLOAD)

        self.assertEqual(topics[0]["title"], "《影之刃零》预购开启")
        self.assertEqual(topics[0]["heat"], 2526863)
        self.assertEqual(topics[0]["url"], "https://b23.tv/x")

    def test_falls_back_to_bvid_url(self):
        payload = {"code": 0, "data": {"list": [
            {"title": "无短链", "bvid": "BV1x", "stat": {"view": 1}}]}}

        topics = hot.fetch_bilibili(get_json=lambda url: payload)

        self.assertEqual(topics[0]["url"], "https://www.bilibili.com/video/BV1x")

    def test_nonzero_code_is_an_error(self):
        with self.assertRaises(hot.HotError):
            hot.fetch_bilibili(get_json=lambda url: {"code": -412, "data": {}})


class DispatchTest(unittest.TestCase):
    def test_unknown_source_names_the_available_ones(self):
        with self.assertRaises(hot.HotError) as caught:
            hot.fetch("douban")

        self.assertIn("weibo", str(caught.exception))

    def test_one_source_down_does_not_sink_the_others(self):
        """一个源挂了要继续拉别的,只有全挂才算失败。"""
        original = dict(hot.SOURCES)
        hot.SOURCES["broken"] = lambda limit=20: (_ for _ in ()).throw(hot.HotError("挂了"))
        hot.SOURCES["fine"] = lambda limit=20: [{"source": "fine", "title": "t", "heat": 1,
                                                 "url": "u", "extra": {"rank": 1}}]
        try:
            self.assertEqual(hot.main(["broken", "fine", "--json"]), 0)
            self.assertEqual(hot.main(["broken", "--json"]), 1)
        finally:
            hot.SOURCES.clear()
            hot.SOURCES.update(original)


class HeaderTest(unittest.TestCase):
    def test_referer_is_per_source(self):
        """B 站接口收到微博的 Referer 会 403,别再往通用客户端里塞。"""
        captured = {}

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return b'{"code":0,"data":{"list":[]}}'

        def fake_urlopen(request, timeout=None):
            captured["headers"] = dict(request.headers)
            return FakeResponse()

        original = hot.urllib.request.urlopen
        hot.urllib.request.urlopen = fake_urlopen
        try:
            hot._get_json("https://api.bilibili.com/x")
        finally:
            hot.urllib.request.urlopen = original

        self.assertNotIn("Referer", captured["headers"])


if __name__ == "__main__":
    unittest.main()
