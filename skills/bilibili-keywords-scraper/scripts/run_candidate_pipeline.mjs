#!/usr/bin/env node
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import { parseArgs, boolArg } from './bili_up_common.mjs';

const __filename = fileURLToPath(import.meta.url);
const dir = path.dirname(__filename);
const args = parseArgs();

const execute = boolArg(args.execute, false);
const enrich = boolArg(args.enrich, true);

function passThrough(extra = []) {
  const out = ['--config', args.config];
  for (const key of ['keyword', 'sort', 'pages', 'mode', 'limit', 'intervalMs', 'pubtimeRange', 'pubtimeBegin', 'pubtimeEnd']) {
    if (args[key] !== undefined) out.push(`--${key}`, String(args[key]));
  }
  if (execute) out.push('--execute');
  return out.concat(extra);
}

function run(script, scriptArgs) {
  const r = spawnSync(process.execPath, [path.join(dir, script), ...scriptArgs], {
    encoding: 'utf8',
    maxBuffer: 120 * 1024 * 1024,
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  if (r.status !== 0) {
    throw new Error(`${script} failed:\n${r.stderr || r.stdout}`);
  }
  return JSON.parse(r.stdout);
}

const collect = run('collect_from_search.mjs', passThrough());
let profile = null;
if (enrich) {
  profile = run('enrich_profiles.mjs', passThrough());
}

console.log(JSON.stringify({ ok: true, execute, collect, enrich: profile }, null, 2));
