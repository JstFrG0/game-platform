"""Assemble a year snapshot with refreshed IGN facts and reviewable mappings."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3

from .collect_igdb import boundaries
from .data_updates import atomic_write, build_bundle, merge_ign_entries
from .ign_reviews import candidates, import_records, migrate, read_import, resolved_reviews


def normalized_review(row):
    result = {key: row[key] for key in (
        'name', 'score', 'review_url', 'ign_game_url', 'us_release_date', 'review_date',
        'reviewed_on', 'scope', 'title', 'verdict', 'raw_json')}
    result['platforms'] = json.loads(row['platforms_json'])
    return result


def prepare(stage_database, catalog_database, ign_csv, ign_database, year, output):
    """Carry reviewed mappings into staging; propose new mappings without confirming."""
    stage = sqlite3.connect(stage_database)
    stage.row_factory = sqlite3.Row
    source = sqlite3.connect(Path(catalog_database).resolve().as_uri()+'?mode=ro', uri=True)
    source.row_factory = sqlite3.Row
    capture = sqlite3.connect(Path(ign_database).resolve().as_uri()+'?mode=ro', uri=True)
    capture.row_factory = sqlite3.Row
    try:
        start, end = boundaries(year)
        ids = {r[0] for r in stage.execute('SELECT igdb_id FROM igdb_games WHERE first_release_date>=? AND first_release_date<?', (start, end))}
        run = stage.execute("SELECT expected_count,status FROM collection_runs WHERE year=? ORDER BY started_at DESC LIMIT 1", (year,)).fetchone()
        if not run or run['status'] != 'completed' or len(ids) != run['expected_count']:
            raise ValueError('IGDB 暂存采集未通过完整性检查。')
        migrate(stage)
        carried = []
        source_urls = set()
        for row in resolved_reviews(source):
            targets = sorted(set(row['resolved_igdb_ids']) & ids)
            if targets or (row['us_release_date'] or '').startswith(f'{year}-'):
                source_urls.add(row['review_url'])
                carried.append({'review': normalized_review(row), 'igdb_ids': targets})
        with stage:
            merge_ign_entries(stage, carried)
        refreshed, info = read_import(Path(ign_csv))
        records = [r for r in refreshed if r['review_url'] in source_urls or
                   (r['us_release_date'] or '').startswith(f'{year}-')]
        for record in records:
            row = capture.execute('SELECT raw_json FROM reviews WHERE review_url=?', (record['review_url'],)).fetchone()
            if row:
                raw = json.loads(row['raw_json'])
                record['raw_json'] = row['raw_json']
                review = raw.get('review') or {}
                record['verdict'] = review.get('verdict') if isinstance(review.get('verdict'), str) else None
        import_records(stage, records, 'refreshed-ign-capture')
        matches = candidates(stage)
        proposed = [m for m in matches if not m['linked_review_count'] and m['eligible_igdb_id'] is not None]
        pending = [m for m in matches if not m['linked_review_count'] and m['eligible_igdb_id'] is None]
        report = {'year': year, 'igdb_records': len(ids), 'carried_reviews': len(carried),
                  'refreshed_relevant_reviews': len(records), 'import_exclusions': info,
                  'proposed_exact': proposed, 'requires_review': pending}
        atomic_write(Path(output)/'snapshot-review.json', json.dumps(report, ensure_ascii=False, indent=2).encode('utf-8'))
        return report
    finally:
        capture.close()
        source.close()
        stage.close()


def package(stage_database, year, output, supplemental_jsonl=None):
    connection = sqlite3.connect(Path(stage_database).resolve().as_uri()+'?mode=ro', uri=True)
    connection.row_factory = sqlite3.Row
    try:
        start, end = boundaries(year)
        rows = connection.execute('SELECT raw_json FROM igdb_games WHERE first_release_date>=? AND first_release_date<? ORDER BY igdb_id', (start, end))
        records = [json.loads(r['raw_json']) for r in rows]
        year_count = len(records)
        run = connection.execute("SELECT expected_count,status FROM collection_runs WHERE year=? ORDER BY started_at DESC LIMIT 1", (year,)).fetchone()
        if not run or run['status'] != 'completed' or year_count != run['expected_count']:
            raise ValueError('IGDB 暂存采集未通过完整性检查，拒绝打包。')
        if supplemental_jsonl:
            supplemental = [json.loads(line) for line in Path(supplemental_jsonl).read_text(encoding='utf-8').splitlines()]
            for record in supplemental:
                record.setdefault('first_release_date', None)
                released = record['first_release_date']
                if released is not None and start <= released < end:
                    raise ValueError('补充修正条目仍属于目标年份，应重新核验年份扫描。')
            records.extend(supplemental)
        types = {r['type_id']: r['source_name'] for r in connection.execute('SELECT * FROM igdb_game_types')}
        for record in records:
            modern = record.get('game_type')
            if type(modern) is int and modern in types:
                record['game_type'] = {'id': modern, 'type': types[modern]}
        ids = {r['id'] for r in records}
        entries = [{'review': normalized_review(row), 'igdb_ids': sorted(set(row['resolved_igdb_ids']) & ids)}
                   for row in resolved_reviews(connection)]
        manifest = build_bundle(records, output, ign_reviews=entries,
            scope={'year': year, 'basis': 'IGDB first_release_date (UTC)',
                   'year_record_count': year_count, 'correction_record_count': len(records)-year_count})
        report = {'manifest': manifest, 'igdb_year_records': year_count,
                  'igdb_scope_correction_records': len(records)-year_count,
                  'linked_ign_reviews': sum(bool(e['igdb_ids']) for e in entries),
                  'unlinked_ign_reviews': sum(not e['igdb_ids'] for e in entries),
                  'games_with_ign': len({i for e in entries for i in e['igdb_ids']})}
        atomic_write(Path(output)/'snapshot-report.json', json.dumps(report, ensure_ascii=False, indent=2).encode('utf-8'))
        return report
    finally:
        connection.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['prepare', 'package'])
    parser.add_argument('--stage-database', type=Path, required=True)
    parser.add_argument('--catalog-database', type=Path)
    parser.add_argument('--ign-csv', type=Path)
    parser.add_argument('--ign-database', type=Path)
    parser.add_argument('--year', type=int, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--supplemental-jsonl', type=Path)
    args = parser.parse_args()
    if args.command == 'prepare':
        if not all((args.catalog_database, args.ign_csv, args.ign_database)):
            parser.error('prepare requires --catalog-database, --ign-csv, --ign-database')
        result = prepare(args.stage_database, args.catalog_database, args.ign_csv, args.ign_database, args.year, args.output)
        print(json.dumps({key: result[key] for key in ('year', 'igdb_records', 'carried_reviews', 'refreshed_relevant_reviews')}, ensure_ascii=False))
        print('Proposed exact:', len(result['proposed_exact']), 'Requires review:', len(result['requires_review']))
    else:
        print(json.dumps(package(args.stage_database, args.year, args.output, args.supplemental_jsonl), ensure_ascii=False))


if __name__ == '__main__':
    main()
