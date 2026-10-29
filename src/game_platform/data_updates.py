"""Build, publish and transactionally merge versioned IGDB data snapshots."""
from __future__ import annotations

import argparse
import asyncio
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import io
import json
import logging
import math
import os
from pathlib import Path
import re
import sqlite3
import tempfile
import zipfile

import httpx

from .collect_igdb import ROOT, RATINGS, initialize, numeric, upsert_record, utc_now
from .classify_games import backup_database, migrate

log = logging.getLogger(__name__)
MANIFEST = 'catalog-manifest.json'
PACKAGE = 'catalog-data.zip'
MAX_PACKAGE = 128 * 1024 * 1024
MAX_RAW = 512 * 1024 * 1024
REPOSITORY = re.compile(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z')


def json_bytes(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False).encode('utf-8')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def validate_record(record, *, allow_unknown_date=False):
    if not isinstance(record, dict):
        raise ValueError('游戏记录必须为对象。')
    ident = record.get('id')
    if type(ident) is not int or ident <= 0:
        raise ValueError('游戏 ID 不合法。')
    if not isinstance(record.get('name'), str) or not record['name'].strip():
        raise ValueError('游戏缺少名称。')
    released = record.get('first_release_date')
    unknown = allow_unknown_date and 'first_release_date' in record and released is None
    if not unknown and (type(released) is not int or not -631152000 <= released < 4133980800):
        raise ValueError('首次发售时间超出支持范围（1950–2100）。')
    for field in RATINGS:
        numeric(record, field)
    for field in ('platforms', 'genres', 'game_modes'):
        if record.get(field) is not None and not isinstance(record[field], list):
            raise ValueError(f'{field} 必须为数组。')
    if record.get('summary') is not None and not isinstance(record['summary'], str):
        raise ValueError('游戏简介必须为字符串。')


def validate_manifest(manifest):
    if not isinstance(manifest, dict) or manifest.get('format_version') not in (1, 2):
        raise ValueError('不支持的数据包格式。')
    if manifest.get('source') != 'igdb' or manifest.get('package') != PACKAGE:
        raise ValueError('数据包来源或名称不符。')
    stamp = manifest.get('created_at', '')
    try:
        parsed = datetime.fromisoformat(stamp)
        if parsed.utcoffset() is None or parsed > datetime.now(timezone.utc):
            raise ValueError()
    except (TypeError, ValueError):
        raise ValueError('数据包时间戳无效。') from None
    if manifest.get('version') != stamp:
        raise ValueError('数据包版本与时间戳不一致。')
    for key in ('sha256', 'records_sha256'):
        if not re.fullmatch(r'[0-9a-f]{64}', str(manifest.get(key, ''))):
            raise ValueError('缺少 SHA-256 校验值。')
    for key, maximum in (('size', MAX_PACKAGE), ('records_size', MAX_RAW), ('record_count', 1000000)):
        if type(manifest.get(key)) is not int or not 0 < manifest[key] <= maximum:
            raise ValueError(f'数据包 {key} 超出限制。')
    if manifest['format_version'] == 2:
        for key, maximum in (('ign_records_size', MAX_RAW), ('ign_record_count', 1000000)):
            if type(manifest.get(key)) is not int or not 0 <= manifest[key] <= maximum:
                raise ValueError(f'数据包 {key} 超出限制。')
        if not re.fullmatch(r'[0-9a-f]{64}', str(manifest.get('ign_records_sha256', ''))):
            raise ValueError('缺少 IGN SHA-256 校验值。')
        if manifest['records_size'] + manifest['ign_records_size'] > MAX_RAW:
            raise ValueError('原始数据总大小超出限制。')
    scope = manifest.get('scope')
    if scope is not None:
        if not isinstance(scope, dict) or type(scope.get('year')) is not int or not 1950 <= scope['year'] <= 2100:
            raise ValueError('年份包范围无效。')
        for key in ('year_record_count', 'correction_record_count'):
            if type(scope.get(key)) is not int or scope[key] < 0:
                raise ValueError('年份包范围计数无效。')
        if scope['year_record_count'] + scope['correction_record_count'] != manifest['record_count']:
            raise ValueError('年份包范围计数不一致。')
    return parsed


def atomic_write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as file:
        temporary = Path(file.name)
        file.write(data)
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def operation_lock(path):
    """OS-backed lock: released automatically if a process exits or crashes."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a+b') as file:
        file.seek(0, 2)
        if file.tell() == 0:
            file.write(b'0')
            file.flush()
        file.seek(0)
        if os.name == 'nt':
            import msvcrt
            try:
                msvcrt.locking(file.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                raise RuntimeError('同一目录已有更新任务运行。') from None
        else:
            import fcntl
            try:
                fcntl.flock(file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                raise RuntimeError('同一目录已有更新任务运行。') from None
        try:
            yield
        finally:
            file.seek(0)
            if os.name == 'nt':
                msvcrt.locking(file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(file, fcntl.LOCK_UN)


def validate_ign_entry(entry, game_ids):
    from .ign_reviews import date_value, ign_url
    if not isinstance(entry, dict) or not isinstance(entry.get('review'), dict):
        raise ValueError('IGN 评测格式无效。')
    review = entry['review']
    for key, kind in (('review_url', 'articles'), ('ign_game_url', 'games')):
        if ign_url(review.get(key), kind) != review[key]:
            raise ValueError('IGN 评测链接不是标准格式。')
    for key in ('name', 'scope', 'raw_json'):
        if not isinstance(review.get(key), str) or not review[key].strip():
            raise ValueError(f'IGN {key} 缺失。')
    if not isinstance(json.loads(review['raw_json']), dict):
        raise ValueError('IGN 原始记录无效。')
    score = review.get('score')
    if score is not None and (type(score) not in (int, float) or not math.isfinite(score) or not 0 <= score <= 10):
        raise ValueError('IGN 评分超出0–10范围。')
    if not isinstance(review.get('platforms'), list) or not all(isinstance(p, str) for p in review['platforms']):
        raise ValueError('IGN 平台列表无效。')
    for key in ('us_release_date', 'review_date'):
        if key not in review or date_value(review[key]) != review[key]:
            raise ValueError('IGN 日期格式无效。')
    for key in ('reviewed_on', 'title', 'verdict'):
        if key not in review or (review[key] is not None and not isinstance(review[key], str)):
            raise ValueError(f'IGN {key} 格式无效。')
    ids = entry.get('igdb_ids')
    if not isinstance(ids, list) or any(type(i) is not int or i not in game_ids for i in ids) or len(set(ids)) != len(ids):
        raise ValueError('IGN 关联游戏不在更新包内或存在重复。')


def build_bundle(records, output, *, ign_reviews=None, scope=None):
    entries = sorted(records, key=lambda r: r['id'])
    seen = set()
    for record in entries:
        validate_record(record, allow_unknown_date=ign_reviews is not None)
        if record['id'] in seen:
            raise ValueError('数据包含重复游戏 ID。')
        seen.add(record['id'])
    raw = b''.join(json_bytes(record) + b'\n' for record in entries)
    ign_raw = None
    if ign_reviews is not None:
        urls = set()
        for entry in ign_reviews:
            validate_ign_entry(entry, seen)
            url = entry['review']['review_url']
            if url in urls:
                raise ValueError('IGN 包含重复评测链接。')
            urls.add(url)
        ign_raw = b''.join(json_bytes(entry) + b'\n' for entry in ign_reviews)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('games.jsonl', raw)
        if ign_raw is not None:
            archive.writestr('ign-reviews.jsonl', ign_raw)
    package = buffer.getvalue()
    stamp = utc_now()
    manifest = dict(format_version=1, source='igdb', version=stamp, created_at=stamp,
                    package=PACKAGE, sha256=digest(package), size=len(package),
                    records_sha256=digest(raw), records_size=len(raw), record_count=len(entries))
    if ign_raw is not None:
        manifest.update(format_version=2, sources=['igdb', 'ign'], ign_record_count=len(ign_reviews),
                        ign_records_size=len(ign_raw), ign_records_sha256=digest(ign_raw))
    if scope is not None:
        manifest['scope'] = scope
    validate_manifest(manifest)
    atomic_write(Path(output)/PACKAGE, package)
    atomic_write(Path(output)/MANIFEST, json_bytes(manifest))
    return manifest


def read_bundle_content(manifest, package):
    validate_manifest(manifest)
    if len(package) != manifest['size'] or digest(package) != manifest['sha256']:
        raise ValueError('下载包大小或 SHA-256 校验失败。')
    with zipfile.ZipFile(io.BytesIO(package)) as archive:
        names = ['games.jsonl'] + (['ign-reviews.jsonl'] if manifest['format_version'] == 2 else [])
        if archive.namelist() != names:
            raise ValueError('数据包内容不符合协议。')
        info = archive.getinfo('games.jsonl')
        if info.file_size != manifest['records_size'] or info.file_size > MAX_RAW:
            raise ValueError('解压大小超出限制。')
        raw = archive.read(info)
        ign_raw = b''
        if manifest['format_version'] == 2:
            info = archive.getinfo('ign-reviews.jsonl')
            if info.file_size != manifest['ign_records_size'] or info.file_size > MAX_RAW:
                raise ValueError('IGN 解压大小超出限制。')
            ign_raw = archive.read(info)
            if digest(ign_raw) != manifest['ign_records_sha256']:
                raise ValueError('IGN SHA-256 校验失败。')
    if digest(raw) != manifest['records_sha256']:
        raise ValueError('原始记录 SHA-256 校验失败。')
    records = [json.loads(line) for line in raw.splitlines()]
    if len(records) != manifest['record_count']:
        raise ValueError('数据包记录数不一致。')
    seen = set()
    for record in records:
        validate_record(record, allow_unknown_date=manifest['format_version'] == 2)
        if record['id'] in seen:
            raise ValueError('数据包含重复游戏 ID。')
        seen.add(record['id'])
    ign_reviews = [json.loads(line) for line in ign_raw.splitlines()]
    if manifest['format_version'] == 2 and len(ign_reviews) != manifest['ign_record_count']:
        raise ValueError('IGN 评测数量不一致。')
    urls = set()
    for entry in ign_reviews:
        validate_ign_entry(entry, seen)
        url = entry['review']['review_url']
        if url in urls:
            raise ValueError('IGN 包含重复评测链接。')
        urls.add(url)
    return records, ign_reviews


def read_bundle(manifest, package):
    return read_bundle_content(manifest, package)[0]


def merge_ign_entries(connection, entries):
    from .ign_reviews import import_records
    import_records(connection, [entry['review'] for entry in entries], 'github-data-update', commit=False)
    for entry in entries:
        review = entry['review']
        url = review['review_url']
        binding = connection.execute('SELECT method FROM ign_review_bindings WHERE review_url=?', (url,)).fetchone()
        if binding and binding['method'] != 'data_update':
            continue
        # Local manual assignments always take precedence over distributed mappings.
        if connection.execute('SELECT 1 FROM ign_review_links WHERE review_url=?', (url,)).fetchone():
            continue
        if connection.execute('SELECT 1 FROM ign_links WHERE ign_game_url=?', (review['ign_game_url'],)).fetchone():
            continue
        if not entry['igdb_ids']:
            continue
        connection.execute('''INSERT INTO ign_review_bindings VALUES(?,?,'data_update',?,?)
            ON CONFLICT(review_url) DO UPDATE SET scope_override=excluded.scope_override,
            confirmed_at=excluded.confirmed_at,reason=excluded.reason''',
            (url, review['scope'], utc_now(), 'Verified publisher mapping; local manual mappings take precedence'))
        connection.execute('DELETE FROM ign_review_binding_targets WHERE review_url=?', (url,))
        connection.executemany('INSERT INTO ign_review_binding_targets VALUES(?,?)',
                               [(url, ident) for ident in entry['igdb_ids']])


def apply_bundle(database, manifest, package):
    """All game merges and the version receipt commit together; never replace a DB."""
    records, ign_reviews = read_bundle_content(manifest, package)
    database = Path(database)
    with operation_lock(database.parent/'updates.lock'):
        # Read the receipt before a backup or schema change; reruns are no-ops.
        if database.exists():
            connection = sqlite3.connect(database.resolve().as_uri()+'?mode=ro', uri=True)
            try:
                if connection.execute("SELECT 1 FROM sqlite_master WHERE name='data_update_receipts'").fetchone():
                    row = connection.execute('SELECT version,sha256 FROM data_update_receipts ORDER BY version DESC LIMIT 1').fetchone()
                    if row:
                        if row[0] == manifest['version']:
                            if row[1] != manifest['sha256']:
                                raise ValueError('相同版本对应不同数据包，拒绝更新。')
                            return {'status': 'up_to_date', 'version': row[0]}
                        if datetime.fromisoformat(row[0]) >= datetime.fromisoformat(manifest['version']):
                            raise ValueError('拒绝安装旧版本数据包。')
            finally:
                connection.close()
        backup = backup_database(database, 'data_update') if database.exists() else None
        connection = initialize(database)
        try:
            if not connection.execute('SELECT 1 FROM schema_versions WHERE version=2').fetchone():
                migrate(connection)
            if manifest['format_version'] == 2:
                from .ign_reviews import migrate as migrate_ign
                migrate_ign(connection)
            with connection:
                connection.execute('BEGIN IMMEDIATE')
                connection.execute('''CREATE TABLE IF NOT EXISTS data_update_receipts(
                    version TEXT PRIMARY KEY, sha256 TEXT NOT NULL, applied_at TEXT NOT NULL,
                    record_count INTEGER NOT NULL)''')
                for record in records:
                    upsert_record(connection, record)
                if ign_reviews:
                    merge_ign_entries(connection, ign_reviews)
                connection.execute('INSERT INTO data_update_receipts VALUES(?,?,?,?)',
                                   (manifest['version'], manifest['sha256'], utc_now(), len(records)))
                if connection.execute('PRAGMA foreign_key_check').fetchone():
                    raise ValueError('外键检查失败，更新已回滚。')
        finally:
            connection.close()
        return {'status': 'updated', 'version': manifest['version'], 'records': len(records),
                'ign_reviews': len(ign_reviews),
                'backup': str(backup) if backup else None}


def check_repository(repository):
    if not REPOSITORY.fullmatch(repository) or any(p in ('.', '..') for p in repository.split('/')):
        raise ValueError('GitHub 仓库格式必须为 owner/repo。')


def download(client, url, limit, headers=None):
    # GitHub's asset API may return bytes directly or redirect to signed storage.
    # Credentials apply only to the first request, never to redirected requests.
    request_headers = headers or {}
    for _ in range(6):
        with client.stream('GET', url, headers=request_headers, follow_redirects=False) as response:
            if response.status_code in (301, 302, 303, 307, 308):
                target = response.url.join(response.headers['location'])
                if target.scheme != 'https' or target.userinfo:
                    raise ValueError('附件重定向地址无效。')
                url, request_headers = target, {}
                continue
            response.raise_for_status()
            chunks, size = [], 0
            for chunk in response.iter_bytes():
                size += len(chunk)
                if size > limit:
                    raise ValueError('下载内容超过大小限制。')
                chunks.append(chunk)
            return b''.join(chunks)
    raise ValueError('附件重定向次数超出限制。')


def installed_update(database):
    """Read the last committed receipt without creating or migrating a database."""
    path = Path(database)
    if not path.is_file():
        return None
    connection = sqlite3.connect(path.resolve().as_uri()+'?mode=ro', uri=True)
    try:
        if not connection.execute("SELECT 1 FROM sqlite_master WHERE name='data_update_receipts'").fetchone():
            return None
        row = connection.execute('SELECT version,sha256 FROM data_update_receipts ORDER BY version DESC LIMIT 1').fetchone()
        return {'version': row[0], 'sha256': row[1]} if row else None
    finally:
        connection.close()


def update_from_github(database, repository, client=None, *, token=None, progress=None):
    check_repository(repository)
    token = os.environ.get('GAME_DATA_GITHUB_TOKEN', '').strip() if token is None else token.strip()
    if client is None:
        with httpx.Client(timeout=60) as http:
            return update_from_github(database, repository, http, token=token, progress=progress)
    api_headers = {'Accept': 'application/vnd.github+json'}
    if token:
        api_headers['Authorization'] = f'Bearer {token}'
    response = client.get(f'https://api.github.com/repos/{repository}/releases?per_page=100',
                          headers=api_headers, follow_redirects=False)
    if response.status_code in (301, 302, 303, 307, 308):
        raise ValueError('仓库地址发生变更，请更新配置的 owner/repo。')
    response.raise_for_status()
    releases = response.json()
    if not isinstance(releases, list):
        raise ValueError('GitHub Release 响应异常。')
    candidates = [r for r in releases if not r.get('draft') and not r.get('prerelease')
                  and str(r.get('tag_name', '')).startswith('data-')]
    if not candidates:
        return {'status': 'no_release'}
    release = max(candidates, key=lambda r: r.get('published_at') or '')
    assets = {a['name']: a for a in release.get('assets', [])}
    if not {MANIFEST, PACKAGE}.issubset(assets):
        raise ValueError('最新数据 Release 缺少必需附件，保留本地数据。')
    urls = {}
    for name in (MANIFEST, PACKAGE):
        if token:
            ident = assets[name].get('id')
            if type(ident) is not int or ident <= 0:
                raise ValueError('GitHub 附件 ID 无效。')
            urls[name] = f'https://api.github.com/repos/{repository}/releases/assets/{ident}'
            continue
        url = assets[name]['browser_download_url']
        if not url.startswith(f'https://github.com/{repository}/releases/download/'):
            raise ValueError('附件下载地址不属于配置的仓库。')
        urls[name] = url
    asset_headers = {**api_headers, 'Accept': 'application/octet-stream'} if token else None
    manifest = json.loads(download(client, urls[MANIFEST], 64*1024, asset_headers))
    validate_manifest(manifest)
    receipt = installed_update(database)
    if receipt and receipt['version'] == manifest['version']:
        if receipt['sha256'] != manifest['sha256']:
            raise ValueError('相同版本对应不同数据包，拒绝更新。')
        return {'status': 'up_to_date', 'version': receipt['version']}
    if receipt and datetime.fromisoformat(receipt['version']) > datetime.fromisoformat(manifest['version']):
        return {'status': 'up_to_date', 'version': receipt['version']}
    if progress:
        progress('downloading')
    package = download(client, urls[PACKAGE], manifest['size'], asset_headers)
    if progress:
        progress('installing')
    return apply_bundle(database, manifest, package)


def publish_bundle(repository, output, token, client=None):
    """Keep the release a draft until both validated assets have uploaded."""
    check_repository(repository)
    if not token:
        raise ValueError('发布需要环境变量 GITHUB_TOKEN。')
    output = Path(output)
    manifest = json.loads((output/MANIFEST).read_bytes())
    package = (output/PACKAGE).read_bytes()
    read_bundle(manifest, package)
    tag = 'data-' + datetime.fromisoformat(manifest['version']).strftime('%Y%m%dT%H%M%S%fZ')
    if client is None:
        with httpx.Client(timeout=120) as http:
            return publish_bundle(repository, output, token, http)
    headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/vnd.github+json'}
    base = f'https://api.github.com/repos/{repository}/releases'
    title = 'IGDB + IGN data' if manifest['format_version'] == 2 else 'IGDB data'
    body = f'IGDB source snapshot: {manifest["record_count"]} games. SHA-256: {manifest["sha256"]}'
    if manifest['format_version'] == 2:
        body += f'\nIGN reviews: {manifest["ign_record_count"]}. Requires a client supporting catalog format v2.'
    if manifest.get('scope'):
        scope = manifest['scope']
        title = f'{scope["year"]} {title}'
        body += (f'\nScope: global first release in {scope["year"]} (UTC): {scope["year_record_count"]} games.'
                 f'\nAdditional corrections for previously in-scope games: {scope["correction_record_count"]}.'
                 '\nLocal manual IGN mappings take precedence over distributed mappings.')
    response = client.post(base, headers=headers, json=dict(
        tag_name=tag, name=f'{title} {manifest["version"]}', draft=True, body=body))
    response.raise_for_status()
    release = response.json()
    # Build the upload endpoint ourselves so credentials never follow response-provided hosts.
    upload = f'https://uploads.github.com/repos/{repository}/releases/{int(release["id"])}/assets'
    for name, content in ((PACKAGE, package), (MANIFEST, json_bytes(manifest))):
        result = client.post(upload, params={'name': name}, content=content,
                             headers={**headers, 'Content-Type': 'application/octet-stream'})
        result.raise_for_status()
    response = client.patch(f'{base}/{int(release["id"])}', headers=headers,
                            json={'draft': False, 'make_latest': 'false'})
    response.raise_for_status()
    return {'status': 'published', 'tag': tag, 'url': response.json()['html_url']}


async def automatic_updates(database, repository, interval, state):
    while True:
        state.update(status='checking', checked_at=utc_now())
        try:
            result = await asyncio.to_thread(update_from_github, database, repository)
            state.update(result, error=None)
        except Exception as exc:
            # Keep the read-only API available offline; never expose tokens or request URLs.
            log.warning('Catalog update failed (%s); local catalog retained', type(exc).__name__)
            state.update(status='failed', error=type(exc).__name__)
        await asyncio.sleep(interval)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    apply = sub.add_parser('apply')
    apply.add_argument('--bundle-dir', type=Path, required=True)
    apply.add_argument('--database', type=Path, default=ROOT/'data/igdb.sqlite3')
    update = sub.add_parser('update')
    update.add_argument('--repository', required=True)
    update.add_argument('--database', type=Path, default=ROOT/'data/igdb.sqlite3')
    publish = sub.add_parser('publish')
    publish.add_argument('--repository', required=True)
    publish.add_argument('--bundle-dir', type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == 'apply':
            result = apply_bundle(args.database, json.loads((args.bundle_dir/MANIFEST).read_bytes()),
                                  (args.bundle_dir/PACKAGE).read_bytes())
        elif args.command == 'update':
            result = update_from_github(args.database, args.repository)
        else:
            result = publish_bundle(args.repository, args.bundle_dir, os.environ.get('GITHUB_TOKEN', ''))
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(f'ERROR: {type(exc).__name__}；任务失败，详情请检查本地配置和日志。')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
