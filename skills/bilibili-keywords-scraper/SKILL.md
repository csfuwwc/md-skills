---
name: bilibili-keywords-scraper
description: Use this skill when the user wants to collect Bilibili/B站 candidate UP creators from keyword search results or an already-filtered Bilibili search page, deduplicate by UP主页 mid, write/update a Lark Base candidate table, and optionally enrich each UP profile with fans, likes, plays, representative videos, and public contact info. This skill does not send DMs or manage outreach status.
metadata:
  short-description: B站候选UP抓取与飞书候选池回填
---

# Bilibili UP Candidate Scraper

## Scope

Use this skill only for candidate UP collection:

- Collect UP names, UP homepage links, and source video links from Bilibili video search result pages.
- Deduplicate by normalized `https://space.bilibili.com/<mid>`.
- Write new rows to a Lark Base candidate table.
- If an existing UP is found, append the keyword to the keyword field instead of creating a duplicate row.
- Optionally visit UP homepages to enrich fans, likes, plays, representative videos, and public contact info.

Do not use this skill for Bilibili private messages, outreach status machines, reply judging, or conversation extraction. Those should be a separate outreach skill.

## Browser Rule

Always use the dedicated Bilibili browser profile:

- Platform: `bilibili`
- CDP URL: configurable (recommended via `config.browser.cdpUrl` or env `BILIBILI_CDP_URL`)
- Prefer `social-browser-profiles` if available; scripts fall back to the configured CDP URL.

If the user has already filtered the Bilibili search page manually, use `--mode current`. If the user gives keyword/sort and wants the script to open the page, use `--mode navigate`.

## Config First

Never hardcode the user's table. Require a local config file based on `templates/config.example.json`.

Minimum required Lark config:

```json
{
  "lark": {
    "baseToken": "...",
    "tableId": "..."
  }
}
```

The config may override field names. See `references/lark-schema.md` for the default schema.

Recommended local config path in a project workspace:

```bash
./.bilibili-up-candidates.config.json
```

Do not commit user-specific config files into a skill repo.

## Main Commands

Dry-run from the currently open/filtered Bilibili search page:

```bash
node ~/.agents/skills/bilibili-up-candidate-scraper/scripts/run_candidate_pipeline.mjs \
  --config ./.bilibili-up-candidates.config.json \
  --keyword "示例关键词" \
  --mode current \
  --pages 1
```

Write to table and enrich profile data:

```bash
node ~/.agents/skills/bilibili-up-candidate-scraper/scripts/run_candidate_pipeline.mjs \
  --config ./.bilibili-up-candidates.config.json \
  --keyword "示例关键词" \
  --mode current \
  --pages all \
  --limit 50 \
  --intervalMs 3000 \
  --execute
```

Navigate by keyword and sort, then write:

```bash
node ~/.agents/skills/bilibili-up-candidate-scraper/scripts/run_candidate_pipeline.mjs \
  --config ./.bilibili-up-candidates.config.json \
  --keyword "示例关键词" \
  --sort pubdate \
  --mode navigate \
  --pages all \
  --execute
```

Collect search results only, without visiting UP homepages:

```bash
node ~/.agents/skills/bilibili-up-candidate-scraper/scripts/run_candidate_pipeline.mjs \
  --config ./.bilibili-up-candidates.config.json \
  --keyword "示例关键词" \
  --mode current \
  --pages all \
  --enrich false \
  --execute
```

## Parameters

- `--config`: Required. Local JSON config for target Lark Base and field mapping.
- `--keyword`: Required. Keyword to write into the keyword field.
- `--mode`: `current` or `navigate`. Default is `current`.
- `--sort`: Used only with `--mode navigate`. Common values: `pubdate`, `click`, `totalrank`.
- `--pubtimeRange`: Optional time filter. Supported values: `recent6m`, `recent3m`, `recent1m`.
- `--pubtimeBegin` / `--pubtimeEnd`: Optional Unix second timestamps for an exact Bilibili publish-time window.
- `--pages`: Page count or `all`. Default is `1`.
- `--limit`: Max UP profiles to enrich in this run. Default comes from config, usually `50`.
- `--intervalMs`: Delay between profile visits. Default comes from config, usually `3000`.
- `--enrich`: Whether to visit UP profiles after collection. Default is `true`.
- `--execute`: Required for Lark writes. Without this, scripts dry-run and print samples.

## Safety Rules

- Default to dry-run unless the user clearly asks to write.
- Before a large run, confirm the target table shown by the config is the intended one.
- Never overwrite enriched profile data by default. Existing UPs only get keyword union updates during search collection.
- Write profile enrichment one record at a time so the table updates visibly.
- If Bilibili shows an ordered-click captcha popup, stop immediately, keep the tab open, and tell the user which UP caused the stop.

## Workflow

1. Confirm or create a local config from `templates/config.example.json`.
2. Before a new keyword run, confirm filter conditions with the user unless they explicitly say to use defaults. At minimum confirm sort (`综合排序`/`最新发布`/`最多播放`), page scope (`当前页`/`前 N 页`/`全部页`), and whether to reuse the current manually filtered page.
3. Ensure the configured Bilibili browser instance is logged in and on the intended search/filter page, or choose `--mode navigate`.
4. Run one dry-run for the first page and show the sample candidates.
5. Run with `--execute` when the target table, filter conditions, and sample look right.
6. For long runs, use batches such as `--limit 50 --intervalMs 3000`; stop only on captcha or hard error.

## Files

- `scripts/collect_from_search.mjs`: Collects UP candidates from search result pages and upserts rows/keywords.
- `scripts/enrich_profiles.mjs`: Visits UP homepages and fills profile metrics/contact fields.
- `scripts/run_candidate_pipeline.mjs`: Runs collection then optional enrichment.
- `references/lark-schema.md`: Default field mapping and required/optional fields.
- `references/bilibili-selectors.md`: Selector and captcha notes.
- `templates/config.example.json`: Copy this to a local config and fill in table info.
