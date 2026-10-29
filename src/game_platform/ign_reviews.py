"""Local IGN import and reviewable IGDB matching. No network requests."""
from __future__ import annotations

import argparse
import csv
import difflib
import json
import math
import re
import sqlite3
import unicodedata
import zipfile
from contextlib import nullcontext
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from xml.etree import ElementTree as ET

from .classify_games import DEFAULT_TYPES, backup_database
from .collect_igdb import ROOT, initialize, utc_now

HEADERS = {
    'name': ('name', '游戏名称'), 'score': ('score', 'IGN评分'),
    'review_url': ('review_url', '评测链接'), 'ign_game_url': ('ign_game_url', 'game_url', '游戏链接'),
    'platforms': ('platforms', '平台（页面所列）', '平台（含来源核验补充）'),
    'us_release_date': ('us_release_date', '美区最早发售日期（非预计）'),
    'review_date': ('review_date', '评测日期'), 'reviewed_on': ('reviewed_on', '评测平台'),
    'scope': ('scope', '评测分项'), 'title': ('title', '评测标题'), 'verdict': ('verdict', '评价摘要'),
    'genres': ('genres', '类型'),
}
NS = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}


def ign_url(value, kind):
    if not isinstance(value, str):
        raise ValueError('IGN 链接缺失。')
    parts = urlsplit(value.strip())
    if parts.scheme not in ('https', 'http') or parts.hostname not in ('www.ign.com', 'ign.com') or parts.username or parts.password or parts.port:
        raise ValueError('链接必须是 IGN 官方网页。')
    path = parts.path.rstrip('/')
    pattern = '/'+kind+r'/[A-Za-z0-9._~%+-]+'
    if kind == 'articles':
        pattern = r'/articles/(?:(\d{4})/(\d{2})/(\d{2})/)?[A-Za-z0-9._~%+-]+'
    match = re.fullmatch(pattern, path)
    if not match:
        raise ValueError(f'IGN 链接必须指向 /{kind}/ 下的具体页面。')
    if kind == 'articles' and match.group(1):
        try:
            date(*map(int, match.groups()))
        except ValueError:
            raise ValueError('IGN 旧评测链接的日期路径无效。') from None
    return urlunsplit(('https', 'www.ign.com', path, '', ''))


def date_value(value, excel_1904=False):
    if value is None or str(value).strip() == '':
        return None
    text = str(value).strip()
    try:
        if re.fullmatch(r'\d+(\.\d+)?', text):
            base = datetime(1904, 1, 1) if excel_1904 else datetime(1899, 12, 30)
            result = (base+timedelta(days=float(text))).date()
        else:
            result = date.fromisoformat(text[:10])
        if not 1950 <= result.year <= 2100:
            raise ValueError
        return result.isoformat()
    except (ValueError, OverflowError):
        raise ValueError(f'无效日期：{text}') from None


def review_scope(url):
    slug = url.rsplit('/', 1)[-1].lower()
    for tokens, label in [(('single-player-campaign', 'campaign-review'), '单人战役'),
                          (('multiplayer',), '多人'), (('zombies',), '僵尸模式'),
                          (('early-access',), '抢先体验'), (('dlc',), 'DLC')]:
        if any(t in slug for t in tokens):
            return label
    return '一般评测'


def platform_key(value):
    value = re.sub(r'[^a-z0-9]', '', str(value).casefold())
    return {'pcmicrosoftwindows': 'pc', 'windows': 'pc', 'steam': 'pc',
            'ps5': 'playstation5', 'ps4': 'playstation4', 'switch': 'nintendoswitch',
            'xboxseriesxs': 'xboxseries', 'xboxseriesx': 'xboxseries', 'xboxseriess': 'xboxseries',
            'iphone': 'ios', 'ipad': 'ios', 'macos': 'mac'}.get(value, value)


def name_key(value):
    text = unicodedata.normalize('NFKD', value.casefold())
    return ''.join(c for c in text if c.isalnum() and not unicodedata.combining(c))


def read_rows(path):
    if path.suffix.lower() == '.csv':
        with path.open(encoding='utf-8-sig', newline='') as file:
            reader = csv.DictReader(file)
            return list(reader), reader.fieldnames or [], False
    if path.suffix.lower() != '.xlsx':
        raise ValueError('只支持评测明细 CSV 或 XLSX。')
    with zipfile.ZipFile(path) as archive:
        if sum(i.file_size for i in archive.infolist()) > 256*1024*1024:
            raise ValueError('Excel 解压后过大，停止读取。')
        strings = []
        if 'xl/sharedStrings.xml' in archive.namelist():
            strings = [''.join(t.text or '' for t in e.findall('.//s:t', NS)) for e in ET.fromstring(archive.read('xl/sharedStrings.xml'))]
        workbook = ET.fromstring(archive.read('xl/workbook.xml'))
        props = workbook.find('s:workbookPr', NS)
        is_1904 = props is not None and props.get('date1904') in ('1', 'true')
        rels = {r.get('Id'): r.get('Target') for r in ET.fromstring(archive.read('xl/_rels/workbook.xml.rels'))}
        sheets = list(workbook.findall('s:sheets/s:sheet', NS))
        sheets.sort(key=lambda s: s.get('name') not in ('评测明细', 'IGN评测'))
        for sheet in sheets:
            target = rels[sheet.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id')]
            location = target.lstrip('/') if target.startswith('/') else 'xl/'+target
            rows = []
            for row in ET.fromstring(archive.read(location)).findall('s:sheetData/s:row', NS):
                cells = {}
                for cell in row.findall('s:c', NS):
                    letters = re.match(r'[A-Z]+', cell.get('r', 'A1')).group()
                    index = 0
                    for char in letters:
                        index = index*26+ord(char)-64
                    value = cell.find('s:v', NS)
                    value = value.text if value is not None else ''
                    if cell.get('t') == 's':
                        value = strings[int(value)]
                    elif cell.get('t') == 'inlineStr':
                        value = ''.join(t.text or '' for t in cell.findall('.//s:t', NS))
                    cells[index-1] = value
                rows.append([cells.get(n, '') for n in range(max(cells, default=-1)+1)])
            if not rows:
                continue
            headers = rows[0]
            if any(h in headers for h in HEADERS['review_url']):
                return [dict(zip(headers, row+['']*max(0, len(headers)-len(row)))) for row in rows[1:] if any(row)], headers, is_1904
    raise ValueError('Excel 中没有评测明细；请使用 IGN评测 或 评测明细 工作表。')


def read_import(path):
    rows, headers, is_1904 = read_rows(path)
    for field in ('name', 'score', 'review_url', 'ign_game_url'):
        if not any(h in headers for h in HEADERS[field]):
            raise ValueError(f'缺少 {field} 列；请使用评测明细，不是游戏汇总表。')
    records, excluded, seen = [], 0, {}
    exclusions = []
    excluded_hardware = deferred = 0
    for number, raw in enumerate(rows, 2):
        def get(field):
            return next((raw.get(h) for h in HEADERS[field] if h in raw), '')
        try:
            platforms = [p.strip() for p in str(get('platforms') or '').split(';') if p.strip()]
            genres = {g.strip().casefold() for g in str(get('genres') or '').split(';') if g.strip()}
            article_slug = str(get('review_url') or '').rstrip('/').rsplit('/', 1)[-1].casefold()
            game_path = str(get('ign_game_url') or '').casefold()
            reason = None
            if article_slug in {'dropmix-review', 'nintendo-labo-vr-kit-review'}:
                reason = '待确认：实体组件与软件结合的混合产品，本批暂缓导入'
                deferred += 1
            elif 'hardware' in genres or article_slug in {
                    'snes-classic-edition-review', 'game-and-watch-legend-of-zelda-edition-review'}:
                reason = '硬件评测'
                excluded_hardware += 1
            elif (any(platform_key(p) == 'tabletop' for p in platforms)
                  or 'board-game' in game_path or 'board game' in genres):
                reason = '桌游或实体卡牌评测，含混合平台记录'
                excluded += 1
            if reason:
                exclusions.append({'source_row': number, 'name': str(get('name') or ''),
                                   'review_url': str(get('review_url') or ''), 'reason': reason})
                continue
            name = str(get('name') or '').strip()
            if not name:
                raise ValueError('缺少游戏名称。')
            review_url = ign_url(get('review_url'), 'articles')
            game_url = ign_url(get('ign_game_url'), 'games')
            value = get('score')
            score = float(value) if value is not None and str(value).strip() else None
            if score is not None and (not math.isfinite(score) or not 0 <= score <= 10):
                raise ValueError('IGN 评分必须在0～10之间。')
            record = {'name': name, 'score': score, 'review_url': review_url, 'ign_game_url': game_url,
                      'platforms': platforms, 'us_release_date': date_value(get('us_release_date'), is_1904),
                      'review_date': date_value(get('review_date'), is_1904),
                      'reviewed_on': str(get('reviewed_on') or '').strip() or None,
                      'scope': str(get('scope') or '').strip() or review_scope(review_url),
                      'title': str(get('title') or '').strip() or None,
                      'verdict': str(get('verdict') or '').strip() or None,
                      'raw_json': json.dumps(raw, ensure_ascii=False)}
            previous = seen.get(review_url)
            if previous is not None:
                if any(previous[k] != record[k] for k in record if k != 'raw_json'):
                    raise ValueError('同一评测URL存在冲突内容。')
                continue
            seen[review_url] = record
            records.append(record)
        except (ValueError, TypeError) as exc:
            raise ValueError(f'第{number}行：{exc}') from None
    return records, {'input_rows': len(rows), 'video_reviews': len(records), 'excluded_tabletop': excluded,
                     'excluded_hardware': excluded_hardware, 'deferred_reviews': deferred,
                     'exclusions': exclusions,
                     'duplicate_rows': len(rows)-excluded-excluded_hardware-deferred-len(records)}


def migrate(connection):
    if not connection.execute('SELECT 1 FROM schema_versions WHERE version=2').fetchone():
        raise ValueError('请先完成分类字段迁移。')
    with connection:
        connection.execute('BEGIN IMMEDIATE')
        connection.execute('''CREATE TABLE IF NOT EXISTS ign_reviews(
            review_id INTEGER PRIMARY KEY, review_url TEXT NOT NULL UNIQUE,
            ign_game_url TEXT NOT NULL, name TEXT NOT NULL, scope TEXT NOT NULL,
            score REAL CHECK(score IS NULL OR score BETWEEN 0 AND 10),
            platforms_json TEXT NOT NULL, us_release_date TEXT, review_date TEXT, reviewed_on TEXT,
            title TEXT, verdict TEXT, raw_json TEXT NOT NULL, imported_at TEXT NOT NULL, source_file TEXT NOT NULL)''')
        connection.execute('CREATE INDEX IF NOT EXISTS ix_ign_game_url ON ign_reviews(ign_game_url)')
        connection.execute('''CREATE TABLE IF NOT EXISTS ign_links(
            ign_game_url TEXT PRIMARY KEY, igdb_id INTEGER NOT NULL REFERENCES igdb_games(igdb_id),
            method TEXT NOT NULL, confirmed_at TEXT NOT NULL)''')
        connection.execute('CREATE INDEX IF NOT EXISTS ix_ign_link_game ON ign_links(igdb_id)')
        connection.execute('''CREATE TABLE IF NOT EXISTS ign_link_events(
            event_id INTEGER PRIMARY KEY, ign_game_url TEXT NOT NULL, old_igdb_id INTEGER,
            new_igdb_id INTEGER, method TEXT NOT NULL, changed_at TEXT NOT NULL)''')
        connection.execute('INSERT OR IGNORE INTO schema_versions VALUES(3,?)', (utc_now(),))
        connection.execute('''CREATE TABLE IF NOT EXISTS ign_review_links(
            review_url TEXT PRIMARY KEY REFERENCES ign_reviews(review_url),
            igdb_id INTEGER NOT NULL REFERENCES igdb_games(igdb_id),
            method TEXT NOT NULL, confirmed_at TEXT NOT NULL, reason TEXT NOT NULL)''')
        connection.execute('CREATE INDEX IF NOT EXISTS ix_ign_review_link_game ON ign_review_links(igdb_id)')
        connection.execute('''CREATE TABLE IF NOT EXISTS ign_review_link_events(
            event_id INTEGER PRIMARY KEY, review_url TEXT NOT NULL, old_igdb_id INTEGER,
            new_igdb_id INTEGER, method TEXT NOT NULL, reason TEXT NOT NULL, changed_at TEXT NOT NULL)''')
        connection.execute('''CREATE VIEW IF NOT EXISTS ign_resolved_reviews AS
            SELECT r.*,COALESCE(a.igdb_id,l.igdb_id) AS resolved_igdb_id,
                CASE WHEN a.igdb_id IS NOT NULL THEN 'article'
                     WHEN l.igdb_id IS NOT NULL THEN 'game' ELSE NULL END AS association_scope
            FROM ign_reviews r LEFT JOIN ign_review_links a USING(review_url)
            LEFT JOIN ign_links l USING(ign_game_url)''')
        connection.execute('INSERT OR IGNORE INTO schema_versions VALUES(4,?)', (utc_now(),))
        connection.execute('''CREATE TABLE IF NOT EXISTS ign_review_bindings(
            review_url TEXT PRIMARY KEY REFERENCES ign_reviews(review_url),
            scope_override TEXT, method TEXT NOT NULL, confirmed_at TEXT NOT NULL,
            reason TEXT NOT NULL)''')
        connection.execute('''CREATE TABLE IF NOT EXISTS ign_review_binding_targets(
            review_url TEXT NOT NULL REFERENCES ign_review_bindings(review_url) ON DELETE CASCADE,
            igdb_id INTEGER NOT NULL REFERENCES igdb_games(igdb_id),
            PRIMARY KEY(review_url,igdb_id))''')
        connection.execute('CREATE INDEX IF NOT EXISTS ix_ign_binding_game ON ign_review_binding_targets(igdb_id)')
        connection.execute('''CREATE TABLE IF NOT EXISTS ign_review_binding_events(
            event_id INTEGER PRIMARY KEY, review_url TEXT NOT NULL,
            old_binding_json TEXT, new_binding_json TEXT, method TEXT NOT NULL,
            reason TEXT NOT NULL, changed_at TEXT NOT NULL)''')
        # Each row is an effective article-to-game edge. An explicit set replaces
        # earlier single-article/group assignments; it never inherits extra games.
        # Keep the schema-4 view unchanged for legacy tools (single-target only).
        connection.execute('''CREATE VIEW IF NOT EXISTS ign_effective_review_targets AS
            SELECT t.review_url,t.igdb_id,'binding' AS association_scope
            FROM ign_review_binding_targets t
            UNION ALL
            SELECT a.review_url,a.igdb_id,'article' FROM ign_review_links a
            WHERE NOT EXISTS(SELECT 1 FROM ign_review_bindings b WHERE b.review_url=a.review_url)
            UNION ALL
            SELECT r.review_url,l.igdb_id,'game' FROM ign_reviews r
            JOIN ign_links l USING(ign_game_url)
            WHERE NOT EXISTS(SELECT 1 FROM ign_review_bindings b WHERE b.review_url=r.review_url)
            AND NOT EXISTS(SELECT 1 FROM ign_review_links a WHERE a.review_url=r.review_url)''')
        connection.execute('INSERT OR IGNORE INTO schema_versions VALUES(5,?)', (utc_now(),))


def has_article_links(connection):
    return connection.execute('SELECT 1 FROM schema_versions WHERE version=4').fetchone() is not None


def has_bindings(connection):
    return connection.execute('SELECT 1 FROM schema_versions WHERE version=5').fetchone() is not None


def resolved_reviews(connection):
    """One row per source article. Multi-target articles have no scalar target."""
    if has_bindings(connection):
        targets = defaultdict(list)
        scopes = {}
        for row in connection.execute('SELECT * FROM ign_effective_review_targets ORDER BY igdb_id'):
            targets[row['review_url']].append(row['igdb_id'])
            scopes[row['review_url']] = row['association_scope']
        output = []
        for row in connection.execute('''SELECT r.*,b.scope_override FROM ign_reviews r
                LEFT JOIN ign_review_bindings b USING(review_url) ORDER BY review_id'''):
            r = dict(row)
            ids = targets[r['review_url']]
            r.update(source_scope=r['scope'], scope=r['scope_override'] or r['scope'],
                     resolved_igdb_ids=ids, resolved_igdb_id=ids[0] if len(ids) == 1 else None,
                     association_scope=scopes.get(r['review_url']))
            output.append(r)
        return output
    if has_article_links(connection):
        rows = connection.execute('SELECT * FROM ign_resolved_reviews ORDER BY review_id')
    else:
        rows = connection.execute('''SELECT r.*,l.igdb_id AS resolved_igdb_id,
            CASE WHEN l.igdb_id IS NOT NULL THEN 'game' ELSE NULL END AS association_scope
            FROM ign_reviews r LEFT JOIN ign_links l USING(ign_game_url) ORDER BY review_id''')
    return [dict(r, resolved_igdb_ids=[] if r['resolved_igdb_id'] is None else [r['resolved_igdb_id']],
                 source_scope=r['scope']) for r in rows]


def import_records(connection, records, source_file, *, commit=True):
    with connection if commit else nullcontext():
        for r in records:
            connection.execute('''INSERT INTO ign_reviews(review_url,ign_game_url,name,scope,score,platforms_json,
                us_release_date,review_date,reviewed_on,title,verdict,raw_json,imported_at,source_file)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(review_url) DO UPDATE SET
                ign_game_url=excluded.ign_game_url,name=excluded.name,
                scope=CASE WHEN excluded.scope='一般评测' AND ign_reviews.scope<>'一般评测'
                    THEN ign_reviews.scope ELSE excluded.scope END,score=excluded.score,
                platforms_json=excluded.platforms_json,us_release_date=excluded.us_release_date,
                review_date=excluded.review_date,reviewed_on=COALESCE(excluded.reviewed_on,ign_reviews.reviewed_on),
                title=COALESCE(excluded.title,ign_reviews.title),verdict=COALESCE(excluded.verdict,ign_reviews.verdict),
                raw_json=excluded.raw_json,imported_at=excluded.imported_at,source_file=excluded.source_file''',
                (r['review_url'], r['ign_game_url'], r['name'], r['scope'], r['score'], json.dumps(r['platforms'], ensure_ascii=False),
                 r['us_release_date'], r['review_date'], r['reviewed_on'], r['title'], r['verdict'], r['raw_json'], utc_now(), source_file))


def candidates(connection, *, game_urls=None):
    games, index, keys = {}, defaultdict(set), {}
    for row in connection.execute('SELECT * FROM igdb_games'):
        game = dict(row)
        raw = json.loads(game['raw_json'])
        aliases = [a['name'] for a in raw.get('alternative_names') or [] if isinstance(a, dict) and isinstance(a.get('name'), str)]
        games[game['igdb_id']] = game
        keys[game['igdb_id']] = name_key(game['name'])
        for name in [game['name'], *aliases]:
            key = name_key(name)
            if key:
                index[key].add(game['igdb_id'])
    groups = defaultdict(list)
    for row in resolved_reviews(connection):
        if game_urls is not None and row['ign_game_url'] not in game_urls:
            continue
        groups[row['ign_game_url']].append(dict(row))
    existing = {r['ign_game_url']: r['igdb_id'] for r in connection.execute('SELECT * FROM ign_links')}
    output = []
    for url, reviews in groups.items():
        # Explicit article assignments do not supply evidence for a fallback
        # game-group match. Fully resolved groups retain candidates for audit.
        source_reviews = [r for r in reviews if r['association_scope'] not in ('article', 'binding')] or reviews
        names = {name_key(r['name']) for r in source_reviews}
        exact = set().union(*(index.get(k, set()) for k in names))
        matches = exact
        if not matches:
            near = {k for name in names for k in difflib.get_close_matches(name, index.keys(), n=5, cutoff=.84)}
            matches = set().union(*(index[k] for k in near)) if near else set()
        source_platforms = {platform_key(p) for r in source_reviews for p in json.loads(r['platforms_json'])}
        release_dates = {r['us_release_date'] for r in source_reviews if r['us_release_date']}
        options = []
        for ident in matches:
            game = games[ident]
            platform_overlap = sorted(source_platforms & {platform_key(p) for p in json.loads(game['platforms_json'])})
            released = (datetime.fromtimestamp(game['first_release_date'], timezone.utc).date()
                        if game['first_release_date'] is not None else None)
            days = min((abs((released-date.fromisoformat(d)).days) for d in release_dates), default=None) if released else None
            similarity = max(difflib.SequenceMatcher(None, k, keys[ident]).ratio() for k in names)
            method = ('name_exact' if keys[ident] in names else 'alias_exact') if ident in exact else 'fuzzy'
            eligible = len(exact) == 1 and ident in exact and bool(platform_overlap) and days is not None and days <= 7 and game['game_type_key'] in DEFAULT_TYPES
            options.append({'igdb_id': ident, 'name': game['name'], 'game_type': game['game_type_key'],
                            'platforms': json.loads(game['platforms_json']), 'release_date': released.isoformat() if released else None,
                            'match_method': method, 'name_similarity': round(similarity, 4),
                            'platform_overlap': platform_overlap, 'release_day_difference': days, 'eligible_exact': eligible})
        options.sort(key=lambda o: (not o['eligible_exact'], o['match_method'] == 'fuzzy', not bool(o['platform_overlap']),
                                    -o['name_similarity'], o['release_day_difference'] if o['release_day_difference'] is not None else 99999, o['igdb_id']))
        linked_count = sum(bool(r['resolved_igdb_ids']) for r in reviews)
        targets = sorted({ident for r in reviews for ident in r['resolved_igdb_ids']})
        status = ('unlinked' if not linked_count else 'partial' if linked_count < len(reviews)
                  else 'split' if len(targets) > 1 else 'linked')
        output.append({'ign_game_url': url, 'ign_name': reviews[0]['name'], 'review_count': len(reviews),
                       'linked_igdb_id': existing.get(url), 'exact_candidate_count': len(exact),
                       'linked_review_count': linked_count, 'unlinked_review_count': len(reviews)-linked_count,
                       'fully_linked': linked_count == len(reviews), 'link_status': status,
                       'linked_igdb_ids': targets,
                       'review_associations': [{'review_url': r['review_url'], 'score': r['score'],
                           'scope': r['scope'], 'igdb_id': r['resolved_igdb_id'],
                           'igdb_ids': r['resolved_igdb_ids'], 'source_scope': r['source_scope'],
                           'association_scope': r['association_scope']} for r in reviews],
                       'candidates': options[:5], 'eligible_igdb_id': next((o['igdb_id'] for o in options if o['eligible_exact']), None)})
    return output


def apply_links(connection, actions, method, replace=False):
    # Validate every row before beginning any changes.
    seen = set()
    for url, target in actions:
        if url in seen:
            raise ValueError('确认文件中同一IGN游戏出现多次。')
        seen.add(url)
        if not connection.execute('SELECT 1 FROM ign_reviews WHERE ign_game_url=?', (url,)).fetchone():
            raise ValueError('确认文件包含尚未导入的 IGN 游戏。')
        if target is not None and not connection.execute('SELECT 1 FROM igdb_games WHERE igdb_id=?', (target,)).fetchone():
            raise ValueError(f'本地未收录 IGDB ID {target}。')
        old = connection.execute('SELECT igdb_id FROM ign_links WHERE ign_game_url=?', (url,)).fetchone()
        if old and target is not None and old['igdb_id'] != target and not replace:
            raise ValueError('已有不同关联；确认需要改绑时使用 --replace。')
    changed = 0
    with connection:
        for url, target in actions:
            old = connection.execute('SELECT igdb_id FROM ign_links WHERE ign_game_url=?', (url,)).fetchone()
            previous = old['igdb_id'] if old else None
            if previous == target:
                continue
            if target is None:
                connection.execute('DELETE FROM ign_links WHERE ign_game_url=?', (url,))
            else:
                connection.execute('''INSERT INTO ign_links VALUES(?,?,?,?) ON CONFLICT(ign_game_url)
                    DO UPDATE SET igdb_id=excluded.igdb_id,method=excluded.method,confirmed_at=excluded.confirmed_at''', (url, target, method, utc_now()))
            connection.execute('INSERT INTO ign_link_events(ign_game_url,old_igdb_id,new_igdb_id,method,changed_at) VALUES(?,?,?,?,?)', (url, previous, target, method, utc_now()))
            changed += 1
    return changed


def confirm_actions(path):
    with path.open(encoding='utf-8-sig', newline='') as file:
        reader = csv.DictReader(file)
        if not {'ign_game_url', 'igdb_id', 'decision'}.issubset(reader.fieldnames or []):
            raise ValueError('确认CSV必须含 ign_game_url、igdb_id、decision。')
        actions = []
        for row in reader:
            decision = (row.get('decision') or '').strip().lower()
            if decision in ('', 'skip', '跳过'):
                continue
            if decision not in ('link', '关联', 'unlink', '解除'):
                raise ValueError('decision 必须为 link/关联、skip/跳过 或 unlink/解除。')
            url = ign_url(row['ign_game_url'], 'games')
            target = None if decision in ('unlink', '解除') else int(row['igdb_id'])
            if target is not None and not 1 <= target <= 9223372036854775807:
                raise ValueError('IGDB ID 必须为正整数。')
            actions.append((url, target))
        return actions


def review_confirm_actions(path):
    """Read explicit per-article assignments, with optional evidence guards."""
    with path.open(encoding='utf-8-sig', newline='') as file:
        reader = csv.DictReader(file)
        if not {'review_url', 'igdb_id', 'decision'}.issubset(reader.fieldnames or []):
            raise ValueError('文章确认CSV必须含 review_url、igdb_id、decision。')
        actions = []
        for row in reader:
            decision = (row.get('decision') or '').strip().lower()
            if decision in ('', 'skip', '跳过'):
                continue
            if decision not in ('link', '关联', 'unlink', '解除'):
                raise ValueError('decision 必须为 link、skip 或 unlink。')
            target = None if decision in ('unlink', '解除') else int(row['igdb_id'])
            if target is not None and not 1 <= target <= 9223372036854775807:
                raise ValueError('IGDB ID 必须为正整数。')
            action = {'review_url': ign_url(row['review_url'], 'articles'), 'igdb_id': target,
                      'reason': (row.get('reason') or '').strip() or 'Manual article confirmation'}
            if row.get('expected_ign_game_url'):
                action['expected_ign_game_url'] = ign_url(row['expected_ign_game_url'], 'games')
            if row.get('expected_score'):
                score = float(row['expected_score'])
                if not math.isfinite(score) or not 0 <= score <= 10:
                    raise ValueError('核验评分必须在0～10之间。')
                action['expected_score'] = score
            if row.get('expected_review_date'):
                action['expected_review_date'] = date_value(row['expected_review_date'])
            if row.get('expected_igdb_name'):
                action['expected_igdb_name'] = row['expected_igdb_name'].strip()
            if row.get('expected_parent_game_id'):
                action['expected_parent_game_id'] = int(row['expected_parent_game_id'])
            actions.append(action)
        return actions


def apply_review_links(connection, actions, method, replace=False):
    """An article assignment takes priority over its IGN game-group fallback.

    unlink removes the article override and restores the group fallback, if any.
    It does not suppress a review or alter source metadata.
    """
    changed = 0
    with connection:
        connection.execute('BEGIN IMMEDIATE')
        seen = set()
        # Validate the whole batch under the same write transaction before writing.
        for action in actions:
            url, target = action['review_url'], action['igdb_id']
            if has_bindings(connection) and connection.execute(
                    'SELECT 1 FROM ign_review_bindings WHERE review_url=?', (url,)).fetchone():
                raise ValueError('该评测已有版本/联合关联，请使用 confirm-bindings 修改或 restore 恢复旧关联。')
            if url in seen:
                raise ValueError('文章确认文件中同一评测出现多次。')
            seen.add(url)
            review = connection.execute('SELECT * FROM ign_reviews WHERE review_url=?', (url,)).fetchone()
            if review is None:
                raise ValueError('文章确认文件包含尚未导入的评测。')
            for field in ('ign_game_url', 'score', 'review_date'):
                guard = 'expected_'+field
                if guard in action and review[field] != action[guard]:
                    raise ValueError(f'评测 {url} 的 {field} 与审核依据不同，停止关联。')
            if target is not None:
                game = connection.execute('SELECT * FROM igdb_games WHERE igdb_id=?', (target,)).fetchone()
                if game is None:
                    raise ValueError(f'本地未收录 IGDB ID {target}。')
                if 'expected_igdb_name' in action and game['name'] != action['expected_igdb_name']:
                    raise ValueError('目标游戏名称与审核依据不同，停止关联。')
                if 'expected_parent_game_id' in action:
                    raw = json.loads(game['raw_json'])
                    if raw.get('parent_game') != action['expected_parent_game_id']:
                        raise ValueError('目标 DLC 的本体关系与审核依据不同，停止关联。')
            old = connection.execute('SELECT igdb_id FROM ign_review_links WHERE review_url=?', (url,)).fetchone()
            if old and target is not None and old['igdb_id'] != target and not replace:
                raise ValueError('已有不同文章关联；确认需要改绑时使用 --replace。')
        for action in actions:
            url, target = action['review_url'], action['igdb_id']
            old = connection.execute('SELECT igdb_id FROM ign_review_links WHERE review_url=?', (url,)).fetchone()
            previous = old['igdb_id'] if old else None
            if previous == target:
                continue
            now = utc_now()
            if target is None:
                connection.execute('DELETE FROM ign_review_links WHERE review_url=?', (url,))
            else:
                connection.execute('''INSERT INTO ign_review_links VALUES(?,?,?,?,?)
                    ON CONFLICT(review_url) DO UPDATE SET igdb_id=excluded.igdb_id,
                    method=excluded.method,confirmed_at=excluded.confirmed_at,reason=excluded.reason''',
                    (url, target, method, now, action['reason']))
            connection.execute('''INSERT INTO ign_review_link_events
                (review_url,old_igdb_id,new_igdb_id,method,reason,changed_at) VALUES(?,?,?,?,?,?)''',
                (url, previous, target, method, action['reason'], now))
            changed += 1
    return changed


def binding_actions(path):
    """Strict, reviewable JSON input; target identity guards are mandatory."""
    value = json.loads(path.read_text(encoding='utf-8-sig'))
    if not isinstance(value, dict) or value.get('format_version') != 1 or not isinstance(value.get('bindings'), list):
        raise ValueError('关联JSON必须含 format_version:1 和 bindings 数组。')
    actions, seen = [], set()
    for item in value['bindings']:
        if not isinstance(item, dict):
            raise ValueError('每条关联必须为对象。')
        action = dict(item)
        if set(action) - {'action', 'review_url', 'reason', 'expected_source', 'scope_override', 'targets'}:
            raise ValueError('关联包含未知字段，请检查字段拼写。')
        url = ign_url(action.get('review_url'), 'articles')
        if url in seen:
            raise ValueError('关联JSON中同一评测出现多次。')
        seen.add(url); action['review_url'] = url
        if action.get('action') not in ('link', 'restore'):
            raise ValueError('action 必须为 link 或 restore。')
        if not isinstance(action.get('reason'), str) or not action['reason'].strip():
            raise ValueError('关联必须填写 reason。')
        expected = action.get('expected_source')
        if not isinstance(expected, dict) or set(expected) != {'ign_game_url', 'score', 'review_date', 'scope'}:
            raise ValueError('expected_source 必须包含且仅包含 ign_game_url、score、review_date、scope。')
        expected = dict(expected)
        expected['ign_game_url'] = ign_url(expected['ign_game_url'], 'games')
        score = expected['score']
        if score is not None and (isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score) or not 0 <= score <= 10):
            raise ValueError('核验评分必须为0～10数字或null。')
        if expected['review_date'] is not None and date_value(expected['review_date']) != expected['review_date']:
            raise ValueError('核验日期必须使用 YYYY-MM-DD。')
        if not isinstance(expected['scope'], str) or not expected['scope'].strip():
            raise ValueError('核验分项必须为非空文字。')
        action['expected_source'] = expected
        label = action.get('scope_override')
        if label is not None and (not isinstance(label, str) or not label.strip() or len(label) > 80 or any(ord(c) < 32 for c in label)):
            raise ValueError('版本标签必须为1～80字文字或null。')
        targets = action.get('targets')
        if action['action'] == 'restore':
            if targets not in (None, []) or label is not None:
                raise ValueError('restore 仅移除新版关联并恢复先前规则，不接受 targets 或标签。')
        else:
            if not isinstance(targets, list) or not targets:
                raise ValueError('link 必须至少包含一个目标。')
            ids = set()
            for target in targets:
                fields = {'igdb_id', 'name', 'game_type_key', 'parent_game_id', 'version_parent_id', 'platforms'}
                if not isinstance(target, dict) or set(target) != fields:
                    raise ValueError('目标必须填写 igdb_id、name、game_type_key、parent_game_id、version_parent_id、platforms。')
                ident = target['igdb_id']
                if type(ident) is not int or not 1 <= ident <= 9223372036854775807 or ident in ids:
                    raise ValueError('目标ID无效或重复。')
                ids.add(ident)
                for key in ('name', 'game_type_key'):
                    if not isinstance(target[key], str) or not target[key].strip():
                        raise ValueError('目标名称和类型必须为非空文字。')
                for key in ('parent_game_id', 'version_parent_id'):
                    if target[key] is not None and (type(target[key]) is not int or not 1 <= target[key] <= 9223372036854775807):
                        raise ValueError('父游戏ID必须为正整数或null。')
                if not isinstance(target['platforms'], list) or not all(isinstance(p, str) for p in target['platforms']):
                    raise ValueError('目标平台必须为文字数组。')
        actions.append(action)
    return actions


def current_binding(connection, url):
    row = connection.execute('SELECT scope_override FROM ign_review_bindings WHERE review_url=?', (url,)).fetchone()
    if row is None:
        return None
    return {'igdb_ids': [r[0] for r in connection.execute(
        'SELECT igdb_id FROM ign_review_binding_targets WHERE review_url=? ORDER BY igdb_id', (url,))],
        'scope_override': row['scope_override']}


def apply_bindings(connection, actions, method, replace=False):
    """Validate the entire batch before changing any association or label."""
    changed = 0
    with connection:
        connection.execute('BEGIN IMMEDIATE')
        seen = set()
        prepared = []
        for action in actions:
            url = action['review_url']
            if url in seen:
                raise ValueError('关联文件中同一评测出现多次。')
            seen.add(url)
            review = connection.execute('SELECT * FROM ign_reviews WHERE review_url=?', (url,)).fetchone()
            if review is None:
                raise ValueError(f'尚未导入评测：{url}')
            for field, expected in action['expected_source'].items():
                if review[field] != expected:
                    raise ValueError(f'评测 {url} 的 {field} 与审核依据不同，整批停止。')
            desired = None
            if action['action'] == 'link':
                for target in action['targets']:
                    game = connection.execute('SELECT * FROM igdb_games WHERE igdb_id=?', (target['igdb_id'],)).fetchone()
                    if game is None:
                        raise ValueError(f"本地未收录 IGDB ID {target['igdb_id']}，整批停止。")
                    raw = json.loads(game['raw_json'])
                    if not isinstance(raw, dict) or raw.get('id') != target['igdb_id']:
                        raise ValueError('目标游戏原始资料ID不一致，整批停止。')
                    actual = {'name': game['name'], 'game_type_key': game['game_type_key'],
                              'parent_game_id': raw.get('parent_game'), 'version_parent_id': raw.get('version_parent'),
                              'platforms': sorted(json.loads(game['platforms_json']))}
                    for field, value in actual.items():
                        expected = sorted(target[field]) if field == 'platforms' else target[field]
                        if value != expected:
                            raise ValueError(f"IGDB {target['igdb_id']} 的 {field} 与审核依据不同，整批停止。")
                desired = {'igdb_ids': sorted(t['igdb_id'] for t in action['targets']),
                           'scope_override': action.get('scope_override')}
            old = current_binding(connection, url)
            if desired is not None and old != desired and not replace:
                effective = sorted(r[0] for r in connection.execute(
                    'SELECT igdb_id FROM ign_effective_review_targets WHERE review_url=?', (url,)))
                if old is not None or (effective and effective != desired['igdb_ids']):
                    raise ValueError('已有不同关联或标签；确认改绑后使用 --replace。')
            prepared.append((action, old, desired))
        for action, old, desired in prepared:
            if old == desired:
                continue
            url, now = action['review_url'], utc_now()
            connection.execute('DELETE FROM ign_review_binding_targets WHERE review_url=?', (url,))
            connection.execute('DELETE FROM ign_review_bindings WHERE review_url=?', (url,))
            if desired is not None:
                connection.execute('INSERT INTO ign_review_bindings VALUES(?,?,?,?,?)',
                    (url, desired['scope_override'], method, now, action['reason']))
                connection.executemany('INSERT INTO ign_review_binding_targets VALUES(?,?)',
                    [(url, ident) for ident in desired['igdb_ids']])
            connection.execute('''INSERT INTO ign_review_binding_events
                (review_url,old_binding_json,new_binding_json,method,reason,changed_at) VALUES(?,?,?,?,?,?)''',
                (url, json.dumps(old, ensure_ascii=False) if old is not None else None,
                 json.dumps(desired, ensure_ascii=False) if desired is not None else None,
                 method, action['reason'], now))
            changed += 1
    return changed


def write_csv(path, headers, rows):
    with path.open('w', encoding='utf-8-sig', newline='') as file:
        writer = csv.writer(file); writer.writerow(headers)
        for row in rows:
            writer.writerow(["'"+v if isinstance(v, str) and v.lstrip().startswith(('=', '+', '-', '@')) else v for v in row])


def report(connection, output, import_info=None):
    matches = candidates(connection)
    exports, reports = output/'exports', output/'reports'
    exports.mkdir(parents=True, exist_ok=True); reports.mkdir(parents=True, exist_ok=True)
    if import_info is not None:
        write_csv(exports/'ign_import_exclusions.csv', ['source_row', 'name', 'review_url', 'reason'],
                  [[r[k] for k in ('source_row', 'name', 'review_url', 'reason')]
                   for r in import_info.get('exclusions', [])])
        print(f"本批输入 {import_info['input_rows']} 行；待导入评测 {import_info['video_reviews']} 篇；"
              f"排除桌游 {import_info['excluded_tabletop']}、硬件 {import_info.get('excluded_hardware', 0)}；"
              f"暂缓 {import_info.get('deferred_reviews', 0)} 篇。")
    write_csv(exports/'ign_match_candidates.csv',
              ['ign_game_url', 'ign_name', 'igdb_id', 'igdb_name', 'match_method', 'platform_overlap', 'release_day_difference', 'eligible_exact'],
              [[g['ign_game_url'], g['ign_name'], o['igdb_id'], o['name'], o['match_method'], '; '.join(o['platform_overlap']), o['release_day_difference'], o['eligible_exact']] for g in matches for o in g['candidates']])
    write_csv(exports/'ign_link_confirmations_template.csv', ['ign_game_url', 'ign_name', 'igdb_id', 'decision'],
              [[g['ign_game_url'], g['ign_name'], g['eligible_igdb_id'], ''] for g in matches if not g['fully_linked']])
    overrides = ([dict(row) for row in connection.execute('''SELECT a.*,r.ign_game_url,r.score,r.scope,
        g.name AS igdb_name FROM ign_review_links a JOIN ign_reviews r USING(review_url)
        JOIN igdb_games g ON g.igdb_id=a.igdb_id ORDER BY a.review_url''')]
        if has_article_links(connection) else [])
    bindings = []
    if has_bindings(connection):
        binding_urls = set()
        for row in connection.execute('SELECT * FROM ign_review_bindings ORDER BY review_url'):
            binding = dict(row)
            binding.update(current_binding(connection, row['review_url']))
            bindings.append(binding); binding_urls.add(row['review_url'])
        overrides = [a for a in overrides if a['review_url'] not in binding_urls]
        overrides.extend(dict(row) for row in connection.execute('''SELECT b.*,t.igdb_id,
            g.name AS igdb_name,r.ign_game_url,r.score,COALESCE(b.scope_override,r.scope) AS scope
            FROM ign_review_bindings b JOIN ign_review_binding_targets t USING(review_url)
            JOIN ign_reviews r USING(review_url) JOIN igdb_games g ON g.igdb_id=t.igdb_id
            ORDER BY b.review_url,t.igdb_id'''))
    write_csv(exports/'ign_review_link_overrides.csv',
              ['review_url', 'ign_game_url', 'igdb_id', 'igdb_name', 'score', 'scope', 'reason'],
              [[a[k] for k in ('review_url', 'ign_game_url', 'igdb_id', 'igdb_name', 'score', 'scope', 'reason')]
               for a in overrides])
    data = {'schema_version': 5 if has_bindings(connection) else 4 if has_article_links(connection) else 3,
            'review_count': connection.execute('SELECT count(*) FROM ign_reviews').fetchone()[0],
            'ign_game_count': len(matches), 'linked_ign_games': sum(g['fully_linked'] for g in matches),
            'linked_reviews': sum(g['linked_review_count'] for g in matches),
            'unlinked_reviews': sum(g['unlinked_review_count'] for g in matches),
            'unlinked_ign_games': sum(not g['fully_linked'] for g in matches),
            'split_ign_games': sum(g['link_status'] == 'split' for g in matches),
            'article_link_count': len({a['review_url'] for a in overrides}), 'article_links': overrides,
            'article_target_count': len(overrides), 'review_bindings': bindings,
            'joint_review_count': sum(len(b['igdb_ids']) > 1 for b in bindings),
            'eligible_unlinked_games': sum(not g['fully_linked'] and g['eligible_igdb_id'] is not None for g in matches),
            'no_candidate_games': sum(not g['candidates'] for g in matches), 'import': import_info, 'matches': matches}
    path = reports/'ign_link_report.json'
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"IGN评测 {data['review_count']} 篇；游戏 {data['ign_game_count']} 款；已关联评测 {data['linked_reviews']} 篇；待确认精确候选 {data['eligible_unlinked_games']} 款。")
    print('Report:', path)
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, default=ROOT/'data')
    subs = parser.add_subparsers(dest='command', required=True)
    sub = subs.add_parser('import'); sub.add_argument('file', type=Path)
    subs.add_parser('match')
    subs.add_parser('approve-exact', help='Confirm currently eligible exact matches; never fuzzy matches')
    sub = subs.add_parser('confirm'); sub.add_argument('file', type=Path); sub.add_argument('--replace', action='store_true')
    sub = subs.add_parser('confirm-reviews', help='Confirm per-article assignments; they override game-group links')
    sub.add_argument('file', type=Path); sub.add_argument('--replace', action='store_true')
    sub = subs.add_parser('confirm-bindings', help='Confirm complete article target sets and persistent version labels')
    sub.add_argument('file', type=Path); sub.add_argument('--replace', action='store_true')
    args = parser.parse_args()
    db = args.data_dir/'igdb.sqlite3'
    if not db.is_file():
        print('找不到已有 igdb.sqlite3。'); return 1
    try:
        records, info = read_import(args.file) if args.command == 'import' else (None, None)
        actions = confirm_actions(args.file) if args.command == 'confirm' else None
        if args.command == 'confirm-reviews':
            actions = review_confirm_actions(args.file)
        elif args.command == 'confirm-bindings':
            actions = binding_actions(args.file)
        if args.command != 'match':
            backup_database(db, 'ign')
        connection = initialize(db)
        try:
            if args.command == 'import':
                migrate(connection); import_records(connection, records, args.file.name)
            elif not connection.execute('SELECT 1 FROM schema_versions WHERE version=3').fetchone():
                raise ValueError('请先导入IGN评测文件。')
            elif args.command == 'confirm-reviews':
                migrate(connection)
                print('Changed:', apply_review_links(connection, actions, 'manual_article_csv', args.replace))
            elif args.command == 'confirm-bindings':
                migrate(connection)
                print('Changed:', apply_bindings(connection, actions, 'reviewed_bindings_json', args.replace))
            elif args.command == 'approve-exact':
                actions = [(g['ign_game_url'], g['eligible_igdb_id']) for g in candidates(connection) if not g['fully_linked'] and g['eligible_igdb_id'] is not None]
                print('Confirmed:', apply_links(connection, actions, 'approved_exact'))
            elif args.command == 'confirm':
                print('Changed:', apply_links(connection, actions, 'manual_csv', args.replace))
            report(connection, args.data_dir, info)
        finally:
            connection.close()
        return 0
    except (ValueError, TypeError, OSError, sqlite3.Error, zipfile.BadZipFile, ET.ParseError) as exc:
        print('ERROR:', str(exc)); return 1


if __name__ == '__main__':
    raise SystemExit(main())
