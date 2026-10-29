"""Deterministic daily IGDB + IGN collection, validation and GitHub publication."""
from __future__ import annotations

import argparse
import csv
from contextlib import closing
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import uuid

from .classify_games import migrate, sync_types
from .collect_igdb import FIELDS, ROOT, boundaries, collect, initialize, load_env, upsert_record, utc_now
from .data_updates import atomic_write, build_bundle, merge_ign_entries, operation_lock, publish_bundle, read_bundle_content
from .igdb_client import IGDBClient
from .ign_reviews import apply_links, candidates, import_records, migrate as migrate_ign, read_import, resolved_reviews
from .release_snapshot import normalized_review
from .update_service import read_token
from .data_retention import prune_releases


def save(path, value):
    atomic_write(Path(path), json.dumps(value, ensure_ascii=False, indent=2).encode('utf-8'))


def execute(command, cwd, log):
    with Path(log).open('a', encoding='utf-8') as output:
        result = subprocess.run(command, cwd=cwd, stdout=output, stderr=subprocess.STDOUT,
            env={**os.environ, 'PYTHONUTF8': '1', 'PYTHONIOENCODING': 'utf-8'}, timeout=2400)
    if result.returncode:
        raise RuntimeError(f'Child process failed (exit {result.returncode}); see {Path(log).name}')


def review_in_years(record, years):
    return years is None or (record.get('review_date') or '')[:4] in {str(year) for year in years}


def capture_ign(root, run, since, proxy, years=None):
    """Run existing public collectors and accept only a fresh, bounded discovery."""
    root = Path(root)
    python = root/'.venv/Scripts/python.exe'
    started = datetime.now().timestamp()
    execute([str(python), '-u', 'ign_feed_discover.py', '--headless', '--http',
        '--sort', 'Latest', '--until', since, '--max-pages', '100',
        *(['--proxy', proxy] if proxy else [])], root, run/'ign-discovery.log')
    reports = [p for p in (root/'data/feed_discovery').glob('*/feed_discovery_report.json')
               if p.stat().st_mtime >= started - 1]
    if not reports:
        raise ValueError('No fresh IGN discovery report')
    report_path = max(reports, key=lambda p: p.stat().st_mtime)
    report = json.loads(report_path.read_text(encoding='utf-8'))
    if report.get('date_boundary') != since or report.get('sort') != 'Latest' or report.get('stop_reason') not in {
        'review_date_boundary_reached', 'empty_page_returned'}:
        raise ValueError('IGN discovery did not finish the requested date window')
    urls = (report_path.parent/'feed_review_urls.txt').read_text(encoding='utf-8-sig').splitlines()
    urls = list(dict.fromkeys(u.strip() for u in urls if u.strip()))
    if len(urls) != report['candidate_count'] or len(urls) > 200:
        raise ValueError('IGN discovery count mismatch or daily collection limit exceeded')
    if years is not None:
        with (report_path.parent/'feed_review_metadata.csv').open(encoding='utf-8-sig', newline='') as metadata:
            allowed = {row['评测链接'] for row in csv.DictReader(metadata)
                if review_in_years({'review_date': row['评测发布日期']}, years)}
        urls = [url for url in urls if url in allowed]
        report['selected_review_years'] = years
        report['selected_candidate_count'] = len(urls)
    save(run/'ign-discovery.json', report)
    if urls:
        url_file = run/'ign-urls.txt'
        url_file.write_text('\n'.join(urls)+'\n', encoding='utf-8')
        execute([str(python), '-u', 'ign_http_retry.py', '--file', str(url_file),
            '--limit', '200', '--refresh', '--http', '--csv-only',
            *(['--proxy', proxy] if proxy else [])], root, run/'ign-collection.log')
    else:
        # No new articles is legitimate; still export the existing source archive.
        sys.path.insert(0, str(root))
        from ign_collect import export_files
        with sqlite3.connect(root/'data/games.sqlite3') as archive:
            export_files(archive, root/'data/exports', None, True)
    return root/'data/exports/ign_all.csv', root/'data/games.sqlite3', urls


def refresh_ids(api, connection, ids):
    ids = sorted(set(ids))
    for offset in range(0, len(ids), 200):
        batch = ids[offset:offset+200]
        rows = api.query('games', f'fields {FIELDS}; where id = ({",".join(map(str, batch))}); limit 200;')
        if {r['id'] for r in rows} != set(batch) or len(rows) != len(batch):
            raise ValueError('Previously published game disappeared; manual review required')
        with connection:
            for row in rows:
                row.setdefault('first_release_date', None)
                upsert_record(connection, row)


def assemble(api, connection, years, run, prior_ids, csv, capture_db, recent_urls, ign_years=None):
    # New/refreshed rows are classified by upsert_record; historical rows need
    # not be rewritten for a daily snapshot of a bounded set of years.
    sync_types(api, connection, refresh_records=False)
    scans, ids = [], set()
    for year in years:
        scan = collect(api, connection, year, run/'igdb', fresh=True)
        scans.append({k: scan[k] for k in ('year', 'status', 'count_check_passed', 'collected_unique_games')})
        if not scan['count_check_passed']:
            raise ValueError(f'{year}: IGDB count validation failed')
        ids.update(r[0] for r in connection.execute('SELECT igdb_id FROM run_members WHERE run_id=?', (scan['run_id'],)))
    scan_ids = set(ids)
    # Include moved/delayed games so clients can correct yesterday's release date.
    refresh_ids(api, connection, set(prior_ids) - ids)
    ids.update(prior_ids)
    records, exclusions = read_import(csv)
    records = [record for record in records if review_in_years(record, ign_years)]
    with closing(sqlite3.connect(Path(capture_db).resolve().as_uri()+'?mode=ro', uri=True)) as source:
        for record in records:
            raw = source.execute('SELECT raw_json FROM reviews WHERE review_url=?', (record['review_url'],)).fetchone()
            if raw:
                record['raw_json'] = raw[0]
                verdict = (json.loads(raw[0]).get('review') or {}).get('verdict')
                record['verdict'] = verdict if isinstance(verdict, str) else None
    import_records(connection, records, 'daily-ign-archive')
    relevant = {r['review_url'] for r in resolved_reviews(connection)
        if review_in_years(r, ign_years) and (set(r['resolved_igdb_ids']) & ids
        or (r['us_release_date'] or '')[:4] in {str(y) for y in years} or r['review_url'] in recent_urls)}
    # Restrict automatic association to the existing strict exact-match rule.
    relevant_games = {r['ign_game_url'] for r in records if r['review_url'] in relevant}
    matches = candidates(connection, game_urls=relevant_games)
    actions = [(m['ign_game_url'], m['eligible_igdb_id']) for m in matches
        if m['ign_game_url'] in relevant_games and not m['linked_review_count'] and m['eligible_igdb_id'] is not None]
    apply_links(connection, actions, 'daily_exact')
    entries = [{'review': normalized_review(r), 'igdb_ids': r['resolved_igdb_ids']}
        for r in resolved_reviews(connection) if r['review_url'] in relevant]
    targets = {i for e in entries for i in e['igdb_ids']}
    refresh_ids(api, connection, targets - ids)
    ids.update(targets)
    types = {r['type_id']: r['source_name'] for r in connection.execute('SELECT * FROM igdb_game_types')}
    games = []
    for ident in sorted(ids):
        record = json.loads(connection.execute('SELECT raw_json FROM igdb_games WHERE igdb_id=?', (ident,)).fetchone()[0])
        modern = record.get('game_type')
        if type(modern) is int and modern in types:
            record['game_type'] = {'id': modern, 'type': types[modern]}
        games.append(record)
    approved = {url for url, _ in actions}
    pending = [m for m in matches if not m['fully_linked'] and m['ign_game_url'] not in approved]
    save(run/'ign-matching.json', {'automatic_exact': actions, 'pending': pending, 'import_exclusions': exclusions})
    scope = {'year': years[0], 'year_record_count': len(scan_ids), 'correction_record_count': len(ids)-len(scan_ids)} if len(years) == 1 else None
    manifest = build_bundle(games, run/'bundle', ign_reviews=entries, scope=scope)
    return {'scans': scans, 'manifest': manifest, 'pending_ign_games': len(pending),
            'automatic_exact_links': len(actions), 'linked_ign_reviews': sum(bool(e['igdb_ids']) for e in entries)}, sorted(ids)


def run(settings, *, publish=True):
    years = sorted(set(settings['years']))
    ign_years = sorted(set(settings.get('ign_review_years', years)))
    keep = settings.get('release_retention_count', 31)
    if type(keep) is not int or keep < 1:
        raise ValueError('Invalid release retention count')
    if not years or any(type(y) is not int or not 1950 <= y <= 2100 for y in years):
        raise ValueError('Invalid collection years')
    if not ign_years or any(type(y) is not int or not 1950 <= y <= 2100 for y in ign_years):
        raise ValueError('Invalid IGN review years')
    output = ROOT/'data/daily'
    output.mkdir(parents=True, exist_ok=True)
    with operation_lock(output/'daily.lock'):
        run = output/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:8])
        run.mkdir()
        report = {'started_at': utc_now(), 'status': 'running', 'stage': 'preflight', 'years': years,
                  'ign_review_years': ign_years, 'run_directory': str(run)}
        def checkpoint(stage):
            report['stage'] = stage
            save(run/'report.json', report)
            save(output/'latest-report.json', report)
            print('STAGE:', stage, flush=True)
        try:
            if settings.get('proxy'):
                os.environ['HTTP_PROXY'] = settings['proxy']
                os.environ['HTTPS_PROXY'] = settings['proxy']
                os.environ.setdefault('NO_PROXY', 'localhost,127.0.0.1,::1')
            load_env(ROOT/'.env')
            if not os.environ.get('IGDB_CLIENT_ID') or not os.environ.get('IGDB_CLIENT_SECRET'):
                raise ValueError('Missing IGDB credentials')
            token = read_token(ROOT/'data', 'publish') if publish else None
            previous_path = output/'last-success.json'
            previous = json.loads(previous_path.read_text(encoding='utf-8')) if previous_path.exists() else {}
            since = (datetime.now(timezone.utc)-timedelta(days=14)).date()
            if previous.get('finished_at'):
                since = min(since, (datetime.fromisoformat(previous['finished_at'])-timedelta(days=2)).date())
            since = max(since, datetime(min(ign_years), 1, 1).date())
            checkpoint('ign_collection')
            csv, capture, urls = capture_ign(settings['ign_root'], run, since.isoformat(), settings.get('proxy'), ign_years)
            report['ign_discovered_urls'] = len(urls)
            retained_urls = set(urls)
            checkpoint('igdb_collection')
            stage = run/'stage.sqlite3'
            with closing(sqlite3.connect((ROOT/'data/igdb.sqlite3').as_uri()+'?mode=ro', uri=True)) as source:
                with closing(sqlite3.connect(stage)) as destination:
                    source.backup(destination)
            connection = initialize(stage)
            try:
                if not connection.execute('SELECT 1 FROM schema_versions WHERE version=2').fetchone():
                    migrate(connection)
                migrate_ign(connection)
                prior_ids = set(previous.get('game_ids', []))
                baseline = ROOT/'data/release-2026/bundle'
                if (baseline/'catalog-manifest.json').is_file():
                    baseline_manifest = json.loads((baseline/'catalog-manifest.json').read_text(encoding='utf-8'))
                    if baseline_manifest.get('scope', {}).get('year') in years:
                        baseline_games, _ = read_bundle_content(baseline_manifest, (baseline/'catalog-data.zip').read_bytes())
                        prior_ids.update(game['id'] for game in baseline_games)
                # Retain last publication even if the desktop application has not installed it yet.
                if previous.get('bundle_directory'):
                    directory = Path(previous['bundle_directory'])
                    manifest = json.loads((directory/'catalog-manifest.json').read_text(encoding='utf-8'))
                    games, entries = read_bundle_content(manifest, (directory/'catalog-data.zip').read_bytes())
                    retained_urls.update(entry['review']['review_url'] for entry in entries)
                    with connection:
                        for game in games:
                            if not connection.execute('SELECT 1 FROM igdb_games WHERE igdb_id=?', (game['id'],)).fetchone():
                                upsert_record(connection, game)
                        merge_ign_entries(connection, entries)
                for year in years:
                    low, high = boundaries(year)
                    prior_ids.update(r[0] for r in connection.execute('SELECT igdb_id FROM igdb_games WHERE first_release_date>=? AND first_release_date<?', (low, high)))
                with IGDBClient(os.environ['IGDB_CLIENT_ID'], os.environ['IGDB_CLIENT_SECRET']) as api:
                    result, ids = assemble(api, connection, years, run, prior_ids, csv, capture, retained_urls, ign_years)
                report.update(result)
            finally:
                connection.close()
            checkpoint('publish' if publish else 'build_only')
            if publish:
                report['publication'] = publish_bundle(settings['repository'], run/'bundle', token)
            report.update(status='published' if publish else 'built', finished_at=utc_now())
            if publish:
                save(previous_path, {'finished_at': report['finished_at'], 'game_ids': ids,
                    'bundle_directory': str(run/'bundle'), 'publication': report['publication']})
                # The validated bundle is the durable baseline. Do not retain
                # an entire copy of the historical catalog for every successful day.
                try:
                    stage.unlink(missing_ok=True)
                except OSError:
                    report['staging_cleanup'] = 'deferred'
                checkpoint('retention')
                def retention_progress(value):
                    report['retention'] = value
                    save(run/'report.json', report)
                    save(output/'latest-report.json', report)
                report['retention'] = prune_releases(settings['repository'], token, keep=keep,
                    protected_tag=report['publication']['tag'], progress=retention_progress)
                report['finished_at'] = utc_now()
        except Exception as exc:
            # Never log raw HTTP exceptions: request headers may contain secrets.
            report.update(status='failed', error_type=type(exc).__name__, finished_at=utc_now())
            if isinstance(exc, KeyError):
                report['missing_field'] = str(exc.args[0])[:80]
            raise
        finally:
            save(run/'report.json', report)
            save(output/'latest-report.json', report)
        return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--settings', type=Path, default=ROOT/'data/daily-settings.json')
    parser.add_argument('--build-only', action='store_true')
    args = parser.parse_args()
    try:
        report = run(json.loads(args.settings.read_text(encoding='utf-8-sig')), publish=not args.build_only)
        print(json.dumps({k: report[k] for k in ('status', 'run_directory', 'pending_ign_games', 'linked_ign_reviews')}, ensure_ascii=False))
        if report.get('publication'):
            print(report['publication']['url'])
        if report.get('retention', {}).get('status') == 'failed':
            print('RETENTION_FAILED: publication succeeded; inspect retention in the run report')
            return 1
        return 0
    except Exception as exc:
        print(f'DAILY_FAILED: {type(exc).__name__}; see data/daily/latest-report.json', flush=True)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
