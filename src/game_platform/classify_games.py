"""Back up, migrate and classify local IGDB data without re-collecting games."""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from .collect_igdb import ROOT, boundaries, initialize, load_env, utc_now
from .igdb_client import APIError, IGDBClient

# Only the deprecated category enum uses these numbers. Modern IDs are opaque.
LEGACY_TYPES = dict(enumerate((
    'main_game', 'dlc_addon', 'expansion', 'bundle', 'standalone_expansion',
    'mod', 'episode', 'season', 'remake', 'remaster', 'expanded_game',
    'port', 'fork', 'pack', 'update')))
DEFAULT_TYPES = ('main_game', 'remake', 'remaster', 'standalone_expansion')
LABELS = {
    'main_game': '游戏本体', 'dlc_addon': 'DLC', 'expansion': '扩展包',
    'bundle': '合集', 'standalone_expansion': '独立扩展', 'mod': '模组',
    'episode': '章节', 'season': '季', 'remake': '重制版', 'remaster': '高清复刻版',
    'expanded_game': '扩充版', 'port': '移植版', 'fork': '衍生分支',
    'pack': '内容包', 'update': '更新', 'unknown': '待分类',
}
COLUMNS = {
    'game_type_id': 'INTEGER', 'legacy_category': 'INTEGER',
    'game_type_key': "TEXT NOT NULL DEFAULT 'unknown'",
    'classification_source': "TEXT NOT NULL DEFAULT 'missing'",
    'parent_game_id': 'INTEGER', 'version_parent_id': 'INTEGER',
    'game_status_id': 'INTEGER', 'legacy_status': 'INTEGER',
    'game_modes_json': "TEXT NOT NULL DEFAULT '[]'",
}


def reference_id(value):
    if isinstance(value, dict):
        value = value.get('id')
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def type_key(value):
    if not isinstance(value, str):
        return 'unknown'
    key = re.sub(r'[^a-z0-9]+', '_', value.lower()).strip('_')
    aliases = {'main': 'main_game', 'dlc': 'dlc_addon', 'dlc_add_on': 'dlc_addon',
               'standalone': 'standalone_expansion', 'expanded': 'expanded_game',
               'pack_addon': 'pack', 'pack_add_on': 'pack'}
    key = aliases.get(key, key)
    return key if key in LABELS else 'unknown'


def migrate(connection):
    """All ALTERs, data backfill and version registration are one transaction."""
    with connection:
        connection.execute('BEGIN IMMEDIATE')
        columns = {row['name'] for row in connection.execute('PRAGMA table_info(igdb_games)')}
        for name, sql_type in COLUMNS.items():
            if name not in columns:
                connection.execute(f'ALTER TABLE igdb_games ADD COLUMN {name} {sql_type}')
        connection.execute('''CREATE TABLE IF NOT EXISTS igdb_game_types(
            type_id INTEGER PRIMARY KEY, source_name TEXT NOT NULL,
            type_key TEXT NOT NULL, fetched_at TEXT NOT NULL)''')
        connection.execute('''CREATE TABLE IF NOT EXISTS game_tags(
            igdb_id INTEGER NOT NULL REFERENCES igdb_games(igdb_id) ON DELETE CASCADE,
            kind TEXT NOT NULL CHECK(kind IN ('platform','genre','mode')),
            tag_id INTEGER NOT NULL, name TEXT,
            PRIMARY KEY(igdb_id,kind,tag_id))''')
        connection.execute('CREATE INDEX IF NOT EXISTS ix_game_tags ON game_tags(kind,tag_id,igdb_id)')
        connection.execute('CREATE INDEX IF NOT EXISTS ix_game_type ON igdb_games(game_type_key)')
        connection.execute('CREATE INDEX IF NOT EXISTS ix_parent_game ON igdb_games(parent_game_id)')
        # Reinterpret existing source labels locally when mapping rules improve.
        for entry in connection.execute('SELECT type_id,source_name FROM igdb_game_types').fetchall():
            connection.execute('UPDATE igdb_game_types SET type_key=? WHERE type_id=?',
                               (type_key(entry['source_name']), entry['type_id']))
        # Materialize before writes so the SELECT cursor cannot be affected by updates.
        for row in connection.execute('SELECT igdb_id,raw_json FROM igdb_games').fetchall():
            record = json.loads(row['raw_json'])
            if not isinstance(record, dict) or record.get('id') != row['igdb_id']:
                raise ValueError(f"IGDB {row['igdb_id']} 的原始 JSON 与记录 ID 不匹配，迁移回滚。")
            backfill_record(connection, row['igdb_id'], record)
        connection.execute('INSERT OR IGNORE INTO schema_versions VALUES(2,?)', (utc_now(),))


def backfill_record(connection, game_id, record):
    modern = record.get('game_type')
    modern_id = reference_id(modern)
    legacy = reference_id(record.get('category'))
    key, source = 'unknown', 'missing'
    if modern_id is not None:
        entry = connection.execute('SELECT type_key FROM igdb_game_types WHERE type_id=?', (modern_id,)).fetchone()
        embedded = type_key(modern.get('type')) if isinstance(modern, dict) else 'unknown'
        key = entry['type_key'] if entry else embedded
        source = 'game_types_dictionary' if entry else ('embedded_game_type' if embedded != 'unknown' else 'unresolved_game_type')
    elif modern is not None:
        source = 'invalid_game_type'
    elif legacy in LEGACY_TYPES:
        key, source = LEGACY_TYPES[legacy], 'legacy_category'
    elif legacy is not None:
        source = 'unresolved_legacy_category'
    modes = record.get('game_modes') or []
    connection.execute('''UPDATE igdb_games SET game_type_id=?,legacy_category=?,game_type_key=?,
        classification_source=?,parent_game_id=?,version_parent_id=?,game_status_id=?,legacy_status=?,
        game_modes_json=? WHERE igdb_id=?''', (
        modern_id, legacy, key, source, reference_id(record.get('parent_game')),
        reference_id(record.get('version_parent')), reference_id(record.get('game_status')),
        reference_id(record.get('status')), json.dumps(modes, ensure_ascii=False), game_id))
    connection.execute('DELETE FROM game_tags WHERE igdb_id=?', (game_id,))
    for field, kind in [('platforms', 'platform'), ('genres', 'genre'), ('game_modes', 'mode')]:
        for item in record.get(field) or []:
            tag_id = reference_id(item)
            if tag_id is not None:
                name = item.get('name') if isinstance(item, dict) else None
                connection.execute('INSERT OR REPLACE INTO game_tags VALUES(?,?,?,?)',
                                   (game_id, kind, tag_id, name if isinstance(name, str) else None))


def sync_types(api, connection, *, refresh_records=True):
    """Fetch a complete dictionary before applying it; no hard-coded modern IDs."""
    entries, last = [], -1
    while True:
        page = api.query('game_types', f'fields id,type; where id > {last}; sort id asc; limit 500;')
        if not isinstance(page, list):
            raise ValueError('game_types 响应不是列表。')
        if not page:
            break
        for entry in page:
            if not isinstance(entry, dict):
                raise ValueError('game_types 条目格式错误。')
            ident = reference_id(entry)
            if ident is None or ident <= last or not isinstance(entry.get('type'), str) or not entry['type'].strip():
                raise ValueError('game_types ID 或类别名称异常，字典不更新。')
            last = ident
            entries.append(entry)
    if not entries:
        raise ValueError('game_types 字典为空，保留已有字典。')
    with connection:
        connection.execute('DELETE FROM igdb_game_types')
        connection.executemany('INSERT INTO igdb_game_types VALUES(?,?,?,?)',
            [(e['id'], e['type'], type_key(e['type']), utc_now()) for e in entries])
        # Backfill in the same transaction. migrate() is not called here.
        if refresh_records:
            for row in connection.execute('SELECT igdb_id,raw_json FROM igdb_games').fetchall():
                backfill_record(connection, row['igdb_id'], json.loads(row['raw_json']))
    return len(entries)


def filter_sql(year=2025, scope='default', platform_id=None, genre_id=None,
               mode_id=None, min_rating=None, min_rating_count=None, game_type=None, q=None):
    if scope not in ('default', 'all', 'unknown'):
        raise ValueError('scope 必须为 default、all 或 unknown。')
    start, end = boundaries(year)
    conditions, params = ['g.first_release_date >= ?', 'g.first_release_date < ?'], [start, end]
    if scope == 'default':
        conditions.append('g.game_type_key IN (?,?,?,?)'); params.extend(DEFAULT_TYPES)
    elif scope == 'unknown':
        conditions.append("g.game_type_key='unknown'")
    for kind, ident in [('platform', platform_id), ('genre', genre_id), ('mode', mode_id)]:
        if ident is not None:
            conditions.append('EXISTS(SELECT 1 FROM game_tags t WHERE t.igdb_id=g.igdb_id AND t.kind=? AND t.tag_id=?)')
            params.extend((kind, ident))
    if min_rating is not None:
        if not 0 <= min_rating <= 100:
            raise ValueError('最低用户评分必须在 0–100 之间。')
        conditions.append('g.rating >= ?'); params.append(min_rating)
    if min_rating_count is not None:
        if min_rating_count < 0:
            raise ValueError('最低评分人数不能小于 0。')
        conditions.append('g.rating IS NOT NULL AND g.rating_count >= ?'); params.append(min_rating_count)
    if game_type is not None:
        if game_type not in LABELS:
            raise ValueError('未知的条目类别。')
        conditions.append('g.game_type_key=?'); params.append(game_type)
    if q and q.strip():
        # Literal substring matching: % and _ are not wildcard characters.
        conditions.append('instr(lower(g.name),lower(?)) > 0'); params.append(q.strip())
    return ' AND '.join(conditions), params


def select_games(connection, year=2025, scope='default', platform_id=None, genre_id=None,
                 mode_id=None, min_rating=None, min_rating_count=None):
    where, params = filter_sql(year, scope, platform_id, genre_id, mode_id, min_rating, min_rating_count)
    return connection.execute('SELECT g.* FROM igdb_games g WHERE ' + where +
                              ' ORDER BY g.first_release_date,g.igdb_id', params).fetchall()


def export_classification(connection, output, year):
    rows = select_games(connection, year, 'all')
    counts = Counter(r['game_type_key'] for r in rows)
    report = {
        'year': year, 'schema_version': 2, 'total_records': len(rows),
        'default_types': list(DEFAULT_TYPES),
        'default_visible_count': sum(counts[k] for k in DEFAULT_TYPES),
        'optional_count': sum(v for k, v in counts.items() if k not in DEFAULT_TYPES and k != 'unknown'),
        'unknown_count': counts['unknown'], 'type_counts': dict(counts),
        'classification_sources': dict(Counter(r['classification_source'] for r in rows)),
        'dictionary_count': connection.execute('SELECT count(*) FROM igdb_game_types').fetchone()[0],
        'missing_modes': sum(not json.loads(r['game_modes_json']) for r in rows),
        'rating_present': sum(r['rating'] is not None for r in rows),
        'zero_rating_count_with_rating': sum(r['rating'] is not None and r['rating_count'] == 0 for r in rows),
        'parent_references_outside_local_catalog': sum(r['parent_game_id'] is not None and
            not connection.execute('SELECT 1 FROM igdb_games WHERE igdb_id=?', (r['parent_game_id'],)).fetchone() for r in rows),
    }
    reports, exports = output/'reports', output/'exports'
    reports.mkdir(parents=True, exist_ok=True); exports.mkdir(parents=True, exist_ok=True)
    report_path = reports/f'igdb_{year}_classification_report.json'
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    headers = ['igdb_id', 'name', 'game_type_id', 'game_type_key', 'game_type_label',
               'classification_source', 'default_visible', 'parent_game_id', 'version_parent_id',
               'game_status_id', 'legacy_status', 'game_modes', 'platforms', 'genres',
               'first_release_date_utc', 'rating', 'rating_count', 'aggregated_rating',
               'aggregated_rating_count', 'total_rating', 'total_rating_count']
    csv_path = exports/f'igdb_{year}_classified.csv'
    with csv_path.open('w', encoding='utf-8-sig', newline='') as file:
        writer = csv.writer(file); writer.writerow(headers)
        for row in rows:
            modes = json.loads(row['game_modes_json'])
            values = [row['igdb_id'], row['name'], row['game_type_id'], row['game_type_key'],
                      LABELS[row['game_type_key']], row['classification_source'],
                      row['game_type_key'] in DEFAULT_TYPES, row['parent_game_id'], row['version_parent_id'],
                      row['game_status_id'], row['legacy_status'],
                      '; '.join(str(m.get('name') or m.get('id', '')) if isinstance(m, dict) else str(m) for m in modes),
                      '; '.join(json.loads(row['platforms_json'])), '; '.join(json.loads(row['genres_json'])),
                      datetime.fromtimestamp(row['first_release_date'], timezone.utc).date().isoformat(),
                      *(row[k] for k in ('rating', 'rating_count', 'aggregated_rating', 'aggregated_rating_count', 'total_rating', 'total_rating_count'))]
            writer.writerow(["'"+v if isinstance(v, str) and v.lstrip().startswith(('=', '+', '-', '@')) else v for v in values])
    print(f"全部 {len(rows)} 条；默认展示 {report['default_visible_count']} 条；可选 {report['optional_count']} 条；待分类 {report['unknown_count']} 条。")
    print('Report:', report_path)
    print('CSV:', csv_path)
    return report


def backup_database(path, label='classification'):
    from contextlib import closing
    import re

    path = Path(path)
    backup_dir = path.parent / 'backups'
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    target = backup_dir / f'igdb_before_{label}_{stamp}.sqlite3'
    partial = target.with_suffix('.sqlite3.partial')

    try:
        with closing(sqlite3.connect(
            path.resolve().as_uri() + '?mode=ro', uri=True
        )) as source:
            with closing(sqlite3.connect(partial)) as destination:
                source.backup(destination)
                result = destination.execute('PRAGMA quick_check').fetchall()
                if result != [('ok',)]:
                    raise RuntimeError(
                        'Backup verification failed; old backups retained.'
                    )

        # 数据库连接全部关闭后，再将临时文件转为正式备份。
        partial.replace(target)
    except Exception:
        try:
            partial.unlink(missing_ok=True)
        except OSError:
            pass
        raise

    print('Backup:', target)

    if label == 'ign':
        pattern = r'igdb_before_ign_\d{8}T\d{12}Z\.sqlite3'
        previous = sorted(
            (
                p for p in backup_dir.glob('igdb_before_ign_*.sqlite3')
                if p != target and p.is_file() and not p.is_symlink()
                and re.fullmatch(pattern, p.name)
            ),
            key=lambda p: p.name,
            reverse=True,
        )

        # 保留本次新备份，以及最近两份旧备份。
        for old in previous[2:]:
            try:
                old.unlink()
                print('Removed old IGN backup:', old.name)
            except OSError as error:
                print('Backup cleanup warning:', old.name, error)

    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--year', type=int, default=2025)
    parser.add_argument('--data-dir', type=Path, default=ROOT/'data')
    parser.add_argument('--env-file', type=Path, default=ROOT/'.env')
    parser.add_argument('--sync-types', action='store_true', help='Fetch game_types dictionary only; never re-fetch games')
    args = parser.parse_args()
    if not 1950 <= args.year <= 2100:
        parser.error('年份必须在 1950–2100 之间。')
    path = args.data_dir/'igdb.sqlite3'
    if not path.is_file():
        print('找不到已有 igdb.sqlite3，请检查项目路径。'); return 1
    try:
        backup_database(path)
        connection = initialize(path)
        try:
            migrate(connection)
            if args.sync_types:
                load_env(args.env_file)
                client_id = os.environ.get('IGDB_CLIENT_ID', '').strip()
                secret = os.environ.get('IGDB_CLIENT_SECRET', '').strip()
                if not client_id or not secret:
                    raise ValueError('请先在本地配置 IGDB 凭据。')
                with IGDBClient(client_id, secret) as api:
                    sync_types(api, connection)
            report = export_classification(connection, args.data_dir, args.year)
            if report['unknown_count']:
                print('待分类记录仍保留，可用 scope=unknown/all 查询；不猜测为游戏本体。')
        finally:
            connection.close()
        return 0
    except (APIError, ValueError, TypeError, OSError, sqlite3.Error) as exc:
        print('ERROR:', str(exc)); return 1


if __name__ == '__main__':
    raise SystemExit(main())
