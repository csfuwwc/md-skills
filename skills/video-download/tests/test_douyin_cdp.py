import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('dl',Path(__file__).parents[1]/'scripts/download.py')
dl=importlib.util.module_from_spec(spec);spec.loader.exec_module(dl)
class CDPTests(unittest.TestCase):
 def test_explicit_cdp_never_falls_back(self):
  with patch.dict(dl.os.environ,{'VIDEO_DOWNLOAD_DOUYIN_CDP_ENDPOINT':'http://127.0.0.1:9222'}),patch.object(dl,'download_douyin_cdp',side_effect=RuntimeError('unavailable'),create=True),patch.object(dl,'launch_browser_and_capture') as legacy:
   with self.assertRaises(RuntimeError):dl.download_douyin('https://www.douyin.com/video/123')
   legacy.assert_not_called()
 def test_wrong_id_rejected(self):
  with self.assertRaises(RuntimeError):dl.douyin_cdp_metadata({'aweme_id':'456'},'123','author')
 def test_wrong_author_rejected(self):
  with self.assertRaises(RuntimeError):dl.douyin_cdp_metadata({'aweme_id':'123','author':{'sec_uid':'wrong'}},'123','author')
 def test_metadata_binds_media_to_target(self):
  r=dl.douyin_cdp_metadata({'aweme_id':'123','author':{'sec_uid':'author','nickname':'name'},'video':{'duration':21000,'play_addr':{'url_list':['https://example.com/video']}}},'123','author')
  self.assertEqual(r['duration'],21);self.assertEqual(r['url'],'https://example.com/video')

class QualityTests(unittest.TestCase):
 def test_720_default_with_all_alternatives_retained(self):
  tiers=[{'bit_rate':b,'play_addr':{'width':w,'height':h,'url_list':['https://example.com/'+str(w)]}} for w,h,b in [(1080,1920,3000000),(720,1280,2000000),(576,1024,1000000)]]
  r=dl.douyin_cdp_metadata({'aweme_id':'1','author':{'sec_uid':'a'},'video':{'duration':1000,'bit_rate':tiers}},'1','a')
  self.assertEqual(r['selected_quality']['width'],720)
  self.assertEqual(len(r['video_candidates']),3)

class ListDownloadTests(unittest.TestCase):
 def test_list_success_does_not_open_detail(self):
  with patch.dict(dl.os.environ,{'VIDEO_DOWNLOAD_DOUYIN_CDP_ENDPOINT':'http://127.0.0.1:9222','VIDEO_DOWNLOAD_DOUYIN_LIST_RECORD':'source.json'}),patch.object(dl,'download_douyin_list',return_value='video.mp4') as direct,patch.object(dl,'download_douyin_cdp') as detail:
   self.assertEqual(dl.download_douyin('https://www.douyin.com/video/123'),'video.mp4')
   detail.assert_not_called()
 def test_expired_list_falls_back_to_same_detail_endpoint(self):
  with patch.dict(dl.os.environ,{'VIDEO_DOWNLOAD_DOUYIN_CDP_ENDPOINT':'http://127.0.0.1:9222','VIDEO_DOWNLOAD_DOUYIN_LIST_RECORD':'source.json'}),patch.object(dl,'download_douyin_list',side_effect=RuntimeError('expired')),patch.object(dl,'download_douyin_cdp',return_value='video.mp4') as detail:
   dl.download_douyin('https://www.douyin.com/video/123')
   detail.assert_called_once_with('https://www.douyin.com/video/123',None,'http://127.0.0.1:9222')

if __name__ == "__main__":
 unittest.main()
