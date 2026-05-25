#!/usr/bin/env node
import { spawnSync, execFileSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const skillDir = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const scraper = path.join(skillDir, "scripts", "scrape-xhs.mjs");
const browserHelperPath = path.join(os.homedir(), ".agents", "social-browser-profiles", "browser-helper.mjs");

async function ensurePlatformBrowserSafe(platform) {
  const mod = await import(pathToFileURL(browserHelperPath).href);
  if (typeof mod.ensurePlatformBrowser !== "function") {
    throw new Error(`browser-helper missing ensurePlatformBrowser(): ${browserHelperPath}`);
  }
  return mod.ensurePlatformBrowser(platform);
}

function parseArgs(argv) {
  const options = {
    baseToken: "",
    tableId: "",
    viewId: "",
    batchSize: 10,
    offset: 0,
    seqFrom: null,
    seqTo: null,
    browserConfirm: false,
    chromeUserDataDir: "",
    cdpUrl: "",
    newTab: false,
    workerTabName: "codex-xhs-worker",
    desktop: false,
    headed: false,
    betweenMs: 6000,
    pageWaitMs: 12000,
    maxConsecutiveFailures: 5,
    maxFailureRate: 0.4,
    dryRun: false,
  };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === "--base-token") options.baseToken = argv[++i] || "";
    else if (arg === "--table-id") options.tableId = argv[++i] || "";
    else if (arg === "--view-id") options.viewId = argv[++i] || "";
    else if (arg === "--batch-size") options.batchSize = Number(argv[++i] || 0);
    else if (arg === "--offset") options.offset = Number(argv[++i] || 0);
    else if (arg === "--seq-from") options.seqFrom = Number(argv[++i] || 0);
    else if (arg === "--seq-to") options.seqTo = Number(argv[++i] || 0);
    else if (arg === "--browser-confirm") options.browserConfirm = true;
    else if (arg === "--chrome-user-data-dir") options.chromeUserDataDir = argv[++i] || "";
    else if (arg === "--cdp-url") options.cdpUrl = argv[++i] || "";
    else if (arg === "--new-tab") options.newTab = true;
    else if (arg === "--worker-tab-name") options.workerTabName = argv[++i] || options.workerTabName;
    else if (arg === "--desktop") options.desktop = true;
    else if (arg === "--headed") options.headed = true;
    else if (arg === "--between-ms") options.betweenMs = Number(argv[++i] || 0);
    else if (arg === "--page-wait-ms") options.pageWaitMs = Number(argv[++i] || 0);
    else if (arg === "--max-consecutive-failures") options.maxConsecutiveFailures = Number(argv[++i] || 0);
    else if (arg === "--max-failure-rate") options.maxFailureRate = Number(argv[++i] || 0);
    else if (arg === "--reprocess-filled") {
      // Backward-compatible no-op. Eligibility is controlled by 抓取状态.
    }
    else if (arg === "--dry-run") options.dryRun = true;
    else if (arg === "--help" || arg === "-h") {
      printHelp();
      process.exit(0);
    } else {
      throw new Error(`unknown argument: ${arg}`);
    }
  }
  if (!options.baseToken || !options.tableId || !options.viewId) {
    printHelp();
    process.exit(1);
  }
  if (options.browserConfirm) {
    options.batchSize = Math.min(options.batchSize || 3, 5);
    options.maxConsecutiveFailures = Math.min(options.maxConsecutiveFailures || 2, 2);
  }
  return options;
}

function printHelp() {
  console.log(`Usage:
  process-lark-xhs.mjs --base-token <token> --table-id <tbl> --view-id <vew> [--batch-size 10]
  process-lark-xhs.mjs --base-token <token> --table-id <tbl> --view-id <vew> --browser-confirm --chrome-user-data-dir <dir> --batch-size 3
  process-lark-xhs.mjs --base-token <token> --table-id <tbl> --view-id <vew> --cdp-url http://127.0.0.1:9223 --new-tab --batch-size 3
  process-lark-xhs.mjs --base-token <token> --table-id <tbl> --view-id <vew> --seq-from 1 --seq-to 20 --batch-size 20

Only processes Base records whose 抓取状态 is 准备抓取 or 保持抓取. 准备抓取 writes body and engagement, then becomes 保持抓取. 保持抓取 refreshes only 点赞数/收藏数/抓取时间. Failed 小红书 rows write 抓取异常 and 抓取时间.`);
}

async function applyManagedBrowserDefaults(options) {
  if (options.dryRun) return options;
  if (options.cdpUrl || options.chromeUserDataDir) return options;
  const browser = await ensurePlatformBrowserSafe("xiaohongshu");
  options.cdpUrl = browser.cdpUrl;
  options.browserConfirm = true;
  options.newTab = true;
  options.workerTabName ||= browser.workerTabName;
  return options;
}

function isPidAlive(pid) {
  try {
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
}

function acquirePlatformLock(name) {
  const dir = "/tmp/social-scraper-locks";
  const lockPath = path.join(dir, `${name}.lock`);
  fs.mkdirSync(dir, { recursive: true });
  try {
    const fd = fs.openSync(lockPath, "wx");
    fs.writeFileSync(fd, JSON.stringify({
      pid: process.pid,
      startedAt: new Date().toISOString(),
      cwd: process.cwd(),
    }, null, 2));
    fs.closeSync(fd);
    return () => {
      try {
        const current = JSON.parse(fs.readFileSync(lockPath, "utf8"));
        if (current.pid === process.pid) fs.unlinkSync(lockPath);
      } catch {
        // Best-effort cleanup only.
      }
    };
  } catch (error) {
    if (error.code !== "EEXIST") throw error;
    let detail = "";
    try {
      const current = JSON.parse(fs.readFileSync(lockPath, "utf8"));
      const alive = Number.isInteger(current.pid) && isPidAlive(current.pid);
      detail = ` pid=${current.pid || "unknown"} alive=${alive} startedAt=${current.startedAt || "unknown"}`;
    } catch {
      detail = " unreadable lock";
    }
    throw new Error(`xiaohongshu platform lock is held:${detail}. Stop the other Xiaohongshu job before starting a new one. Lock: ${lockPath}`);
  }
}

function runJson(command, args, input) {
  const result = spawnSync(command, args, {
    input,
    encoding: "utf8",
    maxBuffer: 1024 * 1024 * 20,
  });
  if (result.status !== 0) throw new Error(result.stderr || result.stdout);
  return JSON.parse(result.stdout);
}

function run(command, args) {
  const result = spawnSync(command, args, {
    encoding: "utf8",
    maxBuffer: 1024 * 1024 * 20,
  });
  if (result.status !== 0) throw new Error(result.stderr || result.stdout);
  return result.stdout;
}

function nowForLark() {
  return run("date", ["+%Y-%m-%d %H:%M:00"]).trim();
}

function extractUrl(value) {
  const text = String(value || "").replace(/&amp;/g, "&");
  const markdown = text.match(/\((https?:\/\/[^)\s]+)[^)]*\)/);
  if (markdown) return markdown[1];
  const raw = text.match(/https?:\/\/\S+/);
  return raw ? raw[0].replace(/[)\],，。]+$/, "") : "";
}

function isXhsUrl(url) {
  return /(?:xiaohongshu\.com|xhslink\.com|xhs\.cn)/i.test(String(url || ""));
}

function normalizeStatus(status) {
  if (status == null) return "准备抓取";
  const text = String(status).trim();
  return text || "准备抓取";
}

function listRecordsPage(options, offset) {
  return runJson("lark-cli", [
    "base",
    "+record-list",
    "--base-token",
    options.baseToken,
    "--table-id",
    options.tableId,
    "--view-id",
    options.viewId,
    "--offset",
    String(offset),
    "--limit",
    "200",
    "--as",
    "user",
    "--field-id",
    "序号",
    "--field-id",
    "平台",
    "--field-id",
    "发布链接",
    "--field-id",
    "列7",
    "--field-id",
    "正文",
    "--field-id",
    "点赞数",
    "--field-id",
    "收藏数",
    "--field-id",
    "抓取时间",
    "--field-id",
    "抓取状态",
  ]).data;
}

function recordsToCandidates(records, options) {
  const rows = records.data || [];
  const ids = records.record_id_list || [];
  const fields = records.fields || [];
  const cellValue = (cells, name) => {
    const index = fields.indexOf(name);
    return index >= 0 ? cells[index] : undefined;
  };
  return rows
    .map((cells, index) => {
      const kind = cellValue(cells, "列7");
      const status = cellValue(cells, "抓取状态");
      return {
        recordId: ids[index],
        seq: cellValue(cells, "序号"),
        platform: Array.isArray(cellValue(cells, "平台")) ? cellValue(cells, "平台")[0] : cellValue(cells, "平台"),
        url: extractUrl(cellValue(cells, "发布链接")),
        kind: Array.isArray(kind) ? kind[0] : kind,
        body: cellValue(cells, "正文"),
        status: Array.isArray(status) ? status[0] : status,
      };
    })
    .map((row) => ({
      ...row,
      normalizedStatus: normalizeStatus(row.status),
    }))
    .filter((row) => row.seq != null && row.url)
    .filter((row) => row.platform === "小红书" || (!row.platform && isXhsUrl(row.url)))
    .filter((row) => options.seqFrom == null || Number(row.seq) >= options.seqFrom)
    .filter((row) => options.seqTo == null || Number(row.seq) <= options.seqTo)
    .filter((row) => ["准备抓取", "保持抓取"].includes(row.normalizedStatus));
}

function readCandidates(options) {
  const candidates = [];
  let offset = options.offset;
  while (candidates.length < options.batchSize) {
    const records = listRecordsPage(options, offset);
    candidates.push(...recordsToCandidates(records, options));
    const pageSize = (records.data || []).length;
    const hasMore = Boolean(records.has_more);
    if (!hasMore || pageSize === 0) break;
    offset += pageSize;
    if (options.seqTo != null && candidates.some((row) => Number(row.seq) >= options.seqTo)) break;
  }
  return candidates.slice(0, options.batchSize);
}

function successPayload(row, result) {
  const payload = {
    ...(Number.isFinite(result.likedCount) ? { 点赞数: result.likedCount } : {}),
    ...(Number.isFinite(result.collectedCount) ? { 收藏数: result.collectedCount } : {}),
    抓取时间: nowForLark(),
  };

  if (row.normalizedStatus === "准备抓取") {
    payload.正文 = result.body;
    payload.抓取状态 = "保持抓取";
  }

  return payload;
}

function failurePayload() {
  return {
    抓取状态: "抓取异常",
    抓取时间: nowForLark(),
  };
}

function scrape(rows, options, useBrowser) {
  const args = [scraper, "--json", "--between-ms", String(options.betweenMs), "--page-wait-ms", String(options.pageWaitMs)];
  if (useBrowser) {
    args.push("--browser", "--stop-after-consecutive-failures", String(options.maxConsecutiveFailures));
    if (options.chromeUserDataDir) args.push("--chrome-user-data-dir", options.chromeUserDataDir);
    if (options.cdpUrl) args.push("--cdp-url", options.cdpUrl);
    if (options.newTab) args.push("--new-tab");
    if (options.workerTabName) args.push("--worker-tab-name", options.workerTabName);
    if (options.desktop) args.push("--desktop");
    if (options.headed) args.push("--headed");
  }

  const result = spawnSync("node", args, {
    input: `${rows.map((row) => row.url).join("\n")}\n`,
    encoding: "utf8",
    maxBuffer: 1024 * 1024 * 20,
  });
  if (result.status !== 0) throw new Error(result.stderr || result.stdout);
  return result.stdout
    .split(/\r?\n/)
    .filter(Boolean)
    .map((line) => JSON.parse(line));
}

function isTerminalFailure(result) {
  const error = String(result?.error || "");
  return /当前内容无法展示|App内打开|404|login|登录|no note state|stopped after/i.test(error);
}

function updateRecord(options, row, payload) {
  if (options.dryRun) return;
  execFileSync("lark-cli", [
    "base",
    "+record-upsert",
    "--base-token",
    options.baseToken,
    "--table-id",
    options.tableId,
    "--record-id",
    row.recordId,
    "--json",
    JSON.stringify(payload),
    "--as",
    "user",
  ], { stdio: "ignore" });
}

const options = await applyManagedBrowserDefaults(parseArgs(process.argv.slice(2)));
const rows = readCandidates(options);
const summary = {
  candidates: rows.length,
  success: [],
  terminated: [],
  retained: [],
  stopped: false,
  dryRun: options.dryRun,
};

if (!rows.length) {
  console.log(JSON.stringify(summary, null, 2));
  process.exit(0);
}

if (options.dryRun) {
  summary.candidateSeqs = rows.map((row) => ({ seq: row.seq, status: row.status }));
  console.log(JSON.stringify(summary, null, 2));
  process.exit(0);
}

const releaseLock = acquirePlatformLock("xiaohongshu");
try {
  const staticResults = scrape(rows, options, false);
  let failures = 0;
  let consecutiveFailures = 0;
  const browserRows = [];

  for (let index = 0; index < rows.length; index += 1) {
    const row = rows[index];
    const result = staticResults[index];
    if (result?.ok) {
      updateRecord(options, row, successPayload(row, result));
      summary.success.push(row.seq);
      consecutiveFailures = 0;
    } else {
      failures += 1;
      consecutiveFailures += 1;
      if (options.browserConfirm) browserRows.push(row);
      else {
        const error = result?.error || "unknown error";
        updateRecord(options, row, failurePayload());
        summary.terminated.push({ seq: row.seq, error });
      }
    }

    if (!options.browserConfirm && (
      consecutiveFailures >= options.maxConsecutiveFailures ||
      failures / rows.length > options.maxFailureRate
    )) {
      summary.stopped = true;
      break;
    }
  }

  if (options.browserConfirm && !summary.stopped && browserRows.length) {
    const browserResults = scrape(browserRows, options, true);
    let browserConsecutiveFailures = 0;
    for (let index = 0; index < browserRows.length; index += 1) {
      const row = browserRows[index];
      const result = browserResults[index];
      if (result?.ok) {
        updateRecord(options, row, successPayload(row, result));
        summary.success.push(row.seq);
        browserConsecutiveFailures = 0;
      } else {
        browserConsecutiveFailures += 1;
        const error = result?.error || "unknown error";
        updateRecord(options, row, failurePayload());
        summary.terminated.push({ seq: row.seq, error });
        if (browserConsecutiveFailures >= options.maxConsecutiveFailures) {
          summary.stopped = true;
          break;
        }
      }
    }
  }
} finally {
  releaseLock();
}

console.log(JSON.stringify(summary, null, 2));
