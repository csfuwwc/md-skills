import importlib.util
import struct
import unittest
import zlib

from profile_data import extract_profile_records

THUMB = 'https://p3-pc-sign.douyinpic.com/tos-cn-i-dy/sample~tplv-dy-cropcenter:323:430.jpeg?signature=synthetic'
OBJECT = 'https://p3-pc-sign.douyinpic.com/obj/tos-cn-i-dy/sample?signature=synthetic'
MIRROR = OBJECT.replace('p3-', 'p9-')


class CoverQualityTests(unittest.TestCase):
    def setUp(self):
        self.video = {'cover': {'uri': 'tos-cn-i-dy/sample', 'width': 720, 'height': 720,
                                'url_list': [THUMB, OBJECT, MIRROR]}}

    def record(self):
        return extract_profile_records({'aweme_list': [{'aweme_id': '123',
            'author': {'sec_uid': 'author'}, 'video': self.video}]}, 'author', 'now')[0]

    def test_extractor_keeps_same_image_options_for_quality_check(self):
        r = self.record()
        self.assertIn('coverCandidates', r)
        self.assertEqual([c['url'] for c in r['coverCandidates']], [THUMB, OBJECT, MIRROR])

    def resolve(self, values):
        self.assertIsNotNone(importlib.util.find_spec('cover_quality'), 'HD cover resolver is missing')
        import cover_quality
        def probe(url):
            v = values[url]
            if isinstance(v, Exception):
                raise v
            return v
        return cover_quality.upgrade_cover(self.record(), probe)

    def test_larger_static_same_image_wins_and_unrelated_fields_preserved(self):
        before = self.record()
        after = self.resolve({THUMB: (323, 430, 'jpeg'), OBJECT: (1242, 1657, 'jpeg')})
        self.assertEqual(after['cover'], OBJECT)
        self.assertEqual((after['coverWidth'], after['coverHeight']), (1242, 1657))
        self.assertEqual(after['coverQuality'], 'largest_verified_static')
        for k in ('statistics', 'caption', 'authorSecUid', 'id', 'coverVerification'):
            self.assertEqual(after[k], before[k])

    def test_object_name_alone_does_not_win(self):
        after = self.resolve({THUMB: (323, 430, 'jpeg'), OBJECT: (100, 100, 'jpeg')})
        self.assertEqual(after['cover'], THUMB)

    def test_failed_object_tries_returned_mirror(self):
        after = self.resolve({THUMB: (323, 430, 'jpeg'), OBJECT: OSError(), MIRROR: (1242, 1657, 'jpeg')})
        self.assertEqual(after['cover'], MIRROR)

    def test_failed_or_animated_candidates_keep_existing_cover(self):
        after = self.resolve({THUMB: (323, 430, 'jpeg'), OBJECT: ValueError(), MIRROR: ValueError()})
        self.assertEqual(after['cover'], THUMB)
        after = self.resolve({THUMB: OSError(), OBJECT: OSError(), MIRROR: OSError()})
        self.assertEqual(after['cover'], THUMB)
        self.assertEqual(after['coverQuality'], 'unverified_fallback')

    def test_other_image_and_dynamic_candidates_are_excluded(self):
        self.video['cover']['url_list'] += [OBJECT.replace('sample', 'other')]
        self.video['raw_cover'] = {'uri': 'other', 'url_list': [OBJECT.replace('sample', 'other')]}
        self.video['dynamic_cover'] = {'uri': 'tos-cn-i-dy/sample', 'url_list': [OBJECT + '&dynamic=1']}
        urls = [x['url'] for x in self.record().get('coverCandidates', [])]
        self.assertEqual(urls, [THUMB, OBJECT, MIRROR])

    def test_detail_crop_does_not_promote_different_original_scale_image(self):
        self.video['cover'] = {'uri': 'image-cut-tos-priv/crop', 'url_list': [
            'https://p3-pc-sign.douyinpic.com/image-cut-tos-priv/crop~resize.jpeg']}
        self.video['cover_original_scale'] = {'uri': 'tos-cn-i-dy/sample', 'url_list': [OBJECT]}
        self.assertNotIn(OBJECT, [c['url'] for c in self.record().get('coverCandidates', [])])

    def test_static_image_dimensions_and_animation_rejection(self):
        self.assertIsNotNone(importlib.util.find_spec('cover_quality'), 'Image probe is missing')
        from cover_quality import image_dimensions
        jpeg = b'\xff\xd8\xff\xc0\x00\x0b\x08' + struct.pack('>HH', 1657, 1242) + b'\x01\x01\x11\x00\xff\xd9'
        self.assertEqual(image_dimensions(jpeg), (1242, 1657, 'jpeg'))
        with self.assertRaises(ValueError):
            image_dimensions(b'GIF89a' + b'\x00' * 30)
        with self.assertRaises(ValueError):
            image_dimensions(b'<html>login</html>')
        with self.assertRaises(ValueError):
            image_dimensions(jpeg[:-2])
        def chunk(kind, payload):
            return struct.pack('>I', len(payload)) + kind + payload + struct.pack('>I', zlib.crc32(kind + payload))
        header = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 3, 2, 8, 2, 0, 0, 0))
        pixels = chunk(b'IDAT', zlib.compress((b'\x00' + b'\x01\x02\x03' * 3) * 2))
        tail = pixels + chunk(b'IEND', b'')
        self.assertEqual(image_dimensions(header + tail), (3, 2, 'png'))
        with self.assertRaises(ValueError):
            image_dimensions(header + chunk(b'acTL', struct.pack('>II', 2, 0)) + tail)


if __name__ == '__main__':
    unittest.main()
