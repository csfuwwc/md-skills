#!/usr/bin/env node
import {
  parseArgs, boolArg, loadConfig, field, nowString, normalizeUpUrl, cleanTitle,
  ensureBilibiliBrowser, loadPlaywright, listRecords, rowToObject, tableFieldSet,
  filterPatchBySchema, patchRecord, unionKeywords,
} from './bili_up_common.mjs';

const args = parseArgs();
const config = loadConfig(args.config);
const keyword = args.keyword || config.search?.keyword || '';
const execute = boolArg(args.execute, false);
const limit = Number(args.limit || config.defaults.batchSize || 50);
const intervalMs = Number(args.intervalMs || config.defaults.intervalMs || 3000);
const schemaSet = execute ? tableFieldSet(config) : new Set(Object.values(config.fields || {}));

function isReady(obj) {
  return Boolean(obj[field(config, 'fans')] && obj[field(config, 'likes')] && obj[field(config, 'plays')] && obj[field(config, 'rep1Title')] && obj[field(config, 'rep1Url')]);
}

function loadPending() {
  const { fields, records } = listRecords(config);
  const out = [];
  const skipUrls = new Set((config.skipUpUrls || []).map(normalizeUpUrl));
  for (const rec of records) {
    const obj = rowToObject(fields, rec.row);
    const kws = Array.isArray(obj[field(config, 'keywords')]) ? obj[field(config, 'keywords')].map(String) : [];
    const kwOk = !keyword || kws.includes(keyword);
    const upUrl = normalizeUpUrl(obj[field(config, 'upUrl')]);
    const name = String(obj[field(config, 'upName')] || '');
    if (skipUrls.has(upUrl)) continue;
    const deletedDone = /账号已注销/.test(name) && kwOk;
    if (upUrl && kwOk && !isReady(obj) && !deletedDone) {
      out.push({ recordId: rec.recordId, obj, upUrl, upName: name, oldKeywords: kws });
    }
    if (out.length >= limit) break;
  }
  return out;
}

function sleep(ms) { return new Promise(resolve => setTimeout(resolve, ms)); }

const pending = loadPending();
const cdpUrl = await ensureBilibiliBrowser(config);
const { chromium } = loadPlaywright();
const browser = await chromium.connectOverCDP(cdpUrl);
const ctx = browser.contexts()[0] || await browser.newContext();

const ok = [];
const fail = [];
let stoppedByCaptcha = false;
let captchaPageKeptOpen = false;

for (const item of pending) {
  const p = await ctx.newPage();
  try {
    await p.goto(item.upUrl, { waitUntil: 'domcontentloaded', timeout: 90000 });
    await p.waitForTimeout(2600);

    const captcha = await p.evaluate(() => {
      const text = el => (el?.innerText || el?.textContent || '').replace(/\s+/g, ' ').trim();
      const overlays = Array.from(document.querySelectorAll('[class*="captcha" i], [class*="geetest" i], [id*="captcha" i], [id*="geetest" i], .bili-mini-mask, [class*="modal" i], [class*="dialog" i]'));
      for (const overlay of overlays) {
        const overlayText = text(overlay).slice(0, 1200);
        const cls = String(overlay.className || '') + ' ' + String(overlay.id || '');
        const orderedClick = /按顺序点击|依次点击|点击.*文字|请按顺序/.test(overlayText);
        const confirm = /确定|确认|提交|完成|下一步/.test(overlayText);
        const vendor = /geetest|captcha|验证码|人机验证|安全验证/i.test(cls + ' ' + overlayText);
        if (vendor || (orderedClick && confirm)) return { hit: true, text: overlayText.slice(0, 400) };
      }
      return { hit: false, text: '' };
    });

    if (captcha.hit) {
      stoppedByCaptcha = true;
      captchaPageKeptOpen = true;
      fail.push({ recordId: item.recordId, upName: item.upName, upUrl: item.upUrl, reason: 'captcha_detected', captchaText: captcha.text });
      break;
    }

    const data = await p.evaluate(() => {
      const body = (document.body?.innerText || '').replace(/\s+/g, ' ');
      const pick = re => {
        const m = body.match(new RegExp('(?:' + re + ')\\s*([0-9]+(?:\\.[0-9]+)?[万亿]?)'));
        return m ? m[1] : '';
      };
      const email = (body.match(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/ig) || [])[0] || '';
      const wx = (body.match(/(?:微信|vx|VX|v信|商务微信)[:：\s]*([a-zA-Z][a-zA-Z0-9_-]{4,})/) || [])[1] || '';
      const qq = (body.match(/(?:QQ|qq)[:：\s]*([1-9][0-9]{4,11})/) || [])[1] || '';

      const cards = Array.from(document.querySelectorAll('.bili-video-card, li.small-item, .small-item, .video-card, [class*="video-card"]'));
      const reps = [];
      const seen = new Set();
      for (const c of cards) {
        const a = c.querySelector('a[href*="/video/"]');
        if (!a) continue;
        const url = (a.href || '').split('?')[0];
        if (!url || seen.has(url)) continue;
        seen.add(url);
        const texts = Array.from(c.querySelectorAll('a,div,span')).map(e => (e.textContent || '').replace(/\s+/g, ' ').trim()).filter(Boolean);
        let title = a.getAttribute('title') || '';
        for (const t of texts) {
          if (t.length < 8) continue;
          if (/^(最新发布|最多播放|最多收藏|投稿|播放全部|查看更多)$/.test(t)) continue;
          title = t;
          break;
        }
        reps.push({ title: title.trim(), url });
        if (reps.length >= 3) break;
      }
      return {
        fans: pick('粉丝数|粉丝'),
        likes: pick('获赞数|获赞'),
        plays: pick('播放数|播放'),
        email, wx, qq, reps,
      };
    });

    const reps = (data.reps || []).map(r => ({ title: cleanTitle(r.title), url: r.url }));
    const contacts = [];
    if (data.email) contacts.push(`邮箱: ${data.email}`);
    if (data.wx) contacts.push(`微信/VX: ${data.wx}`);
    if (data.qq) contacts.push(`QQ: ${data.qq}`);

    const patch = filterPatchBySchema({
      [field(config, 'fans')]: data.fans || null,
      [field(config, 'likes')]: data.likes || null,
      [field(config, 'plays')]: data.plays || null,
      [field(config, 'rep1Title')]: reps[0]?.title || null,
      [field(config, 'rep1Url')]: reps[0]?.url || null,
      [field(config, 'rep2Title')]: reps[1]?.title || null,
      [field(config, 'rep2Url')]: reps[1]?.url || null,
      [field(config, 'rep3Title')]: reps[2]?.title || null,
      [field(config, 'rep3Url')]: reps[2]?.url || null,
      [field(config, 'contacts')]: contacts.join(' | ') || null,
      [field(config, 'scrapedAt')]: nowString(),
      [field(config, 'keywords')]: keyword ? unionKeywords(item.oldKeywords, keyword) : item.oldKeywords,
    }, schemaSet);

    if (execute) patchRecord(config, item.recordId, patch);
    ok.push({ recordId: item.recordId, upName: item.upName, upUrl: item.upUrl, fans: data.fans || null, reps: reps.slice(0, 3) });
  } catch (e) {
    fail.push({ recordId: item.recordId, upName: item.upName, upUrl: item.upUrl, reason: String(e.message || e).slice(0, 300) });
  } finally {
    if (!(stoppedByCaptcha && captchaPageKeptOpen)) await p.close().catch(() => {});
  }
  await sleep(intervalMs);
}

if (!stoppedByCaptcha) await browser.close().catch(() => {});

console.log(JSON.stringify({
  ok: true,
  execute,
  requested: limit,
  intervalMs,
  pendingLoaded: pending.length,
  processed: ok.length + fail.length,
  success: ok.length,
  failed: fail.length,
  stoppedByCaptcha,
  captchaPageKeptOpen,
  sample: ok.slice(0, 10),
  fail,
}, null, 2));
