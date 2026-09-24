import copy
import importlib.util
from pathlib import Path
import unittest


PATH = Path(__file__).with_name('profile_data.py')


class TikTokProfileDataTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location('tiktok_profile_data', PATH)
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)
        self.item = {
            'id': '7688626002200907038',
            'createTime': 1767196800,
            'desc': 'new item',
            'author': {'id': '6805797604203643906', 'uniqueId': 'popmartglobal', 'nickname': 'POP MART'},
            'stats': {'playCount': 10, 'diggCount': 2, 'commentCount': 1, 'collectCount': 0, 'shareCount': 3},
            'video': {'duration': 12, 'width': 720, 'height': 1280,
                      'playAddr': 'https://v.example/video.mp4',
                      'cover': 'https://p.example/cover.jpg'},
        }

    def extract(self, items=None):
        payload = {'statusCode': 0, 'itemList': items if items is not None else [self.item]}
        return self.m.extract_profile_records(payload, 'popmartglobal', 'now')

    def test_video_stats_and_media_are_normalized(self):
        row = self.extract()[0]
        self.assertEqual(row['id'], self.item['id'])
        self.assertEqual(row['url'], f"https://www.tiktok.com/@popmartglobal/video/{self.item['id']}")
        self.assertEqual(row['statistics']['play_count'], 10)
        self.assertEqual(row['statistics']['collect_count'], 0)
        self.assertEqual(row['video']['playAddr'], 'https://v.example/video.mp4')
        self.assertEqual(row['cover'], 'https://p.example/cover.jpg')

    def test_photo_urls_keep_order(self):
        self.item.pop('video')
        self.item['imagePost'] = {'images': [
            {'imageURL': {'urlList': ['https://i.example/1.jpg']}},
            {'imageURL': {'urlList': ['https://i.example/2.jpg']}},
        ]}
        row = self.extract()[0]
        self.assertEqual(row['type'], 'note')
        self.assertEqual(row['imageUrls'], ['https://i.example/1.jpg', 'https://i.example/2.jpg'])

    def test_scraper_keeps_old_and_undated_items_for_callers_to_decide(self):
        old = copy.deepcopy(self.item); old['id'] = '1'; old['createTime'] = 1767196799
        missing = copy.deepcopy(self.item); missing['id'] = '2'; missing.pop('createTime')
        self.assertEqual([row['id'] for row in self.extract([old, self.item, missing])],
                         ['1', self.item['id'], '2'])

    def test_wrong_author_and_api_error_are_rejected(self):
        wrong = copy.deepcopy(self.item); wrong['author']['uniqueId'] = 'another'
        self.assertEqual(self.extract([wrong]), [])
        with self.assertRaises(ValueError):
            self.m.extract_profile_records({'statusCode': 1, 'itemList': [self.item]}, 'popmartglobal', 'now')

    def test_account_snapshot_is_author_bound_and_preserves_zero(self):
        scope = {'webapp.user-detail': {'userInfo': {
            'user': {'id': 'account-id', 'uniqueId': 'popmartglobal', 'nickname': 'POP MART'},
            'stats': {'followerCount': 0, 'followingCount': 2, 'heartCount': 3, 'videoCount': 4}}}}
        row = self.m.account_snapshot(scope, 'popmartglobal', 5)
        self.assertEqual(row['follower_count'], 0)
        self.assertEqual(row['platform_account_id'], 'account-id')
        with self.assertRaises(ValueError):
            self.m.account_snapshot(scope, 'other', 5)


if __name__ == '__main__':
    unittest.main()
