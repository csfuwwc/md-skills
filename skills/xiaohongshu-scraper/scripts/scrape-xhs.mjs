#!/usr/bin/env node
import { createRequire } from "node:module";
import vm from "node:vm";

const require = createRequire(import.meta.url);

const DEFAULT_UA =
  "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148";

function parseArgs(argv) {
  const options = {
    json: false,
    browser: false,
    cdpUrl: "",
    newTab: false,
    workerTabName: "codex-xhs-worker",
    desktop: false,
    headed: false,
    delayMs: 6000,
    pageWaitMs: null,
    stopAfterConsecutiveFailures: 0,
    missingCountAsZero: false,
    chromeUserDataDir: "",
    chromeExecutablePath: "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    urls: [],
  };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === "--json") options.json = true;
    else if (arg === "--browser") options.browser = true;
    else if (arg === "--cdp-url") options.cdpUrl = argv[++i] || "";
    else if (arg === "--new-tab") options.newTab = true;
    else if (arg === "--worker-tab-name") options.workerTabName = argv[++i] || options.workerTabName;
    else if (arg === "--desktop") options.desktop = true;
    else if (arg === "--headed") options.headed = true;
    else if (arg === "--missing-count-as-zero") options.missingCountAsZero = true;
    else if (arg === "--delay-ms") options.delayMs = Number(argv[++i] || 0);
    else if (arg === "--between-ms") options.delayMs = Number(argv[++i] || 0);
    else if (arg === "--page-wait-ms") options.pageWaitMs = Number(argv[++i] || 0);
    else if (arg === "--stop-after-consecutive-failures") options.stopAfterConsecutiveFailures = Number(argv[++i] || 0);
    else if (arg === "--chrome-user-data-dir") options.chromeUserDataDir = argv[++i] || "";
    else if (arg === "--chrome-executable-path") options.chromeExecutablePath = argv[++i] || "";
    else if (arg === "--help" || arg === "-h") {
      printHelp();
      process.exit(0);
    } else {
      options.urls.push(arg);
    }
  }
  return options;
}

function printHelp() {
  console.log(`Usage:
  scrape-xhs.mjs [--json] [--browser] [--cdp-url http://127.0.0.1:9223] [--new-tab] [--worker-tab-name codex-xhs-worker] [--desktop] [--headed] [--delay-ms 6000] [--page-wait-ms 12000] [--stop-after-consecutive-failures 2] [--missing-count-as-zero] [urls...]

Reads additional URLs from stdin, one per line. Outputs one JSON object per URL with:
  ok, url, finalUrl, noteId, title, desc, body, likedCount, collectedCount, error

Browser mode requires playwright-core available to Node and an installed Chrome.`);
}

async function readStdinLines() {
  if (process.stdin.isTTY) return [];
  const chunks = [];
  for await (const chunk of process.stdin) chunks.push(chunk);
  return Buffer.concat(chunks)
    .toString("utf8")
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function extractUrl(value) {
  const text = String(value || "").replace(/&amp;/g, "&");
  const markdown = text.match(/\((https?:\/\/[^)\s]+)[^)]*\)/);
  if (markdown) return markdown[1];
  const raw = text.match(/https?:\/\/\S+/);
  return raw ? raw[0].replace(/[)\],，。]+$/, "") : "";
}

function normalizeCount(value, missingCountAsZero) {
  if (value == null || value === "") return missingCountAsZero ? 0 : null;
  if (typeof value === "number") return value;
  const text = String(value).trim();
  if (!text) return missingCountAsZero ? 0 : null;
  const numeric = Number.parseFloat(text.replace(/,/g, ""));
  if (!Number.isFinite(numeric)) return missingCountAsZero ? 0 : null;
  if (text.includes("万")) return Math.round(numeric * 10000);
  return Math.round(numeric);
}

function findNoteData(value, seen = new Set()) {
  if (!value || typeof value !== "object" || seen.has(value)) return null;
  seen.add(value);
  if (value.noteId && (value.title || value.desc)) return value;
  for (const child of Object.values(value)) {
    const found = findNoteData(child, seen);
    if (found) return found;
  }
  return null;
}

function extractInitialState(html) {
  const marker = "window.__INITIAL_STATE__=";
  const start = html.indexOf(marker);
  if (start < 0) return null;
  const after = start + marker.length;
  const scriptEnd = html.indexOf("\n</script>", after);
  const end = scriptEnd >= 0 ? scriptEnd : html.indexOf("</script>", after);
  if (end < 0) return null;
  const literal = html.slice(after, end).trim().replace(/;$/, "");
  return vm.runInNewContext(`(${literal})`, Object.create(null), { timeout: 1000 });
}

function toResultFromNote({ url, finalUrl, note }, options) {
  const title = String(note.title || "").trim();
  const desc = String(note.desc || "")
    .replace(/\[话题\]#/g, "#")
    .trim();
  const interact = note.interactInfo || {};
  return {
    ok: true,
    url,
    finalUrl,
    noteId: note.noteId || null,
    title,
    desc,
    body: [title, desc].filter(Boolean).join("\n"),
    likedCount: normalizeCount(interact.likedCount ?? interact.niceCount ?? note.likes, options.missingCountAsZero),
    collectedCount: normalizeCount(interact.collectedCount ?? note.collects, options.missingCountAsZero),
  };
}

async function scrapeStatic(url, options) {
  const response = await fetch(url, {
    redirect: "follow",
    headers: {
      "user-agent": DEFAULT_UA,
      "accept-language": "zh-CN,zh;q=0.9",
    },
  });
  const html = await response.text();
  const state = extractInitialState(html);
  const note = findNoteData(state);
  if (!note) {
    const title = (html.match(/<title>([^<]+)/) || [])[1] || "";
    throw new Error(`no note state${title ? `: ${title}` : ""}`);
  }
  return toResultFromNote({ url, finalUrl: response.url, note }, options);
}

async function createBrowserSession(options) {
  let chromium;
  try {
    ({ chromium } = require("playwright-core"));
  } catch {
    throw new Error("browser mode requires playwright-core; run npm install playwright-core in the working directory");
  }

  const launchOptions = {
    executablePath: options.chromeExecutablePath,
    headless: !options.headed,
    args: ["--disable-blink-features=AutomationControlled"],
  };
  const contextOptions = options.desktop
    ? {
        viewport: { width: 1280, height: 900 },
        isMobile: false,
        hasTouch: false,
        locale: "zh-CN",
      }
    : {
        userAgent: DEFAULT_UA,
        viewport: { width: 390, height: 844 },
        isMobile: true,
        hasTouch: true,
        locale: "zh-CN",
      };

  if (options.cdpUrl) {
    const browser = await chromium.connectOverCDP(options.cdpUrl);
    const context = browser.contexts()[0] || await browser.newContext(contextOptions);
    return {
      browserOrContext: browser,
      context,
      async close() {
        await browser.close();
      },
    };
  }

  const browserOrContext = options.chromeUserDataDir
    ? await chromium.launchPersistentContext(options.chromeUserDataDir, { ...launchOptions, ...contextOptions })
    : await chromium.launch(launchOptions);

  const context = options.chromeUserDataDir
    ? browserOrContext
    : await browserOrContext.newContext(contextOptions);

  return {
    browserOrContext,
    context,
    async close() {
      await context.close();
      if (!options.chromeUserDataDir) await browserOrContext.close();
    },
  };
}

async function getWorkerPage(context, options) {
  const pages = context.pages();
  for (const page of pages) {
    try {
      const name = await page.evaluate(() => window.name);
      if (name === options.workerTabName) return page;
    } catch {
      // Ignore detached pages.
    }
  }
  const page = await context.newPage();
  await page.evaluate((workerName) => {
    window.name = workerName;
  }, options.workerTabName);
  return page;
}

async function scrapeBrowserPage(page, url, options) {
  await page.goto(url, { waitUntil: "networkidle", timeout: 45000 });
  const pageWaitMs = options.pageWaitMs == null ? options.delayMs : options.pageWaitMs;
  await page.waitForTimeout(Math.max(3000, pageWaitMs));
  const note = await page.evaluate(() => {
    function find(value, seen = new Set()) {
      if (!value || typeof value !== "object" || seen.has(value)) return null;
      seen.add(value);
      if (value.noteId && (value.title || value.desc)) return value;
      for (const child of Object.values(value)) {
        const found = find(child, seen);
        if (found) return found;
      }
      return null;
    }
    return find(window.__INITIAL_STATE__ || {});
  });
  if (!note) {
    const title = await page.title().catch(() => "");
    const body = await page.locator("body").innerText({ timeout: 5000 }).catch(() => "");
    throw new Error(`no note state${title ? `: ${title}` : ""}${body ? ` | ${body.slice(0, 80).replace(/\s+/g, " ")}` : ""}`);
  }
  return toResultFromNote({ url, finalUrl: page.url(), note }, options);
}

async function scrapeBrowser(url, options) {
  const session = await createBrowserSession(options);
  const page = await session.context.newPage();
  try {
    return await scrapeBrowserPage(page, url, options);
  } finally {
    await session.close();
  }
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  const stdinUrls = await readStdinLines();
  const urls = [...options.urls, ...stdinUrls].map(extractUrl).filter(Boolean);
  if (!urls.length) {
    printHelp();
    process.exit(1);
  }

  const results = [];
  let consecutiveFailures = 0;
  let browserSession = null;
  let browserPage = null;
  if (options.browser && urls.length > 1) {
    browserSession = await createBrowserSession(options);
    browserPage = options.cdpUrl && options.newTab
      ? await getWorkerPage(browserSession.context, options)
      : await browserSession.context.newPage();
  }
  try {
    for (let index = 0; index < urls.length; index += 1) {
      const url = urls[index];
      let result;
      try {
        result = await scrapeStatic(url, options);
      } catch (staticError) {
        if (!options.browser) {
          result = { ok: false, url, error: staticError.message };
        } else {
          try {
          result = browserPage
              ? await scrapeBrowserPage(browserPage, url, options)
              : await scrapeBrowser(url, options);
          } catch (browserError) {
            result = { ok: false, url, error: `${staticError.message}; browser retry: ${browserError.message}` };
          }
        }
      }
      results.push(result);
      console.log(options.json ? JSON.stringify(result) : formatResult(result));
      if (result.ok) {
        consecutiveFailures = 0;
      } else {
        consecutiveFailures += 1;
        if (
          options.stopAfterConsecutiveFailures > 0 &&
          consecutiveFailures >= options.stopAfterConsecutiveFailures
        ) {
          const stopped = {
            ok: false,
            url: "",
            error: `stopped after ${consecutiveFailures} consecutive failures`,
          };
          console.log(options.json ? JSON.stringify(stopped) : formatResult(stopped));
          break;
        }
      }
      if (index < urls.length - 1 && options.delayMs > 0) await sleep(options.delayMs);
    }
  } finally {
    if (browserSession) await browserSession.close();
  }
}

function formatResult(result) {
  if (!result.ok) return `FAIL ${result.url}: ${result.error}`;
  return `OK ${result.title} likes=${result.likedCount ?? ""} collects=${result.collectedCount ?? ""}\n${result.body}`;
}

main().catch((error) => {
  console.error(error.stack || error.message);
  process.exit(1);
});
