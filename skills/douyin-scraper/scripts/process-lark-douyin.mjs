#!/usr/bin/env node
import { spawn, spawnSync, execFileSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const skillDir = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const scraper = path.join(skillDir, "scripts", "scrape-douyin.py");
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
    chromeExecutablePath: "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    cdpUrl: "",
    cdpOnly: false,
    newTab: false,
    workerTabName: "codex-douyin-worker",
    comment: false,
    noVideoAnalysis: false,
    headed: false,
    betweenMs: 6000,
    pageWaitMs: 12000,
    maxConsecutiveFailures: 5,
    maxFailureRate: 0.4,
    dryRun: false,
    workDir: "/tmp/douyin-scraper",
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
    else if (arg === "--chrome-executable-path") options.chromeExecutablePath = argv[++i] || "";
    else if (arg === "--cdp-url") options.cdpUrl = argv[++i] || "";
    else if (arg === "--cdp-only") options.cdpOnly = true;
    else if (arg === "--new-tab") options.newTab = true;
    else if (arg === "--worker-tab-name") options.workerTabName = argv[++i] || options.workerTabName;
    else if (arg === "--comment") options.comment = true;
    else if (arg === "--no-video-analysis") options.noVideoAnalysis = true;
    else if (arg === "--headed") options.headed = true;
    else if (arg === "--between-ms") options.betweenMs = Number(argv[++i] || 0);
    else if (arg === "--page-wait-ms") options.pageWaitMs = Number(argv[++i] || 0);
    else if (arg === "--max-consecutive-failures") options.maxConsecutiveFailures = Number(argv[++i] || 0);
    else if (arg === "--max-failure-rate") options.maxFailureRate = Number(argv[++i] || 0);
    else if (arg === "--work-dir") options.workDir = argv[++i] || options.workDir;
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
  process-lark-douyin.mjs --base-token <token> --table-id <tbl> --view-id <vew> [--batch-size 10]
  process-lark-douyin.mjs --base-token <token> --table-id <tbl> --view-id <vew> --browser-confirm --chrome-user-data-dir <dir> --batch-size 3
  process-lark-douyin.mjs --base-token <token> --table-id <tbl> --view-id <vew> --cdp-url 'http://[::1]:9222' --cdp-only --batch-size 3
  process-lark-douyin.mjs --base-token <token> --table-id <tbl> --view-id <vew> --seq-from 414 --seq-to 420 --cdp-url 'http://[::1]:9222' --cdp-only --new-tab
  process-lark-douyin.mjs --base-token <token> --table-id <tbl> --view-id <vew> --cdp-url 'http://[::1]:9222' --cdp-only --new-tab --comment

Processes 抖音 rows whose 抓取状态 is blank, 准备抓取, or 保持抓取. 准备抓取 writes body and engagement, then becomes 保持抓取. 保持抓取 refreshes only 点赞数/收藏数/抓取时间. Confirmed terminal failure writes 抓取异常.`);
}

async function applyManagedBrowserDefaults(options) {
  if (options.dryRun) return options;
  if (options.cdpUrl || options.chromeUserDataDir) return options;
  const browser = await ensurePlatformBrowserSafe("douyin");
  options.cdpUrl = browser.cdpUrl;
  options.cdpOnly = true;
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
    throw new Error(`douyin platform lock is held:${detail}. Stop the other Douyin job before starting a new one. Lock: ${lockPath}`);
  }
}

function runJson(command, args, input) {
  let lastError = "";
  for (let attempt = 1; attempt <= 3; attempt += 1) {
    const result = spawnSync(command, args, {
      input,
      encoding: "utf8",
      maxBuffer: 1024 * 1024 * 20,
    });
    if (result.status === 0) return JSON.parse(result.stdout);
    lastError = result.stderr || result.stdout;
    if (!/EOF|timeout|temporar/i.test(lastError) || attempt === 3) break;
    spawnSync("sleep", [String(attempt)]);
  }
  throw new Error(lastError);
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

function singleSelect(value) {
  return Array.isArray(value) ? value[0] : value;
}

function normalizeStatus(value) {
  return singleSelect(value) || "准备抓取";
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
    "帖子链接(完整)",
    "--field-id",
    "note_id",
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
    "评论数",
    "--field-id",
    "发布时间",
    "--field-id",
    "标题",
    "--field-id",
    "关键词",
    "--field-id",
    "是否符合要求",
    "--field-id",
    "命中词",
    "--field-id",
    "抓取时间",
    "--field-id",
    "抓取状态",
    "--field-id",
    "生成评论",
    "--field-id",
    "评论状态",
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
      const status = normalizeStatus(cellValue(cells, "抓取状态"));
      const kind = singleSelect(cellValue(cells, "列7"));
      const seqValue = cellValue(cells, "序号") ?? cellValue(cells, "note_id") ?? index + 1;
      const publishLink = cellValue(cells, "发布链接");
      const fullLink = cellValue(cells, "帖子链接(完整)");
      const platform = singleSelect(cellValue(cells, "平台")) || "抖音";
      return {
        recordId: ids[index],
        seq: seqValue,
        platform,
        url: extractUrl(publishLink || fullLink),
        kind,
        status,
        generatedComment: cellValue(cells, "生成评论"),
        commentStatus: singleSelect(cellValue(cells, "评论状态")),
      };
    })
    .filter((row) => row.seq != null && row.url && row.platform === "抖音")
    .filter((row) => options.seqFrom == null || Number(row.seq) >= options.seqFrom)
    .filter((row) => options.seqTo == null || Number(row.seq) <= options.seqTo)
    .filter((row) => ["准备抓取", "保持抓取", "抓取成功"].includes(row.status));
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

function scraperArgs(options, useBrowser = false) {
  const args = [
    scraper,
    "--json",
    "--json-input",
    "--between-ms",
    String(options.betweenMs),
    "--page-wait-ms",
    String(options.pageWaitMs),
    "--work-dir",
    options.workDir,
    "--chrome-executable-path",
    options.chromeExecutablePath,
    "--stop-after-consecutive-failures",
    String(options.maxConsecutiveFailures),
  ];
  if (useBrowser) {
    if (options.cdpUrl) args.push("--cdp-url", options.cdpUrl);
    if (options.newTab) args.push("--new-tab");
    if (options.workerTabName) args.push("--worker-tab-name", options.workerTabName);
    if (options.chromeUserDataDir) args.push("--chrome-user-data-dir", options.chromeUserDataDir);
    if (options.headed) args.push("--headed");
    if (options.comment) args.push("--comment");
  }
  return args;
}

function scraperInput(rows, options) {
  return rows
    .map((row) => JSON.stringify({
      seq: row.seq,
      url: row.url,
      mode: row.status === "保持抓取" ? "refresh" : "initial",
      analyzeVideo: options.noVideoAnalysis ? false : (row.status === "准备抓取" && (row.kind === "视频" || !row.kind)),
      commentText: shouldComment(row, options) ? row.generatedComment : "",
    }))
    .join("\n") + "\n";
}

function evalKeywordMatch(title, body) {
  const keys = ["摩点", "Funcinating", "范趣町", "GISMOW"];
  const text = `${String(title || "")}\n${String(body || "")}`;
  const hit = keys.filter((key) => text.toLowerCase().includes(key.toLowerCase()));
  return {
    matched: hit.length > 0,
    hitWords: hit.join("、"),
  };
}

function shouldComment(row, options) {
  if (!options.comment) return false;
  if (!row.generatedComment || !String(row.generatedComment).trim()) return false;
  if (row.status !== "保持抓取") return false;
  return !row.commentStatus || row.commentStatus === "准备评论";
}

function scrape(rows, options, useBrowser = false) {
  const args = scraperArgs(options, useBrowser);
  const input = scraperInput(rows, options);

  const result = spawnSync("python3", args, {
    input,
    encoding: "utf8",
    maxBuffer: 1024 * 1024 * 50,
  });
  if (result.status !== 0) throw new Error(result.stderr || result.stdout);
  return result.stdout
    .split(/\r?\n/)
    .filter(Boolean)
    .map((line) => JSON.parse(line));
}

function handleScrapeResult(options, summary, row, result, browserRows) {
  if (result.ok) {
    updateRecord(options, row, successPayload(row, result));
    summary.success.push(row.seq);
    return { failed: false, stop: false };
  }

  const error = result.error || "unknown error";
  if (options.browserConfirm && !options.cdpOnly) {
    browserRows.push(row);
  } else if (isTerminalFailure(result)) {
    updateRecord(options, row, failurePayload());
    summary.terminated.push({ seq: row.seq, error });
  } else {
    summary.retained.push({ seq: row.seq, error });
  }
  if (isPlatformRisk(result)) {
    summary.stopped = true;
    return { failed: true, stop: true };
  }
  return { failed: true, stop: false };
}

function scrapeAndWriteEach(rows, options, useBrowser, summary, browserRows) {
  return new Promise((resolve, reject) => {
    const child = spawn("python3", scraperArgs(options, useBrowser), {
      stdio: ["pipe", "pipe", "pipe"],
    });
    let stdoutBuffer = "";
    let stderrBuffer = "";
    let index = 0;
    let failures = 0;
    let consecutiveFailures = 0;
    let stopped = false;

    const processLine = (line) => {
      if (!line.trim() || stopped) return;
      let result;
      try {
        result = JSON.parse(line);
      } catch (error) {
        stopped = true;
        child.kill("SIGTERM");
        reject(new Error(`invalid scraper JSON: ${line}`));
        return;
      }
      const row = rows[index] || { seq: `unknown-${index}` };
      index += 1;
      const handled = handleScrapeResult(options, summary, row, result, browserRows);
      if (handled.failed) {
        failures += 1;
        consecutiveFailures += 1;
      } else {
        consecutiveFailures = 0;
      }
      if (
        handled.stop ||
        consecutiveFailures >= options.maxConsecutiveFailures ||
        failures / rows.length > options.maxFailureRate
      ) {
        summary.stopped = true;
        stopped = true;
        child.kill("SIGTERM");
      }
    };

    child.stdout.on("data", (chunk) => {
      stdoutBuffer += chunk.toString("utf8");
      const lines = stdoutBuffer.split(/\r?\n/);
      stdoutBuffer = lines.pop() || "";
      for (const line of lines) processLine(line);
    });

    child.stderr.on("data", (chunk) => {
      stderrBuffer += chunk.toString("utf8");
    });

    child.on("error", reject);
    child.on("close", (code, signal) => {
      if (stdoutBuffer.trim()) processLine(stdoutBuffer);
      if (stopped && signal === "SIGTERM") {
        resolve();
        return;
      }
      if (code !== 0) {
        reject(new Error(stderrBuffer || `scraper exited with code ${code}`));
        return;
      }
      resolve();
    });

    child.stdin.end(scraperInput(rows, options));
  });
}

function successPayload(row, result) {
  const match = evalKeywordMatch(result.title, result.body);
  const payload = {
    ...(result.title ? { 标题: result.title } : {}),
    ...(result.publishTime ? { 发布时间: result.publishTime } : {}),
    ...(Number.isFinite(result.likedCount) ? { 点赞数: result.likedCount } : {}),
    ...(Number.isFinite(result.commentCount) ? { 评论数: result.commentCount } : {}),
    ...(Number.isFinite(result.collectedCount) ? { 收藏数: result.collectedCount } : {}),
    是否符合要求: match.matched ? "符合" : "不符合",
    命中词: match.hitWords || "无命中",
    抓取时间: nowForLark(),
  };

  if (row.status === "准备抓取") {
    payload.正文 = result.body || "";
    payload.抓取状态 = "保持抓取";
  }
  if (result.commentAttempted) {
    payload.评论状态 = result.commentOk ? "评论成功" : "评论失败";
  }

  return payload;
}

function failurePayload() {
  return {
    抓取状态: "抓取异常",
    抓取时间: nowForLark(),
  };
}

function isTerminalFailure(result) {
  const error = String(result?.error || "");
  return /not found|deleted|不存在|已删除|下架|404|作品不存在|视频不存在/i.test(error);
}

function isPlatformRisk(result) {
  const error = String(result?.error || "");
  return /platform risk|captcha|verify|异常访问|安全验证|访问过于频繁|验证码/i.test(error);
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

async function main() {
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
    return;
  }

  if (options.dryRun) {
    summary.candidateSeqs = rows.map((row) => ({ seq: row.seq, status: row.status, kind: row.kind }));
    console.log(JSON.stringify(summary, null, 2));
    return;
  }

  const releaseLock = acquirePlatformLock("douyin");
  try {
    const browserRows = [];

    await scrapeAndWriteEach(rows, options, options.cdpOnly, summary, browserRows);

    if (options.browserConfirm && !summary.stopped && browserRows.length) {
      const fallbackSummary = {
        candidates: browserRows.length,
        success: [],
        terminated: [],
        retained: [],
        stopped: false,
        dryRun: options.dryRun,
      };
      const fallbackRows = [];
      await scrapeAndWriteEach(browserRows, options, true, fallbackSummary, fallbackRows);
      summary.success.push(...fallbackSummary.success);
      for (const item of fallbackSummary.retained) {
        if (isTerminalFailure(item)) {
          summary.terminated.push(item);
        } else {
          summary.retained.push(item);
        }
      }
      summary.stopped = summary.stopped || fallbackSummary.stopped;
    }
  } finally {
    releaseLock();
  }

  console.log(JSON.stringify(summary, null, 2));
}

await main();
