"""Retry a bounded IGN article list using public server-rendered HTML."""
import argparse
import json
import sqlite3
import time
from datetime import datetime
from pathlib import Path

from ign_batch import (AGENT, BatchStop, load_robots, pending_tasks, read_links,
                       register_tasks, update_status, write_reports)
from ign_collect import export_files, ign_url, parse_review, save_record

ROOT = Path(__file__).resolve().parent


def collect_one(request, url, rules, folder):
    if not rules.can_fetch(AGENT, url):
        raise ValueError('robots.txt disallows automated access')
    response = request.get(url, timeout=45000)
    if response.status in {401, 403, 429} or response.status >= 500:
        raise BatchStop(f'HTTP {response.status}; stopped without further requests')
    if response.status >= 400:
        raise ValueError(f'HTTP {response.status}')
    final = ign_url(response.url, 'articles')
    if final != url or not rules.can_fetch(AGENT, final):
        raise ValueError('Response redirected or final URL disallowed; stopped for this article')
    html = response.text()
    folder.mkdir(parents=True, exist_ok=False)
    (folder / 'review.html').write_text(html, encoding='utf-8')
    record = parse_review(html)
    if record['review_url'] != final:
        raise ValueError('Canonical URL differs from requested article; manual check required')
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--file', type=Path, default=ROOT / 'retry_remaining_games.txt')
    parser.add_argument('--limit', type=int, default=8)
    parser.add_argument('--csv-only', action='store_true')
    parser.add_argument('--proxy', help='Explicit HTTP proxy for public IGN requests')
    parser.add_argument('--http', action='store_true', help='Use public HTTP transport instead of Playwright requests')
    parser.add_argument('--http-no-pool', action='store_true', help='Open fresh public HTTP connections for retries')
    parser.add_argument('--refresh', action='store_true',
                        help='Recollect successful articles in this file (database is backed up first)')
    args = parser.parse_args()
    if not 1 <= args.limit <= 200:
        parser.error('--limit must be between 1 and 200')
    links = read_links(args.file)
    database = ROOT / 'data' / 'games.sqlite3'
    if not database.is_file():
        raise ValueError('Existing IGN database not found; put this script beside ign_batch.py')
    folder = ROOT / 'data' / 'http_retry' / datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    folder.mkdir(parents=True)
    backup = folder / 'games_before_http_retry.sqlite3'
    with sqlite3.connect(database.as_uri() + '?mode=ro', uri=True) as source:
        with sqlite3.connect(backup) as destination:
            source.backup(destination)
    print('BACKUP:', backup, flush=True)
    from playwright.sync_api import sync_playwright
    summary = {'status': 'running', 'items': [], 'database_backup': str(backup), 'refresh': args.refresh}
    code = 0
    with sqlite3.connect(database) as connection:
        try:
            with sync_playwright() as playwright:
                request = playwright.request.new_context(user_agent=AGENT + '/0.3 (+public HTML collection)',
                    **({'proxy': {'server': args.proxy}} if args.proxy else {}))
                if args.http:
                    request.dispose()
                    from ign_public_http import PublicHTTP
                    request = PublicHTTP(args.proxy, persistent=not args.http_no_pool)
                try:
                    rules = load_robots(request)
                    interval = max(4, rules.crawl_delay(AGENT) or rules.crawl_delay('*') or 0)
                    rate = rules.request_rate(AGENT) or rules.request_rate('*')
                    if rate and rate.requests > 0:
                        interval = max(interval, rate.seconds / rate.requests)
                    if interval > 60:
                        raise ValueError('Site requests an interval above 60 seconds; stopped')
                    register_tasks(connection, links, retry_failed=True, refresh=args.refresh)
                    jobs = pending_tasks(connection, links)[:args.limit]
                    mode = 'refresh enabled' if args.refresh else 'successes skipped'
                    print(f'List: {len(links)}; queued: {len(jobs)}; {mode}', flush=True)
                    # Include robots.txt in the minimum inter-request delay.
                    for index, url in enumerate(jobs, 1):
                        time.sleep(interval)
                        print(f'[{index}/{len(jobs)}] {url}', flush=True)
                        with connection:
                            update_status(connection, url, 'running', add_attempt=True)
                        try:
                            record = collect_one(request, url, rules, folder / f'{index:03d}')
                            save_record(connection, record)
                            with connection:
                                update_status(connection, url, 'success')
                            summary['items'].append({'url': url, 'status': 'success', 'name': record['name'],
                                                     'game_url': record['game_url'], 'score': record['score'],
                                                     'identity_correction': record['raw'].get('identityCorrection')})
                            print(f"  OK: {record['name']} | IGN {record['score']}", flush=True)
                        except Exception as exc:
                            with connection:
                                update_status(connection, url, 'failed', str(exc)[:1500])
                            summary['items'].append({'url': url, 'status': 'failed', 'error': str(exc)})
                            print('  FAILED:', exc, flush=True)
                            code = 2
                            if isinstance(exc, BatchStop):
                                raise
                finally:
                    request.dispose()
            summary['status'] = 'processed_requires_review'
        except KeyboardInterrupt:
            summary['status'] = 'interrupted'
            code = 130
        except Exception as exc:
            summary['status'] = 'stopped'
            summary['error'] = str(exc)
            print('STOPPED:', exc, flush=True)
            code = 1
        finally:
            (folder / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
            print('SUMMARY:', folder / 'summary.json', flush=True)
            write_reports(connection, ROOT / 'data' / 'exports')
            export_files(connection, ROOT / 'data' / 'exports', None, args.csv_only)
    return code


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        print('ERROR:', exc)
        raise SystemExit(1)
