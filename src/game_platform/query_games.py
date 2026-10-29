"""Read-only local catalog queries, also reusable by the future FastAPI layer."""
import argparse
import json
import sqlite3

from .classify_games import select_games
from .collect_igdb import ROOT


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--year', type=int, default=2025)
    parser.add_argument('--scope', choices=('default', 'all', 'unknown'), default='default')
    parser.add_argument('--platform-id', type=int)
    parser.add_argument('--genre-id', type=int)
    parser.add_argument('--mode-id', type=int)
    parser.add_argument('--min-rating', type=float)
    parser.add_argument('--min-rating-count', type=int)
    parser.add_argument('--limit', type=int, default=20)
    parser.add_argument('--tags', action='store_true', help='List available exact filter IDs and names')
    args = parser.parse_args()
    if not 1950 <= args.year <= 2100 or args.limit < 1:
        parser.error('年份1950–2100；预览条数必须大于0。')
    path = ROOT/'data/igdb.sqlite3'
    try:
        with sqlite3.connect(path.resolve().as_uri()+'?mode=ro', uri=True) as connection:
            connection.row_factory = sqlite3.Row
            if args.tags:
                rows = connection.execute('''SELECT kind,tag_id,max(name) name,count(*) game_count
                    FROM game_tags GROUP BY kind,tag_id ORDER BY kind,tag_id''').fetchall()
                print(json.dumps([dict(r) for r in rows], ensure_ascii=False, indent=2))
            else:
                rows = select_games(connection, args.year, args.scope, args.platform_id,
                                    args.genre_id, args.mode_id, args.min_rating, args.min_rating_count)
                print('Matching records:', len(rows))
                for row in rows[:args.limit]:
                    print(json.dumps({k: row[k] for k in ('igdb_id', 'name', 'game_type_key', 'rating', 'rating_count')}, ensure_ascii=False))
        return 0
    except (OSError, sqlite3.Error, ValueError) as exc:
        print('ERROR:', str(exc)); print('请先执行 classify_games 数据库迁移。'); return 1


if __name__ == '__main__':
    raise SystemExit(main())
