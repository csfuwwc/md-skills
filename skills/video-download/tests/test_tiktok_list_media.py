import importlib.util
import json
from pathlib import Path
from unittest import TestCase, mock


PATH = Path(__file__).parents[1] / 'scripts' / 'download.py'
spec = importlib.util.spec_from_file_location('video_download_tiktok_list', PATH)
dl = importlib.util.module_from_spec(spec); spec.loader.exec_module(dl)


class TikTokListMediaTests(TestCase):
    def test_list_record_is_preferred_and_bound_to_video_and_author(self):
        record = {'id': '123', 'type': 'video', 'authorHandle': 'account',
                  'dataSource': 'profile_item_list_api',
                  'video': {'playAddr': 'https://cdn/video.mp4', 'duration': 12}}
        with mock.patch('builtins.open', mock.mock_open(read_data=json.dumps(record))), \
             mock.patch.object(dl, 'download_tiktok_media_with_cdp', return_value=10), \
             mock.patch.object(dl, 'validate_video_file'), \
             mock.patch.object(dl, 'get_media_duration_seconds', return_value=12), \
             mock.patch.object(dl, 'output_dir', return_value='/tmp'), \
             mock.patch.object(dl, 'write_tiktok_meta') as meta, \
             mock.patch.dict(dl.os.environ, {'VIDEO_DOWNLOAD_TIKTOK_LIST_RECORD': 'record.json',
                                              'VIDEO_DOWNLOAD_TIKTOK_AUTHOR_HANDLE': 'account'}):
            self.assertEqual(dl.download_tiktok('https://www.tiktok.com/@account/video/123', 'x.mp4'),
                             '/tmp/x.mp4')
        self.assertEqual(meta.call_args.kwargs['source'], 'profile_item_list_api')

    def test_list_only_never_enters_detail_page(self):
        with mock.patch.object(dl, 'download_tiktok_list', side_effect=RuntimeError('expired')), \
             mock.patch.object(dl, 'download_tiktok_cdp') as detail, \
             mock.patch.dict(dl.os.environ, {'VIDEO_DOWNLOAD_TIKTOK_LIST_RECORD': 'record.json',
                                              'VIDEO_DOWNLOAD_TIKTOK_LIST_ONLY': '1'}):
            with self.assertRaisesRegex(RuntimeError, '禁止.*详情页'):
                dl.download_tiktok('https://www.tiktok.com/@account/video/123')
        detail.assert_not_called()
