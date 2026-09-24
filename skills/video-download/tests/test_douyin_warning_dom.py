"""Local HTML fixtures only; no Douyin requests or user browser profile."""
import ast
import os
from pathlib import Path
import unittest
from playwright.sync_api import sync_playwright

class WarningDOMTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.pw=sync_playwright().start()
  cls.browser=cls.pw.chromium.launch(headless=True, channel=os.getenv("PLAYWRIGHT_TEST_CHANNEL") or None)
  cls.page=cls.browser.new_page()
  root=Path(__file__).resolve().parents[2]
  cls.scripts=[]
  for path in [root/'video-download/scripts/download.py',root/'douyin-scraper/scripts/scrape-profile.py']:
   tree=ast.parse(path.read_text())
   cls.scripts.append(next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='PLATFORM_WARNING_SCRIPT' for t in n.targets)))
 @classmethod
 def tearDownClass(cls):
  cls.browser.close();cls.pw.stop()
 def check(self,html,expected):
  self.page.set_content(html)
  for script in self.scripts:self.assertEqual(bool(self.page.evaluate(script)),expected)
 def test_caption_keyword_is_not_a_challenge(self):
  self.check('<div>热门：查询成绩时一遍遍的重新输入验证码，看到成绩心里反复确认</div>',False)
 def test_hidden_challenge_is_not_active(self):
  self.check('<div id="captcha_container" style="display:none">安全验证</div>',False)
 def test_visible_dialog_is_detected(self):
  self.check('<div role="dialog"><h2>安全验证</h2></div>',True)
 def test_slider_instruction_is_detected(self):
  self.check('<div>请拖动滑块完成拼图</div>',True)
 def test_visible_challenge_container_is_detected(self):
  self.check('<div id="captcha_container" style="width:200px;height:80px"></div>',True)

if __name__=='__main__':unittest.main()
