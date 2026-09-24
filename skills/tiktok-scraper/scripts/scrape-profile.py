#!/usr/bin/env python3
"""Collect TikTok account metrics and post-list data through the dedicated CDP browser."""
from __future__ import annotations

import argparse
import asyncio
import datetime
import fcntl
import json
from pathlib import Path
from urllib.parse import urlparse

from profile_data import account_snapshot, extract_profile_records


WARNING_SCRIPT = r"""() => {
 const visible=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'};
 const found=[];
 for(const e of document.querySelectorAll('iframe[src*="captcha"],[class*="captcha"],[id*="captcha"],[class*="verify"]')) if(visible(e)) found.push((e.innerText||e.tagName).trim().slice(0,100));
 return [...new Set(found.filter(Boolean))].slice(0,8);
}"""


def timestamp():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


async def collect(args):
    from playwright.async_api import async_playwright
    handle = urlparse(args.profile_url).path.strip('/').removeprefix('@')
    known = set(json.loads(Path(args.known_ids).read_text())) if args.known_ids else set()
    if not all(isinstance(x, str) and x.isdigit() for x in known):
        raise ValueError('known-ids must be a JSON array of numeric ID strings')
    records, pending = {}, set()
    report = {'profileUrl': args.profile_url, 'startedAt': timestamp(),
              'dataSource': 'profile_item_list_api', 'responses': [],
              'stopReason': None, 'postApiComplete': False}
    last_has_more = None

    def save():
        report['records'] = list(records.values())
        path = Path(args.output); path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2))

    async def read_response(response):
        nonlocal last_has_more
        if urlparse(response.url).path.rstrip('/') != '/api/post/item_list':
            return
        try:
            payload = await response.json()
            items = payload.get('itemList') or []
            batch = extract_profile_records(payload, handle, timestamp())
            for row in batch:
                records[row['id']] = row
            last_has_more = payload.get('hasMore', payload.get('has_more'))
            report['responses'].append({'httpStatus': response.status, 'returnedCount': len(items),
                                        'matchedCount': len(batch), 'hasMore': last_has_more})
            save()
        except Exception as exc:
            report['responses'].append({'errorType': type(exc).__name__})

    def observe(response):
        task = asyncio.create_task(read_response(response)); pending.add(task); task.add_done_callback(pending.discard)

    async with async_playwright() as pw:
        browser = await pw.chromium.connect_over_cdp(args.cdp_url)
        if not browser.contexts:
            raise RuntimeError('CDP has no browser context')
        context = browser.contexts[0]
        page = next((p for p in context.pages if not p.is_closed() and 'tiktok.com' in (p.url or '')), None)
        if page is None:
            page = await context.new_page()
        page.on('response', observe)
        try:
            await page.goto(args.profile_url, wait_until='domcontentloaded', timeout=60000)
            await page.wait_for_timeout(args.wait_ms)
            scope = await page.evaluate('() => window.__UNIVERSAL_DATA__?.__DEFAULT_SCOPE__ || {}')
            if not scope:
                hydration = await page.locator('script#__UNIVERSAL_DATA_FOR_REHYDRATION__').text_content()
                scope = (json.loads(hydration or '{}').get('__DEFAULT_SCOPE__') or {})
            report['account'] = account_snapshot(scope, handle, int(datetime.datetime.now().timestamp() * 1000))
            previous, unchanged = -1, 0
            for step in range(args.max_scrolls + 1):
                warning = await page.evaluate(WARNING_SCRIPT)
                if warning:
                    report['warningEvidence'] = warning; report['stopReason'] = 'platform_warning'; break
                if pending:
                    await asyncio.gather(*list(pending), return_exceptions=True)
                if last_has_more in (False, 0):
                    report['stopReason'] = 'post_api_reached_end'; break
                if known and any(row_id in known and not row.get('isPinned')
                                 for row_id, row in records.items()):
                    report['stopReason'] = 'known_content_reached'; break
                unchanged = unchanged + 1 if len(records) == previous else 0
                if unchanged >= 4:
                    report['stopReason'] = 'no_new_matching_records'; break
                previous = len(records)
                if step == args.max_scrolls:
                    report['stopReason'] = 'scroll_limit'; break
                await page.evaluate('() => window.scrollTo({top:document.documentElement.scrollHeight,behavior:"instant"})')
                await page.wait_for_timeout(args.wait_ms)
        except Exception as exc:
            report['stopReason'] = 'browser_error'; report['errorType'] = type(exc).__name__
            report['errorMessage'] = str(exc)[:200]
        finally:
            page.remove_listener('response', observe)
            if pending:
                await asyncio.gather(*list(pending), return_exceptions=True)
            report['postApiComplete'] = report['stopReason'] in ('post_api_reached_end', 'known_content_reached') and not any('errorType' in r for r in report['responses'])
            report['finishedAt'] = timestamp(); save()
    print(json.dumps({'recordCount': len(records), 'stopReason': report['stopReason'], 'output': args.output}, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cdp-url', default='http://127.0.0.1:9225')
    parser.add_argument('--profile-url', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--known-ids')
    parser.add_argument('--max-scrolls', type=int, default=20)
    parser.add_argument('--wait-ms', type=int, default=4000)
    args = parser.parse_args()
    u = urlparse(args.profile_url)
    if u.scheme != 'https' or u.hostname not in ('www.tiktok.com', 'tiktok.com') or not u.path.startswith('/@'):
        parser.error('profile-url must be https://www.tiktok.com/@<handle>')
    if args.cdp_url != 'http://127.0.0.1:9225':
        parser.error('TikTok account scraping must use the dedicated 9225 CDP endpoint')
    lock = Path('/tmp/social-scraper-locks/tiktok.lock'); lock.parent.mkdir(exist_ok=True)
    with lock.open('a') as fh:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        asyncio.run(collect(args))


if __name__ == '__main__':
    main()
