"""Collect explicitly selected years, verify every scan, then build/publish data."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import tempfile

from .collect_igdb import ROOT, collect, initialize, load_env, utc_now
from .classify_games import migrate, sync_types
from .data_updates import atomic_write, build_bundle, operation_lock, publish_bundle
from .igdb_client import IGDBClient


def run_daily(api, years, output, repository=None, token=None):
    output = Path(output)
    years = sorted(set(years))
    if not years or any(type(year) is not int or not 1950 <= year <= 2100 for year in years):
        raise ValueError('必须明确指定采集年份（1950–2100）。')
    with operation_lock(output/'daily.lock'):
        report = {'started_at': utc_now(), 'years': years, 'status': 'running', 'scans': []}
        try:
            # Never collect into the user's live database or reuse partial output as a release.
            with tempfile.TemporaryDirectory(prefix='catalog-daily-') as work:
                connection = initialize(Path(work)/'igdb.sqlite3')
                try:
                    migrate(connection)
                    sync_types(api, connection)
                    for year in years:
                        scan = collect(api, connection, year, Path(work), fresh=True)
                        report['scans'].append({key: scan[key] for key in (
                            'year', 'status', 'count_check_passed', 'collected_unique_games')})
                        if not scan['count_check_passed']:
                            raise ValueError(f'{year} 年采集未通过计数校验，停止发布。')
                    records = []
                    types = {r['type_id']: r['source_name'] for r in connection.execute('SELECT * FROM igdb_game_types')}
                    for row in connection.execute('SELECT raw_json FROM igdb_games ORDER BY igdb_id'):
                        record = json.loads(row['raw_json'])
                        modern = record.get('game_type')
                        if type(modern) is int and modern in types:
                            record['game_type'] = {'id': modern, 'type': types[modern]}
                        records.append(record)
                    report['manifest'] = build_bundle(records, output)
                finally:
                    connection.close()
            report['status'] = 'built'
            if repository:
                report['publication'] = publish_bundle(repository, output, token)
                report['status'] = 'published'
            return report
        except Exception as exc:
            report.update(status='failed', error=type(exc).__name__)
            raise
        finally:
            report['finished_at'] = utc_now()
            atomic_write(output/'daily-report.json', json.dumps(report, ensure_ascii=False, indent=2).encode('utf-8'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--years', type=int, nargs='+', required=True)
    parser.add_argument('--output', type=Path, default=ROOT/'data/published')
    parser.add_argument('--env-file', type=Path, default=ROOT/'.env')
    parser.add_argument('--publish', action='store_true')
    parser.add_argument('--repository', help='owner/repo; required with --publish')
    args = parser.parse_args()
    if args.publish and not args.repository:
        parser.error('--publish 需要 --repository owner/repo')
    load_env(args.env_file)
    client_id = os.environ.get('IGDB_CLIENT_ID', '')
    secret = os.environ.get('IGDB_CLIENT_SECRET', '')
    token = os.environ.get('GITHUB_TOKEN', '')
    if not client_id or not secret or (args.publish and not token):
        print('缺少 IGDB_CLIENT_ID / IGDB_CLIENT_SECRET 或发布所需的 GITHUB_TOKEN。')
        return 1
    try:
        with IGDBClient(client_id, secret) as api:
            report = run_daily(api, args.years, args.output,
                               args.repository if args.publish else None, token)
        print(json.dumps({'status': report['status'], 'report': str(args.output/'daily-report.json')}, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(f'ERROR: {type(exc).__name__}；本轮未完成，请检查 daily-report.json。')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
