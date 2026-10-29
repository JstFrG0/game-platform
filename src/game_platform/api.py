"""Read-only local catalog API. Run with uvicorn game_platform.api:app."""
from __future__ import annotations

import logging
import json
import sqlite3
from contextlib import contextmanager, asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Literal

from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Path as APIPath, Query, Request
from pydantic import BaseModel

from .classify_games import DEFAULT_TYPES, LABELS, filter_sql
from .collect_igdb import ROOT

logger = logging.getLogger(__name__)
Scope = Literal['default', 'all', 'unknown']
SearchScope = Literal['global', 'filtered']
GameType = Literal['main_game', 'dlc_addon', 'expansion', 'bundle', 'standalone_expansion',
                   'mod', 'episode', 'season', 'remake', 'remaster', 'expanded_game',
                   'port', 'fork', 'pack', 'update', 'unknown']
Sort = Literal['release_desc', 'release_asc', 'name_asc', 'rating_desc', 'rating_asc']
ORDERS = {
    'release_desc': 'g.first_release_date DESC,g.igdb_id ASC',
    'release_asc': 'g.first_release_date ASC,g.igdb_id ASC',
    'name_asc': 'g.name COLLATE NOCASE ASC,g.igdb_id ASC',
    'rating_desc': 'g.rating IS NULL ASC,g.rating DESC,g.igdb_id ASC',
    'rating_asc': 'g.rating IS NULL ASC,g.rating ASC,g.igdb_id ASC',
}


class Tag(BaseModel):
    id: int
    name: str | None


class GameSummary(BaseModel):
    igdb_id: int
    name: str
    cover_url: str | None
    first_release_date_utc: str | None
    game_type: str
    game_type_label: str
    platforms: list[Tag]
    genres: list[Tag]
    game_modes: list[Tag]
    rating: float | None
    rating_count: int | None
    aggregated_rating: float | None
    aggregated_rating_count: int | None
    total_rating: float | None
    total_rating_count: int | None


class GamePage(BaseModel):
    total: int
    page: int
    page_size: int
    total_pages: int
    has_next: bool
    items: list[GameSummary]


class RelatedGame(BaseModel):
    igdb_id: int
    name: str | None
    available_locally: bool


class CompanyRole(BaseModel):
    id: int
    name: str | None
    developer: bool | None
    publisher: bool | None


class IGNReview(BaseModel):
    review_id: int
    score: float | None
    scope: str
    review_date: str | None
    reviewed_on: str | None
    review_url: str
    title: str | None
    verdict: str | None


class GameDetail(GameSummary):
    summary: str | None
    storyline: str | None
    igdb_url: str | None
    alternative_names: list[str]
    companies: list[CompanyRole]
    parent_game: RelatedGame | None
    version_parent: RelatedGame | None
    version_title: str | None
    fetched_at: str
    ign_reviews: list[IGNReview] | None


class TagOption(Tag):
    count: int


class TypeOption(BaseModel):
    key: str
    label: str
    count: int
    default_visible: bool


class GlobalFilterOptions(BaseModel):
    available_years: list[int]
    game_types: list[TypeOption]
    platforms: list[TagOption]
    genres: list[TagOption]
    game_modes: list[TagOption]


class FilterOptions(GlobalFilterOptions):
    year: int
    scope: Scope


class Health(BaseModel):
    status: str
    schema_version: int
    read_only: bool


def database_error(code, message):
    return HTTPException(status_code=503, detail={'code': code, 'message': message})


@contextmanager
def database(path):
    connection = None
    try:
        if not path.is_file():
            raise database_error('DATABASE_NOT_FOUND', '找不到本地数据库，请检查 data/igdb.sqlite3。')
        # URI mode=ro prevents accidental creation; query_only prevents SQL writes.
        connection = sqlite3.connect(path.resolve().as_uri()+'?mode=ro', uri=True, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA query_only=ON')
        connection.execute('BEGIN')
        tables = {r['name'] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {'schema_versions', 'igdb_games', 'game_tags'}.issubset(tables):
            raise database_error('SCHEMA_NOT_READY', '请先执行 classify_games 分类字段迁移。')
        if not connection.execute('SELECT 1 FROM schema_versions WHERE version=2').fetchone():
            raise database_error('SCHEMA_NOT_READY', '请先执行 classify_games 分类字段迁移。')
        yield connection
    except sqlite3.Error:
        logger.exception('Local catalog database unavailable')
        raise database_error('DATABASE_UNAVAILABLE', '数据库暂时不可用，请确认文件状态后重试。') from None
    finally:
        if connection is not None:
            connection.close()


def page_items(connection, rows):
    if not rows:
        return []
    tags = {r['igdb_id']: {'platform': [], 'genre': [], 'mode': []} for r in rows}
    ids = list(tags)
    for tag in connection.execute('SELECT igdb_id,kind,tag_id,name FROM game_tags WHERE igdb_id IN (' +
            ','.join('?' for _ in ids) + ') ORDER BY kind,tag_id', ids):
        tags[tag['igdb_id']][tag['kind']].append({'id': tag['tag_id'], 'name': tag['name']})
    items = []
    for row in rows:
        record = source_record(row)
        cover = record.get('cover')
        item = {k: row[k] for k in ('igdb_id', 'name', 'rating', 'rating_count', 'aggregated_rating',
                                    'aggregated_rating_count', 'total_rating', 'total_rating_count')}
        item.update(first_release_date_utc=(datetime.fromtimestamp(row['first_release_date'], timezone.utc).date().isoformat()
                                           if row['first_release_date'] is not None else None),
                    cover_url=source_url(cover.get('url')) if isinstance(cover, dict) else None,
                    game_type=row['game_type_key'], game_type_label=LABELS.get(row['game_type_key'], '待分类'),
                    platforms=tags[row['igdb_id']]['platform'], genres=tags[row['igdb_id']]['genre'],
                    game_modes=tags[row['igdb_id']]['mode'])
        items.append(item)
    return items


def source_url(value):
    """Return an HTTP(S) source link, never fetch a remote image in this API."""
    if not isinstance(value, str) or not value.strip():
        return None
    value = value.strip()
    if value.startswith('//'):
        value = 'https:'+value
    try:
        parts = urlsplit(value)
        if parts.scheme not in ('http', 'https') or not parts.hostname or parts.username or parts.password:
            return None
    except ValueError:
        return None
    return value


def source_record(row):
    try:
        record = json.loads(row['raw_json'])
        if not isinstance(record, dict) or record.get('id') != row['igdb_id']:
            raise ValueError('Source ID mismatch')
        return record
    except (ValueError, TypeError):
        raise database_error('SOURCE_DATA_INVALID', '该游戏原始资料格式异常，请检查来源数据。') from None


def related_game(connection, ident):
    if ident is None:
        return None
    row = connection.execute('SELECT name FROM igdb_games WHERE igdb_id=?', (ident,)).fetchone()
    return {'igdb_id': ident, 'name': row['name'] if row else None, 'available_locally': row is not None}


def game_detail(connection, row):
    record = source_record(row)
    result = page_items(connection, [row])[0]
    cover = record.get('cover')
    alternative_names = []
    for entry in record.get('alternative_names') or []:
        if isinstance(entry, dict) and isinstance(entry.get('name'), str) and entry['name'].strip():
            if entry['name'] not in alternative_names:
                alternative_names.append(entry['name'])
    companies = []
    for entry in record.get('involved_companies') or []:
        if not isinstance(entry, dict) or not isinstance(entry.get('company'), dict):
            continue
        company = entry['company']
        ident = company.get('id')
        if not isinstance(ident, int) or isinstance(ident, bool) or ident < 0:
            continue
        companies.append({'id': ident, 'name': company.get('name') if isinstance(company.get('name'), str) else None,
                          'developer': entry.get('developer') if isinstance(entry.get('developer'), bool) else None,
                          'publisher': entry.get('publisher') if isinstance(entry.get('publisher'), bool) else None})
    result.update(summary=row['summary'],
                  storyline=record.get('storyline') if isinstance(record.get('storyline'), str) else None,
                  cover_url=source_url(cover.get('url')) if isinstance(cover, dict) else None,
                  igdb_url=source_url(record.get('url')), alternative_names=alternative_names,
                  companies=companies, parent_game=related_game(connection, row['parent_game_id']),
                  version_parent=related_game(connection, row['version_parent_id']),
                  version_title=record.get('version_title') if isinstance(record.get('version_title'), str) else None,
                  fetched_at=row['fetched_at'], ign_reviews=linked_ign_reviews(connection, row['igdb_id']))
    return result


def linked_ign_reviews(connection, game_id):
    if not connection.execute('SELECT 1 FROM schema_versions WHERE version=3').fetchone():
        return None
    if connection.execute('SELECT 1 FROM schema_versions WHERE version=5').fetchone():
        rows = connection.execute('''SELECT r.review_id,r.score,COALESCE(b.scope_override,r.scope) AS scope,
            r.review_date,r.reviewed_on,r.review_url,r.title,r.verdict
            FROM ign_effective_review_targets t JOIN ign_reviews r USING(review_url)
            LEFT JOIN ign_review_bindings b USING(review_url)
            WHERE t.igdb_id=? ORDER BY r.review_date IS NULL,r.review_date DESC,r.review_id''', (game_id,)).fetchall()
    elif connection.execute('SELECT 1 FROM schema_versions WHERE version=4').fetchone():
        rows = connection.execute('''SELECT review_id,score,scope,review_date,reviewed_on,
            review_url,title,verdict FROM ign_resolved_reviews WHERE resolved_igdb_id=?
            ORDER BY review_date IS NULL,review_date DESC,review_id''', (game_id,)).fetchall()
    else:
        rows = connection.execute('''SELECT r.review_id,r.score,r.scope,r.review_date,r.reviewed_on,
            r.review_url,r.title,r.verdict FROM ign_reviews r JOIN ign_links l USING(ign_game_url)
            WHERE l.igdb_id=? ORDER BY r.review_date IS NULL,r.review_date DESC,r.review_id''', (game_id,)).fetchall()
    return [dict(row) for row in rows]


def search_query(year, scope, platform_id, genre_id, mode_id, min_rating,
                 min_rating_count, game_type, q, search_scope, sort, platform_ids=None, genre_ids=None, mode_ids=None):
    """Keep browsing filters intact; global text search bypasses every filter."""
    query = q.strip() if q else ''
    if query and search_scope == 'global':
        where, params = 'instr(lower(g.name),lower(?)) > 0', [query]
    else:
        platforms = sorted(set([*(platform_ids or []), *([platform_id] if platform_id is not None else [])]))
        where, params = filter_sql(year, scope, None, None, None,
                                   min_rating, min_rating_count, game_type, query)
        if platforms:
            where += " AND EXISTS (SELECT 1 FROM game_tags pt WHERE pt.igdb_id=g.igdb_id AND pt.kind='platform' AND pt.tag_id IN (" + ','.join('?' for _ in platforms) + '))'
            params.extend(platforms)
        genres = sorted(set([*(genre_ids or []), *([genre_id] if genre_id is not None else [])]))
        if genres:
            where += " AND EXISTS (SELECT 1 FROM game_tags gt WHERE gt.igdb_id=g.igdb_id AND gt.kind='genre' AND gt.tag_id IN (" + ','.join('?' for _ in genres) + '))'
            params.extend(genres)
        modes = sorted(set([*(mode_ids or []), *([mode_id] if mode_id is not None else [])]))
        if modes:
            where += " AND EXISTS (SELECT 1 FROM game_tags mt WHERE mt.igdb_id=g.igdb_id AND mt.kind='mode' AND mt.tag_id IN (" + ','.join('?' for _ in modes) + '))'
            params.extend(modes)
    order, order_params = ORDERS[sort], []
    if query:
        # Rank before LIMIT/OFFSET so the exact game appears on the first page.
        # The rest of the ordering remains deterministic for stable pagination.
        order = '''CASE WHEN lower(trim(g.name))=lower(?) THEN 0
            WHEN instr(lower(g.name),lower(?))=1 THEN 1 ELSE 2 END,''' + order
        order_params = [query, query]
    return where, params, order, order_params


def parse_platform_ids(value):
    if value is None or not value.strip():
        return []
    parts = value.split(',')
    if len(parts) > 100 or any(not p.strip().isascii() or not p.strip().isdigit() for p in parts):
        raise HTTPException(status_code=422, detail={'message': '平台参数应为逗号分隔的整数，最多 100 项。'})
    ids = sorted({int(p.strip()) for p in parts})
    if any(ident > 2147483647 for ident in ids):
        raise HTTPException(status_code=422, detail={'message': '平台 ID 超出有效范围。'})
    return ids


def parse_genre_ids(value):
    try:
        return parse_platform_ids(value)
    except HTTPException as exc:
        raise HTTPException(status_code=422, detail={'message': '类型参数应为逗号分隔的有效整数 ID，最多 100 项。'}) from exc


def parse_mode_ids(value):
    try:
        return parse_platform_ids(value)
    except HTTPException as exc:
        raise HTTPException(status_code=422, detail={'message': '游玩模式参数应为逗号分隔的有效整数 ID，最多 100 项。'}) from exc


def create_app(database_path: Path | None = None):
    path = Path(database_path) if database_path is not None else ROOT/'data/igdb.sqlite3'
    from .update_service import UpdateService
    update_service = UpdateService(path)

    @asynccontextmanager
    async def lifespan(app):
        update_service.start()
        try:
            yield
        finally:
            await update_service.close()

    app = FastAPI(title='本地游戏资料库 API', version='0.10.0',
                  description='读取 IGDB 本地资料；无评分为 null。支持后台更新与本机手动检查。',
                  lifespan=lifespan)

    @app.get('/api/v1/data-updates', tags=['状态'])
    def data_updates():
        return update_service.snapshot()

    @app.post('/api/v1/data-updates/check', status_code=202, tags=['状态'])
    async def check_data_updates(request: Request):
        origin = request.headers.get('origin')
        if request.headers.get('sec-fetch-site') == 'cross-site' or (
                origin and urlsplit(origin).hostname not in ('127.0.0.1', 'localhost', '::1')):
            raise HTTPException(status_code=403, detail={'message': '请从本机软件中检查更新。'})
        if not update_service.request_check():
            raise HTTPException(status_code=409, detail={'message': '数据自动更新尚未启用，请检查本机更新配置。'})
        return update_service.snapshot()

    @app.get('/health', response_model=Health, tags=['状态'])
    def health():
        with database(path) as connection:
            version = connection.execute('SELECT max(version) FROM schema_versions').fetchone()[0]
            return {'status': 'ok', 'schema_version': version, 'read_only': True}

    @app.get('/api/v1/games', response_model=GamePage, tags=['游戏资料库'])
    def games(
        year: Annotated[int, Query(ge=1950, le=2100, description='全球首次发售的 UTC 年份')] = 2025,
        scope: Scope = 'default',
        page: Annotated[int, Query(ge=1, le=1000000)] = 1,
        page_size: Annotated[int, Query(ge=1, le=100)] = 20,
        sort: Sort = 'release_desc',
        q: Annotated[str | None, Query(max_length=100, description='名称包含文本；不支持通配符')] = None,
        search_scope: Annotated[SearchScope, Query(description='有关键词时默认 global 全库搜索；filtered 与当前筛选条件取交集。无关键词时沿用普通筛选。名称完全匹配优先。')] = 'global',
        game_type: Annotated[GameType | None, Query(description='与 scope 取交集；查看 DLC 等需选 scope=all')] = None,
        platform_id: Annotated[int | None, Query(ge=0)] = None,
        platform_ids: Annotated[str | None, Query(max_length=1100, description='逗号分隔的平台 ID，最多100项；任一平台匹配，游戏不重复。兼容 platform_id，两者并集。')] = None,
        genre_id: Annotated[int | None, Query(ge=0)] = None,
        genre_ids: Annotated[str | None, Query(max_length=1100, description='玩法类型 ID，逗号分隔，最多100项；任一匹配，游戏不重复。与旧 genre_id 合并。')] = None,
        mode_id: Annotated[int | None, Query(ge=0)] = None,
        mode_ids: Annotated[str | None, Query(max_length=1100, description='游玩模式 ID，逗号分隔，最多100项；任一匹配，同一游戏不重复。与旧 mode_id 合并。')] = None,
        min_rating: Annotated[float | None, Query(ge=0, le=100, allow_inf_nan=False, description='最低 IGDB 用户评分')] = None,
        min_rating_count: Annotated[int | None, Query(ge=0, description='最低 IGDB 用户评分人数')] = None,
    ):
        where, params, order, order_params = search_query(year, scope, platform_id, genre_id,
            mode_id, min_rating, min_rating_count, game_type, q, search_scope, sort,
            parse_platform_ids(platform_ids), parse_genre_ids(genre_ids), parse_mode_ids(mode_ids))
        with database(path) as connection:
            total = connection.execute('SELECT count(*) FROM igdb_games g WHERE '+where, params).fetchone()[0]
            offset = (page-1)*page_size
            # SQL does pagination; do not load 25,476 records into Python per request.
            rows = connection.execute('''SELECT g.igdb_id,g.name,g.first_release_date,g.game_type_key,g.raw_json,
                g.rating,g.rating_count,g.aggregated_rating,g.aggregated_rating_count,g.total_rating,g.total_rating_count
                FROM igdb_games g WHERE '''+where+' ORDER BY '+order+' LIMIT ? OFFSET ?',
                [*params, *order_params, page_size, offset]).fetchall()
            return {'total': total, 'page': page, 'page_size': page_size,
                    'total_pages': (total+page_size-1)//page_size,
                    'has_next': offset+page_size < total, 'items': page_items(connection, rows)}

    @app.get('/api/v1/filter-options', response_model=GlobalFilterOptions, tags=['游戏资料库'])
    def global_options():
        """Independent option dictionaries from the whole local catalog."""
        with database(path) as connection:
            counts = dict(connection.execute(
                'SELECT game_type_key,count(*) FROM igdb_games GROUP BY game_type_key'))
            option_tags = {'platform': [], 'genre': [], 'mode': []}
            for row in connection.execute('''SELECT t.kind,t.tag_id,max(t.name) name,
                    count(DISTINCT t.igdb_id) game_count
                    FROM game_tags t JOIN igdb_games g USING(igdb_id)
                    WHERE t.kind IN ('platform','genre','mode')
                    GROUP BY t.kind,t.tag_id ORDER BY t.kind,t.tag_id'''):
                option_tags[row['kind']].append({
                    'id': row['tag_id'], 'name': row['name'], 'count': row['game_count']})
            years = [r[0] for r in connection.execute("""SELECT DISTINCT
                CAST(strftime('%Y',first_release_date,'unixepoch') AS INTEGER)
                FROM igdb_games WHERE first_release_date IS NOT NULL ORDER BY 1""") if r[0] is not None]
            return {'available_years': years,
                    'game_types': [{'key': key, 'label': label, 'count': counts.get(key, 0),
                                    'default_visible': key in DEFAULT_TYPES} for key, label in LABELS.items()],
                    'platforms': option_tags['platform'], 'genres': option_tags['genre'],
                    'game_modes': option_tags['mode']}

    @app.get('/api/v1/filters', response_model=FilterOptions, tags=['游戏资料库'])
    def filters(year: Annotated[int, Query(ge=1950, le=2100)] = 2025, scope: Scope = 'default'):
        with database(path) as connection:
            all_where, all_params = filter_sql(year, 'all')
            counts = dict(connection.execute('SELECT g.game_type_key,count(*) FROM igdb_games g WHERE '+
                                             all_where+' GROUP BY g.game_type_key', all_params))
            where, params = filter_sql(year, scope)
            option_tags = {'platform': [], 'genre': [], 'mode': []}
            for row in connection.execute('''SELECT t.kind,t.tag_id,max(t.name) name,count(*) game_count
                    FROM game_tags t JOIN igdb_games g USING(igdb_id) WHERE '''+where+
                    ' GROUP BY t.kind,t.tag_id ORDER BY t.kind,t.tag_id', params):
                option_tags[row['kind']].append({'id': row['tag_id'], 'name': row['name'], 'count': row['game_count']})
            years = [r[0] for r in connection.execute("SELECT DISTINCT CAST(strftime('%Y',first_release_date,'unixepoch') AS INTEGER) FROM igdb_games WHERE first_release_date IS NOT NULL ORDER BY 1")]
            return {'year': year, 'scope': scope, 'available_years': years,
                    # Type counts always describe all types for this year, so hidden types remain discoverable.
                    'game_types': [{'key': key, 'label': label, 'count': counts.get(key, 0),
                                    'default_visible': key in DEFAULT_TYPES} for key, label in LABELS.items()],
                    'platforms': option_tags['platform'], 'genres': option_tags['genre'], 'game_modes': option_tags['mode']}

    @app.get('/api/v1/games/{igdb_id}', response_model=GameDetail, tags=['游戏资料库'],
             responses={404: {'description': '本地库未收录该 ID'}})
    def detail(igdb_id: Annotated[int, APIPath(ge=1, le=9223372036854775807)]):
        with database(path) as connection:
            row = connection.execute('SELECT * FROM igdb_games WHERE igdb_id=?', (igdb_id,)).fetchone()
            if row is None:
                raise HTTPException(status_code=404, detail={
                    'code': 'GAME_NOT_FOUND', 'message': '本地资料库未收录该游戏 ID。'})
            # Detail remains accessible even if the entry is hidden by default list rules.
            return game_detail(connection, row)

    return app


app = create_app()
