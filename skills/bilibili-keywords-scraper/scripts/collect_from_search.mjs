#!/usr/bin/env node
import {
  parseArgs, boolArg, loadConfig, field, nowString, normalizeUpUrl, normalizeVideoUrl,
  ensureBilibiliBrowser, loadPlaywright, searchUrl, getExistingUpMap, tableFieldSet,
  assertCoreFields, filterPatchBySchema, patchRecord, batchCreateRecords, unionKeywords,
  resolvePubtimeRange, ensureSelectOption, sleep,
} from './bili_up_common.mjs';

const args = parseArgs();
const config = loadConfig(args.config);
const keyword = args.keyword || config.search?.keyword;
const sort = args.sort || config.search?.sort || 'totalrank';
const mode = args.mode || config.search?.mode || 'current';
const execute = boolArg(args.execute, false);
const maxPages = args.pages === 'all' ? Number(config.defaults.maxPages || 80) : Number(args.pages || 1);
const pubtime = resolvePubtimeRange(args);

if (!keyword) throw new Error('missing --keyword');

const schemaSet = execute ? tableFieldSet(config) : new Set(Object.values(config.fields || {}));
if (execute) assertCoreFields(config, schemaSet, ['upName', 'upUrl', 'keywords']);
if (execute) ensureSelectOption(config, field(config, 'keywords'), keyword);

const cdpUrl = await ensureBilibiliBrowser(config);
const { chromium } = loadPlaywright();
const browser = await chromium.connectOverCDP(cdpUrl);
const ctx = browser.contexts()[0] || await browser.newContext();
let page = ctx.pages().find(p => p.url().includes('search.bilibili.com')) || ctx.pages()[0] || await ctx.newPage();
await page.bringToFront();

if (mode === 'navigate') {
  await page.goto(searchUrl({ keyword, sort, ...pubtime }), { waitUntil: 'domcontentloaded', timeout: 90000 });
} else if (!page.url().includes('search.bilibili.com')) {
  throw new Error('current page is not a Bilibili search page; use --mode navigate or open a filtered search page first');
}

const all = new Map();
const visited = new Set();
let scannedPages = 0;

while (scannedPages < maxPages) {
  scannedPages += 1;
  await page.waitForTimeout(1400);

  const cur = await page.evaluate(() => {
    const cards = Array.from(document.querySelectorAll('.bili-video-card, .video-list .video-item, [class*="video-card"]'));
    const rows = [];
    for (const c of cards) {
      const titleEl = c.querySelector('.bili-video-card__info--tit, [class*="info--tit"], h3[title], h3');
      const titleLink =
        titleEl?.closest?.('a[href*="/video/"]') ||
        Array.from(c.querySelectorAll('a[href*="/video/"]')).find(a => (a.textContent || '').replace(/\s+/g, ' ').trim().length >= 6);
      const v = titleLink || c.querySelector('a[href*="/video/"]');
      const u = c.querySelector('a[href*="space.bilibili.com"]');
      if (!v || !u) continue;
      const upText = (u.textContent || '').trim().replace(/\s+/g, ' ');
      const title = (
        titleEl?.getAttribute('title') ||
        titleEl?.textContent ||
        v.getAttribute('title') ||
        v.textContent ||
        ''
      ).trim().replace(/\s+/g, ' ');
      rows.push({
        upName: upText.split('·')[0].trim(),
        upUrl: u.href,
        sourceVideoUrl: v.href,
        sourceVideoTitle: title.slice(0, 200),
      });
    }
    const active = document.querySelector('.vui_pagenation--active, .pagination .active, [class*="active"][class*="page"]')?.textContent?.trim() || '';
    const nextBtn = Array.from(document.querySelectorAll('button,a,span,div')).find(el => (el.textContent || '').trim() === '下一页');
    const disabled = nextBtn ? (nextBtn.getAttribute('disabled') !== null || /disabled|is-disabled|vui_button--disabled/.test(nextBtn.className || '')) : true;
    return { rows, active, disabled };
  });

  const sig = `${cur.active}|${cur.rows.slice(0, 4).map(r => r.sourceVideoUrl).join('|')}`;
  if (visited.has(sig)) break;
  visited.add(sig);

  for (const row of cur.rows) {
    const upUrl = normalizeUpUrl(row.upUrl);
    if (!upUrl) continue;
    if (!all.has(upUrl)) {
      all.set(upUrl, {
        ...row,
        upUrl,
        sourceVideoUrl: normalizeVideoUrl(row.sourceVideoUrl),
        keyword,
        scrapedAt: nowString(),
      });
    }
  }

  if (cur.disabled || scannedPages >= maxPages) break;
  const clicked = await page.evaluate(() => {
    const nextBtn = Array.from(document.querySelectorAll('button,a,span,div')).find(el => (el.textContent || '').trim() === '下一页');
    if (!nextBtn) return false;
    nextBtn.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
    return true;
  });
  if (!clicked) break;
  await page.waitForTimeout(1800);
}

await browser.close();

const candidates = [...all.values()];
let created = 0;
let updatedKeywords = 0;
let skippedExisting = 0;
const samples = candidates.slice(0, 20);

if (execute) {
  const existing = getExistingUpMap(config).map;
  const toCreate = [];
  const createFields = [
    field(config, 'upName'), field(config, 'keywords'), field(config, 'upUrl'),
    field(config, 'sourceVideoUrl'), field(config, 'sourceVideoTitle'), field(config, 'scrapedAt'),
  ].filter((name, i, arr) => name && schemaSet.has(name) && arr.indexOf(name) === i);

  for (const c of candidates) {
    const old = existing.get(c.upUrl);
    if (old) {
      const nextKeywords = unionKeywords(old.keywords, keyword);
      if (nextKeywords.length !== old.keywords.length) {
        const patch = filterPatchBySchema({ [field(config, 'keywords')]: nextKeywords }, schemaSet);
        patchRecord(config, old.recordId, patch);
        updatedKeywords += 1;
        await sleep(500);
      } else {
        skippedExisting += 1;
      }
      continue;
    }
    const obj = {
      [field(config, 'upName')]: c.upName,
      [field(config, 'keywords')]: [keyword],
      [field(config, 'upUrl')]: c.upUrl,
      [field(config, 'sourceVideoUrl')]: c.sourceVideoUrl,
      [field(config, 'sourceVideoTitle')]: c.sourceVideoTitle,
      [field(config, 'scrapedAt')]: c.scrapedAt,
    };
    toCreate.push(createFields.map(name => obj[name] ?? null));
  }

  for (let i = 0; i < toCreate.length; i += 100) {
    const chunk = toCreate.slice(i, i + 100);
    batchCreateRecords(config, createFields, chunk);
    created += chunk.length;
  }
}

console.log(JSON.stringify({
  ok: true,
  execute,
  mode,
  keyword,
  sort,
  pubtime,
  scannedPages,
  uniqueUps: candidates.length,
  created,
  updatedKeywords,
  skippedExisting,
  sample: samples,
}, null, 2));
