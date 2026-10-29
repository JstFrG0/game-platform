"""Export local evidence for unlinked IGN reviews, using read-only SQLite."""
import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def export_evidence(root):
    database = root / 'data' / 'igdb.sqlite3'
    report_path = root / 'data' / 'reports' / 'ign_link_report.json'
    if not database.is_file() or not report_path.is_file():
        raise ValueError('Run from F:\\Projects\\game-platform after generating the matching report.')
    report = json.loads(report_path.read_text(encoding='utf-8-sig'))
    with sqlite3.connect(database.resolve().as_uri() + '?mode=ro', uri=True) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA query_only = ON')
        # One read transaction keeps reviews, links and IGDB records consistent.
        connection.execute('BEGIN')
        pending = {r['ign_game_url']: r['n'] for r in connection.execute('''
            SELECT r.ign_game_url,count(*) AS n FROM ign_reviews r
            LEFT JOIN ign_links l USING(ign_game_url) WHERE l.ign_game_url IS NULL
            GROUP BY r.ign_game_url''')}
        groups = [g for g in report['matches'] if g['linked_igdb_id'] is None]
        if {g['ign_game_url'] for g in groups} != set(pending):
            raise ValueError('Matching report is stale. Run python -m game_platform.ign_reviews match, then retry.')
        cases = []
        for group in groups:
            reviews = [dict(r) for r in connection.execute('''
                SELECT review_url,ign_game_url,name,scope,score,platforms_json,
                    us_release_date,review_date,reviewed_on,title,verdict
                FROM ign_reviews WHERE ign_game_url=? ORDER BY review_date,review_url''',
                (group['ign_game_url'],))]
            if len(reviews) != group['review_count']:
                raise ValueError('Review counts changed since matching; regenerate the report.')
            for review in reviews:
                review['platforms'] = json.loads(review.pop('platforms_json'))
            candidates = []
            for option in group['candidates']:
                row = connection.execute('SELECT * FROM igdb_games WHERE igdb_id=?', (option['igdb_id'],)).fetchone()
                if row is None:
                    raise ValueError('Candidate no longer exists; regenerate the matching report.')
                game = dict(row)
                raw = game.pop('raw_json', None)
                game['source_igdb'] = json.loads(raw) if raw else None
                candidates.append({'match': option, 'local_igdb_record': game})
            visible_exact = sum(o['match_method'] in ('name_exact', 'alias_exact') for o in group['candidates'])
            cases.append({'ign_game_url': group['ign_game_url'], 'ign_name': group['ign_name'],
                          'exact_candidate_count': group['exact_candidate_count'],
                          'all_exact_candidates_visible': visible_exact == group['exact_candidate_count'],
                          'source_reviews': reviews, 'candidates': candidates})
        connection.rollback()
    output = {'generated_at': datetime.now(timezone.utc).isoformat(),
              'pending_ign_games': len(cases), 'pending_reviews': sum(pending.values()),
              'report_summary': {k: report.get(k) for k in ('review_count', 'ign_game_count', 'linked_ign_games', 'linked_reviews')},
              'note': 'Local source evidence; candidate lists retain the existing report limit. No links were changed.',
              'cases': cases}
    path = root / 'data' / 'reports' / ('ign_pending_evidence_' + datetime.now().strftime('%Y%m%d_%H%M%S_%f') + '.json')
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding='utf-8')
    print('Pending IGN games:', output['pending_ign_games'])
    print('Pending reviews:', output['pending_reviews'])
    print('File:', path)
    print('Size (MiB):', round(path.stat().st_size / 1024 / 1024, 2))
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-dir', type=Path, default=Path.cwd())
    args = parser.parse_args()
    export_evidence(args.project_dir.resolve())


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, sqlite3.Error, KeyError) as exc:
        print('ERROR:', exc)
        raise SystemExit(1)
