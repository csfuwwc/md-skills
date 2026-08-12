import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { createRequire } from 'node:module';
import { spawnSync } from 'node:child_process';

const __filename = fileURLToPath(import.meta.url);
export const SCRIPT_DIR = path.dirname(__filename);
export const SKILL_DIR = path.dirname(SCRIPT_DIR);

export const DEFAULT_FIELDS = {
  upName: 'UP姓名列表',
  keywords: '命中关键词',
  upUrl: 'UP主链接',
  sourceVideoUrl: '来源视频链接',
  sourceVideoTitle: '来源视频标题',
  fans: '粉丝数',
  likes: '获赞数',
  plays: '播放数',
  rep1Title: '代表作1标题',
  rep1Url: '代表作1链接',
  rep2Title: '代表作2标题',
  rep2Url: '代表作2链接',
  rep3Title: '代表作3标题',
  rep3Url: '代表作3链接',
  contacts: '提供联系方式',
  scrapedAt: '抓取时间',
};

export function parseArgs(argv = process.argv.slice(2)) {
  const out = { _: [] };
  for (let i = 0; i < argv.length; i += 1) {
    const a = argv[i];
    if (!a.startsWith('--')) {
      out._.push(a);
      continue;
    }
    const eq = a.indexOf('=');
    if (eq >= 0) {
      out[a.slice(2, eq)] = a.slice(eq + 1);
      continue;
    }
    const key = a.slice(2);
    const next = argv[i + 1];
    if (!next || next.startsWith('--')) {
      out[key] = true;
    } else {
      out[key] = next;
      i += 1;
    }
  }
  return out;
}

export function boolArg(value, fallback = false) {
  if (value === undefined) return fallback;
  if (typeof value === 'boolean') return value;
  return !/^(false|0|no|off)$/i.test(String(value));
}

export function loadConfig(configPath) {
  if (!configPath) throw new Error('missing --config path');
  const abs = path.resolve(process.cwd(), configPath);
  const cfg = JSON.parse(fs.readFileSync(abs, 'utf8'));
  cfg.__path = abs;
  cfg.fields = { ...DEFAULT_FIELDS, ...(cfg.fields || {}) };
  cfg.browser = { platform: 'bilibili', cdpUrl: '', ...(cfg.browser || {}) };
  cfg.defaults = { batchSize: 50, intervalMs: 3000, maxPages: 80, ...(cfg.defaults || {}) };
  return cfg;
}

export function field(config, key) {
  return config.fields?.[key] || DEFAULT_FIELDS[key];
}

export function normalizeUpUrl(url = '') {
  const text = String(url || '').trim();
  const m = text.match(/https?:\/\/space\.bilibili\.com\/\d+/);
  return m ? m[0] : text.split('?')[0];
}

export function normalizeVideoUrl(url = '') {
  const text = String(url || '').trim();
  const m = text.match(/https?:\/\/(?:www\.)?bilibili\.com\/video\/[^/?#]+/);
  return m ? m[0] : text.split('?')[0];
}

export function bilibiliMid(url = '') {
  const m = String(url || '').match(/space\.bilibili\.com\/(\d+)/);
  return m ? m[1] : '';
}

export function nowString() {
  const parts = new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai', hour12: false,
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
  }).formatToParts(new Date()).reduce((acc, p) => ({ ...acc, [p.type]: p.value }), {});
  return `${parts.year}-${parts.month}-${parts.day} ${parts.hour}:${parts.minute}:${parts.second}`;
}

export function runJson(args, options = {}) {
  const attempts = options.attempts || 6;
  let last = '';
  for (let attempt = 1; attempt <= attempts; attempt += 1) {
    const r = spawnSync('lark-cli', args, {
      encoding: 'utf8',
      maxBuffer: options.maxBuffer || 80 * 1024 * 1024,
    });
    if (r.status === 0) return JSON.parse(r.stdout);
    last = r.stderr || r.stdout || 'lark-cli failed';
    const retryable = /800004135|limited|EOF|rate|timeout|temporarily/i.test(last);
    if (!retryable || attempt === attempts) break;
    spawnSync('sleep', [String(Math.min(20, attempt * 3))], { stdio: 'ignore' });
  }
  throw new Error(last);
}

export function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

export function requireLarkConfig(config) {
  if (!config.lark?.baseToken || !config.lark?.tableId) {
    throw new Error('config.lark.baseToken and config.lark.tableId are required for table read/write');
  }
}

export function listRecords(config, { viewId } = {}) {
  requireLarkConfig(config);
  const records = [];
  let fields = [];
  let offset = 0;
  while (true) {
    const args = ['base', '+record-list', '--as', 'user', '--base-token', config.lark.baseToken, '--table-id', config.lark.tableId, '--limit', '100', '--offset', String(offset), '--format', 'json'];
    const finalViewId = viewId;
    if (finalViewId) args.push('--view-id', finalViewId);
    const res = runJson(args);
    fields = res?.data?.fields || fields;
    const rows = res?.data?.data || [];
    const ids = res?.data?.record_id_list || [];
    for (let i = 0; i < rows.length; i += 1) records.push({ recordId: ids[i], row: rows[i] });
    if (!res?.data?.has_more) break;
    offset += 100;
  }
  return { fields, records };
}

export function rowToObject(fields, row) {
  const obj = {};
  fields.forEach((name, i) => { obj[name] = row?.[i]; });
  return obj;
}

export function tableFieldSet(config) {
  const { fields } = listRecords(config, { viewId: undefined });
  return new Set(fields);
}

export function listFields(config) {
  requireLarkConfig(config);
  const res = runJson(['base', '+field-list', '--as', 'user', '--base-token', config.lark.baseToken, '--table-id', config.lark.tableId]);
  return res?.data?.fields || [];
}

export function ensureSelectOption(config, fieldName, optionName) {
  if (!optionName) return { changed: false, reason: 'empty option' };
  const fields = listFields(config);
  const f = fields.find(x => x.name === fieldName || x.id === fieldName);
  if (!f) throw new Error(`select field not found: ${fieldName}`);
  if (f.type !== 'select') return { changed: false, reason: `${fieldName} is not select` };
  const options = Array.isArray(f.options) ? f.options : [];
  if (options.some(o => o.name === optionName)) return { changed: false, reason: 'exists' };
  const nextOptions = options
    .map(o => ({ name: o.name, hue: o.hue || 'Blue', lightness: o.lightness || 'Lighter' }))
    .concat([{ name: optionName, hue: 'Blue', lightness: 'Lighter' }]);
  runJson([
    'base', '+field-update', '--as', 'user',
    '--base-token', config.lark.baseToken,
    '--table-id', config.lark.tableId,
    '--field-id', f.id,
    '--json', JSON.stringify({ name: f.name, type: 'select', multiple: f.multiple !== false, options: nextOptions }),
  ]);
  return { changed: true, field: f.name, option: optionName };
}

export function getExistingUpMap(config) {
  const { fields, records } = listRecords(config);
  const upField = field(config, 'upUrl');
  const kwField = field(config, 'keywords');
  const map = new Map();
  for (const rec of records) {
    const obj = rowToObject(fields, rec.row);
    const key = normalizeUpUrl(obj[upField]);
    if (!key) continue;
    map.set(key, {
      recordId: rec.recordId,
      row: obj,
      keywords: Array.isArray(obj[kwField]) ? obj[kwField].map(String) : [],
    });
  }
  return { fields, records, map };
}

export function patchRecord(config, recordId, patch) {
  return runJson([
    'base', '+record-batch-update', '--as', 'user',
    '--base-token', config.lark.baseToken,
    '--table-id', config.lark.tableId,
    '--json', JSON.stringify({ record_id_list: [recordId], patch }),
  ]);
}

export function batchCreateRecords(config, fields, rows) {
  if (!rows.length) return { ok: true };
  return runJson([
    'base', '+record-batch-create', '--as', 'user',
    '--base-token', config.lark.baseToken,
    '--table-id', config.lark.tableId,
    '--json', JSON.stringify({ fields, rows }),
  ]);
}

export function unionKeywords(oldKeywords = [], keyword) {
  const all = Array.isArray(oldKeywords) ? oldKeywords.map(String).filter(Boolean) : [];
  if (keyword) all.push(String(keyword));
  return Array.from(new Set(all));
}

export function filterPatchBySchema(patch, schemaSet) {
  const out = {};
  for (const [k, v] of Object.entries(patch)) {
    if (schemaSet.has(k) && v !== undefined) out[k] = v;
  }
  return out;
}

export function assertCoreFields(config, schemaSet, keys) {
  const missing = keys.map(k => field(config, k)).filter(name => !schemaSet.has(name));
  if (missing.length) throw new Error(`target table missing required fields: ${missing.join(', ')}`);
}

export function loadPlaywright() {
  const require = createRequire(import.meta.url);
  const searchPaths = [process.cwd(), SKILL_DIR, path.join(process.env.HOME || '', '.agents')];
  const resolved = require.resolve('playwright-core', { paths: searchPaths });
  return require(resolved);
}

function probeCdp(cdpUrl) {
  const r = spawnSync('curl', ['-s', `${cdpUrl}/json/version`], { encoding: 'utf8' });
  if (r.status !== 0 || !r.stdout) return false;
  try { return Boolean(JSON.parse(r.stdout)?.webSocketDebuggerUrl); } catch { return false; }
}

export async function ensureBilibiliBrowser(config) {
  const cdpUrl = config.browser?.cdpUrl || process.env.BILIBILI_CDP_URL || process.env.BROWSER_CDP_URL || '';
  if (cdpUrl && probeCdp(cdpUrl)) return cdpUrl;

  const helperPathCandidates = [
    process.env.SOCIAL_BROWSER_PROFILES_HELPER,
    path.resolve(SKILL_DIR, '../social-browser-profiles/browser-helper.mjs'),
  ].filter(Boolean);
  const helperPath = helperPathCandidates.find(p => fs.existsSync(p));
  if (helperPath && fs.existsSync(helperPath)) {
    const helper = await import(pathToFileURL(helperPath).href);
    const info = helper.ensurePlatformBrowser('bilibili', { launchIfMissing: true, waitSeconds: 15 });
    if (info?.cdpUrl && probeCdp(info.cdpUrl)) return info.cdpUrl;
  }
  throw new Error(`Bilibili browser CDP is not available. Checked: ${cdpUrl || '(empty)'}. Set config.browser.cdpUrl or env BILIBILI_CDP_URL/BROWSER_CDP_URL, or install social-browser-profiles helper.`);
}

export function searchUrl({ keyword, sort = 'totalrank', pubtimeBegin, pubtimeEnd }) {
  const url = new URL('https://search.bilibili.com/video');
  url.searchParams.set('keyword', keyword || '');
  url.searchParams.set('from_source', 'webtop_search');
  url.searchParams.set('search_source', '5');
  if (sort && sort !== 'totalrank' && sort !== 'default') url.searchParams.set('order', sort);
  if (pubtimeBegin) url.searchParams.set('pubtime_begin_s', String(pubtimeBegin));
  if (pubtimeEnd) url.searchParams.set('pubtime_end_s', String(pubtimeEnd));
  return url.toString();
}

export function resolvePubtimeRange(args = {}) {
  if (args.pubtimeBegin || args.pubtimeEnd) {
    return {
      pubtimeBegin: args.pubtimeBegin ? Number(args.pubtimeBegin) : undefined,
      pubtimeEnd: args.pubtimeEnd ? Number(args.pubtimeEnd) : undefined,
    };
  }
  const range = String(args.pubtimeRange || '').trim().toLowerCase();
  if (!range) return {};
  const now = new Date();
  let begin = null;
  if (['recent6m', 'last6m', '6m', '半年', '最近半年'].includes(range)) {
    begin = new Date(now);
    begin.setMonth(begin.getMonth() - 6);
  } else if (['recent3m', 'last3m', '3m', '最近三个月'].includes(range)) {
    begin = new Date(now);
    begin.setMonth(begin.getMonth() - 3);
  } else if (['recent1m', 'last1m', '1m', '最近一个月'].includes(range)) {
    begin = new Date(now);
    begin.setMonth(begin.getMonth() - 1);
  }
  if (!begin) throw new Error(`unsupported --pubtimeRange: ${args.pubtimeRange}`);
  begin.setHours(0, 0, 0, 0);
  const end = new Date(now);
  end.setHours(23, 59, 59, 999);
  return {
    pubtimeBegin: Math.floor(begin.getTime() / 1000),
    pubtimeEnd: Math.floor(end.getTime() / 1000),
  };
}

export function cleanTitle(title = '') {
  let s = String(title || '').replace(/\s+/g, ' ').replace(/稍后再看/g, '').replace(/正在缓冲\.\.\./g, '').trim();
  s = s.replace(/^[0-9.万亿kK]+[0-9:]{3,}\s*/, '').trim();
  s = s.replace(/^(最新|合作)?\d+(?:\.\d+)?[万亿]?[0-9:]{2,}\s*/, '').trim();
  return s;
}
