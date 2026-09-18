#!/usr/bin/env python3
"""Read a bounded homepage batch from an existing, approved CDP browser."""
import argparse
import asyncio
import datetime
import fcntl
import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from profile_data import extract_profile_records


def timestamp():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


async def collect(args):
    from playwright.async_api import async_playwright
    sec_uid = urlparse(args.profile_url).path.rstrip('/').split('/')[-1]
    wanted = None
    if args.target_ids:
        wanted = set(json.loads(Path(args.target_ids).read_text()))
        if not wanted or not all(isinstance(x, str) and x.isdigit() for x in wanted):
            raise ValueError('target-ids must be a nonempty JSON array of numeric ID strings')
    records, pending = {}, set()
    report = {'profileUrl': args.profile_url, 'startedAt': timestamp(),
              'dataSource': 'profile_post_api', 'postApiComplete': False,
              'responses': [], 'stopReason': None}
    last_has_more = None

    def save():
        report['records'] = list(records.values())
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2))

    async def read_response(response):
        nonlocal last_has_more
        u = urlparse(response.url)
        if u.path != '/aweme/v1/web/aweme/post/' or parse_qs(u.query).get('sec_user_id') != [sec_uid]:
            return
        try:
            payload = await response.json()
            batch = extract_profile_records(payload, sec_uid, timestamp(), wanted)
            for record in batch:
                records[record['id']] = record
            last_has_more = payload.get('has_more')
            report['responses'].append({'httpStatus': response.status,
                'returnedCount': len(payload.get('aweme_list') or []),
                'matchedCount': len(batch), 'hasMore': last_has_more})
            save()
        except Exception as exc:
            report['responses'].append({'errorType': type(exc).__name__})

    def observe(response):
        task = asyncio.create_task(read_response(response))
        pending.add(task)
        task.add_done_callback(pending.discard)

    async with async_playwright() as pw:
        browser = await pw.chromium.connect_over_cdp(args.cdp_url)
        context = browser.contexts[0]
        page = None
        for candidate in context.pages:
            try:
                if await candidate.evaluate('window.name') == args.worker_tab_name:
                    page = candidate
                    break
            except Exception:
                continue
        if page is None:
            page = await context.new_page()
            await page.evaluate('(name) => window.name = name', args.worker_tab_name)
        page.on('response', observe)
        previous, unchanged = -1, 0
        try:
            await page.goto(args.profile_url, wait_until='domcontentloaded', timeout=45000)
            for step in range(args.max_scrolls + 1):
                if page.is_closed() or not browser.is_connected():
                    report['stopReason'] = 'browser_or_page_closed'
                    break
                await page.wait_for_timeout(args.wait_ms)
                warning = await page.evaluate("() => /验证码|异常访问|访问过于频繁|安全验证|拖动滑块|完成验证/.test(document.body?.innerText || '')")
                if warning:
                    report['stopReason'] = 'platform_warning'
                    break
                if pending:
                    await asyncio.gather(*list(pending), return_exceptions=True)
                if last_has_more == 0:
                    report['stopReason'] = 'post_api_reached_end'
                    break
                if wanted is not None and wanted.issubset(records):
                    report['stopReason'] = 'target_ids_collected'
                    break
                unchanged = unchanged + 1 if len(records) == previous else 0
                if unchanged >= 4:
                    report['stopReason'] = 'no_new_matching_records'
                    break
                previous = len(records)
                if step == args.max_scrolls:
                    report['stopReason'] = 'scroll_limit'
                    break
                await page.evaluate("""() => {
                    const nodes = [document.scrollingElement, ...document.querySelectorAll('main,section,div')]
                        .filter(e => e && e.clientHeight > 200 && e.scrollHeight > e.clientHeight + 100
                            && ['auto','scroll'].includes(getComputedStyle(e).overflowY));
                    const el = nodes.sort((a,b) => (b.scrollHeight-b.clientHeight)-(a.scrollHeight-a.clientHeight))[0]
                        || document.scrollingElement;
                    el.scrollTo({top:el.scrollHeight, behavior:'instant'});
                }""")
        except Exception as exc:
            report['stopReason'] = 'browser_error'
            report['errorType'] = type(exc).__name__
        finally:
            page.remove_listener('response', observe)
            if pending:
                await asyncio.gather(*list(pending), return_exceptions=True)
            report['postApiComplete'] = (
                report['stopReason'] == 'post_api_reached_end'
                and not any('errorType' in r for r in report['responses']))
            report['targetCoverageComplete'] = wanted.issubset(records) if wanted is not None else None
            report['finishedAt'] = timestamp()
            save()
        # Disconnect only: never close the user's browser/context/worker tab.
    print(json.dumps({k: v for k, v in report.items() if k not in ('records', 'responses')}, ensure_ascii=False))
    print(json.dumps({'recordCount': len(records), 'output': args.output}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cdp-url', required=True, help='Exact endpoint returned by approved browser manager')
    parser.add_argument('--profile-url', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--target-ids', help='Optional JSON array of existing platform ID strings')
    parser.add_argument('--worker-tab-name', default='codex-douyin-worker')
    parser.add_argument('--max-scrolls', type=int, default=12)
    parser.add_argument('--wait-ms', type=int, default=4500)
    args = parser.parse_args()
    u = urlparse(args.profile_url)
    if u.hostname != 'www.douyin.com' or not u.path.startswith('/user/') or len(u.path.rstrip('/').split('/')) != 3:
        parser.error('profile-url must be a canonical https://www.douyin.com/user/<sec_uid> URL')
    if u.scheme != 'https' or not u.path.rstrip('/').split('/')[-1] or args.max_scrolls < 0 or args.wait_ms < 3000:
        parser.error('Use HTTPS, a valid author ID, nonnegative scrolls and wait-ms >= 3000')
    lock_path = Path('/tmp/social-scraper-locks/douyin.lock')
    lock_path.parent.mkdir(exist_ok=True)
    with lock_path.open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        asyncio.run(collect(args))


if __name__ == '__main__':
    main()
