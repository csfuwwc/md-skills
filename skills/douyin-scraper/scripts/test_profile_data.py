import copy
import importlib.util
from pathlib import Path
import unittest

PATH = Path(__file__).with_name('profile_data.py')


class ProfileDataTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(PATH.exists(), 'Reusable profile extractor is missing')
        spec = importlib.util.spec_from_file_location('profile_data', PATH)
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)
        self.item = {'aweme_id': '123', 'author': {'sec_uid': 'author-a'},
                     'statistics': {'digg_count': 0}, 'video': {
                         'cover': {'url_list': ['https://cdn.example/display.jpg']},
                         'origin_cover': {'url_list': ['https://cdn.example/original.jpg']}}}

    def extract(self, items=None, **kw):
        return self.m.extract_profile_records(
            {'status_code': 0, 'aweme_list': items if items is not None else [self.item]},
            'author-a', '2026-01-01T00:00:00+08:00', **kw)

    def test_video_quality_candidates_survive_profile_extraction(self):
        self.item['video']['duration'] = 12000
        self.item['video']['bit_rate'] = [
            {'gear_name':'normal_720','bit_rate':2000000,'is_h265':0,
             'play_addr':{'width':720,'height':1280,'data_size':3000,
                          'url_list':['https://cdn.example/video.mp4']}}]
        record = self.extract()[0]
        self.assertEqual(record['video']['duration'],12000)
        self.assertEqual(record['video']['bit_rate'][0]['play_addr']['url_list'],['https://cdn.example/video.mp4'])
        self.assertEqual(record['videoQualities'][0]['width'],720)
        self.assertNotIn('url_list',record['videoQualities'][0])

    def test_display_cover_wins_over_origin(self):
        r = self.extract()[0]
        self.assertEqual(r['cover'], 'https://cdn.example/display.jpg')
        self.assertEqual(r['coverSource'], 'video.cover')
        self.assertFalse(r['coverFallback'])

    def test_origin_fallback_is_explicit(self):
        self.item['video']['cover']['url_list'] = []
        r = self.extract()[0]
        self.assertEqual(r['coverSource'], 'video.origin_cover')
        self.assertTrue(r['coverFallback'])

    def test_dynamic_cover_does_not_fill_static_cover(self):
        self.item['video'] = {'dynamic_cover': {'url_list': ['https://cdn.example/a.webp']}}
        self.assertIsNone(self.extract()[0]['cover'])

    def test_zero_preserved_missing_metric_stays_null(self):
        stats = self.extract()[0]['statistics']
        self.assertEqual(stats['digg_count'], 0)
        self.assertIsNone(stats['comment_count'])

    def test_wrong_or_missing_author_rejected(self):
        wrong = copy.deepcopy(self.item); wrong['author']['sec_uid'] = 'other'
        missing = copy.deepcopy(self.item); missing['author'] = {}
        self.assertEqual(self.extract([wrong, missing]), [])

    def test_dedup_and_target_filter(self):
        self.assertEqual(len(self.extract([self.item, self.item], target_ids={'123'})), 1)
        self.assertEqual(self.extract(target_ids={'456'}), [])

    def test_photo_first_image_is_candidate_not_verified_homepage_cover(self):
        self.item.update(aweme_type=68, images=[{'url_list': ['https://cdn.example/photo.jpg']}])
        r = self.extract()[0]
        self.assertEqual(r['coverSource'], 'images[0]')
        self.assertEqual(r['coverVerification'], 'needs_homepage_check')
        self.assertIn('/note/123', r['url'])

    def test_api_error_does_not_yield_records(self):
        with self.assertRaises(ValueError):
            self.m.extract_profile_records({'status_code': 1, 'aweme_list': [self.item]}, 'author-a', 'now')

    def test_empty_author_cannot_disable_binding(self):
        with self.assertRaises(ValueError):
            self.m.extract_profile_records({'aweme_list': [self.item]}, '', 'now')


if __name__ == '__main__':
    unittest.main()


class MaterialImagesTest(__import__('unittest').TestCase):
    def test_all_note_images_preserve_order(self):
        from profile_data import extract_profile_records
        rows = extract_profile_records({'aweme_list': [{'aweme_id': '1', 'author': {'sec_uid': 'u'},
            'images': [{'url_list': ['https://i/1.jpg']}, {'url_list': ['https://i/2.jpg']}]}]}, 'u', 'now')
        self.assertEqual(rows[0]['imageUrls'], ['https://i/1.jpg', 'https://i/2.jpg'])
