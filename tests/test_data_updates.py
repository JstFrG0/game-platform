import asyncio
import json
import sqlite3

import httpx
import pytest
from fastapi.testclient import TestClient

from game_platform import data_updates as updates
from game_platform.api import create_app
from game_platform.classify_games import migrate
from game_platform.daily_catalog import run_daily
from game_platform.ign_reviews import apply_links, import_records, migrate as migrate_ign, read_import
from test_classification import seed, TypesAPI
from test_collection import FakeAPI, RELEASE
from test_ign_reviews import review, source


def record(ident=1, **extra):
    return dict(id=ident, name='Updated', first_release_date=RELEASE,
                category=0, platforms=[{'id': 6, 'name': 'PC'}], **extra)


def bundle(tmp_path, records=None):
    manifest = updates.build_bundle(records if records is not None else [record()], tmp_path)
    return manifest, (tmp_path/updates.PACKAGE).read_bytes()


def test_updates_preserve_ign_links_and_old_games_and_are_idempotent(tmp_path):
    path = tmp_path/'catalog.sqlite3'
    c, _ = seed(path)
    migrate(c)
    migrate_ign(c)
    reviews, _ = read_import(source(tmp_path, [review()]))
    import_records(c, reviews, 'reviews.csv')
    apply_links(c, [(reviews[0]['ign_game_url'], 1)], 'manual_csv')
    before = [tuple(r) for r in c.execute('SELECT * FROM ign_links')]
    manifest, package = bundle(tmp_path/'release', [record(rating=0, rating_count=1), record(99)])
    result = updates.apply_bundle(path, manifest, package)
    assert result['status'] == 'updated'
    assert c.execute('SELECT name,rating FROM igdb_games WHERE igdb_id=1').fetchone()[:] == ('Updated', 0)
    assert c.execute('SELECT count(*) FROM igdb_games').fetchone()[0] == 7
    assert [tuple(r) for r in c.execute('SELECT * FROM ign_links')] == before
    assert c.execute('SELECT name FROM game_tags WHERE igdb_id=1').fetchone()[0] == 'PC'
    with sqlite3.connect(result['backup']) as backup:
        assert backup.execute('SELECT name FROM igdb_games WHERE igdb_id=1').fetchone()[0] == 'Main'
    assert updates.apply_bundle(path, manifest, package)['status'] == 'up_to_date'
    assert len(list((tmp_path/'backups').glob('*.sqlite3'))) == 1
    c.close()


def test_entire_merge_and_receipt_roll_back_on_sql_error(tmp_path):
    path = tmp_path/'catalog.sqlite3'
    c, _ = seed(path)
    migrate(c)
    with c:
        c.execute("CREATE TRIGGER reject_new BEFORE INSERT ON igdb_games WHEN NEW.igdb_id=99 BEGIN SELECT RAISE(ABORT,'reject'); END")
    manifest, package = bundle(tmp_path/'release', [record(), record(99)])
    with pytest.raises(sqlite3.IntegrityError):
        updates.apply_bundle(path, manifest, package)
    assert c.execute('SELECT name FROM igdb_games WHERE igdb_id=1').fetchone()[0] == 'Main'
    assert c.execute('SELECT 1 FROM igdb_games WHERE igdb_id=99').fetchone() is None
    assert c.execute("SELECT 1 FROM sqlite_master WHERE name='data_update_receipts'").fetchone() is None
    c.close()


def test_bootstrap_and_downgrade_and_version_collision(tmp_path):
    older, old_package = bundle(tmp_path/'old')
    newer, new_package = bundle(tmp_path/'new', [record(2)])
    path = tmp_path/'new-db/igdb.sqlite3'
    updates.apply_bundle(path, newer, new_package)
    with pytest.raises(ValueError, match='旧版本'):
        updates.apply_bundle(path, older, old_package)
    older.update(version=newer['version'], created_at=newer['created_at'])
    with pytest.raises(ValueError, match='相同版本'):
        updates.apply_bundle(path, older, old_package)


@pytest.mark.parametrize('fault', ['hash', 'count', 'format', 'records_hash', 'size'])
def test_reject_corruption_before_touching_database(tmp_path, fault):
    manifest, package = bundle(tmp_path/'release')
    if fault == 'hash':
        package = package[:-1] + bytes([package[-1] ^ 1])
    elif fault == 'count':
        manifest['record_count'] += 1
    elif fault == 'format':
        manifest['format_version'] = 2
    elif fault == 'records_hash':
        manifest['records_sha256'] = '0'*64
    else:
        manifest['records_size'] += 1
    path = tmp_path/'must-not-exist.sqlite3'
    with pytest.raises(ValueError):
        updates.apply_bundle(path, manifest, package)
    assert not path.exists()


def test_reject_duplicates_empty_and_bad_records(tmp_path):
    for records in ([], [record(), record()], [record(rating=101)], [dict(id=True)]):
        with pytest.raises((ValueError, KeyError)):
            updates.build_bundle(records, tmp_path)


def github_client(manifest, package, missing=False):
    root = 'https://github.com/owner/repo/releases/download/data-test/'
    def handler(request):
        assert 'authorization' not in request.headers
        if request.url.host == 'api.github.com':
            assets = [{'name': n, 'browser_download_url': root+n} for n in (updates.MANIFEST, updates.PACKAGE)]
            if missing:
                assets.pop()
            return httpx.Response(200, json=[
                dict(tag_name='v99', published_at='2099', assets=[]),
                dict(tag_name='data-test', published_at='2026', assets=assets)])
        return httpx.Response(200, content=updates.json_bytes(manifest) if request.url.path.endswith('.json') else package)
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_github_ignores_software_releases_and_applies_data(tmp_path):
    manifest, package = bundle(tmp_path/'release')
    with github_client(manifest, package) as client:
        result = updates.update_from_github(tmp_path/'db.sqlite3', 'owner/repo', client)
    assert result['status'] == 'updated'


@pytest.mark.parametrize('redirect', [False, True])
def test_private_download_authenticates_api_and_strips_token_on_redirect(tmp_path, monkeypatch, redirect):
    manifest, package = bundle(tmp_path/'release')
    monkeypatch.setenv('GAME_DATA_GITHUB_TOKEN', 'read-only-test-token')
    calls = []
    def handler(request):
        calls.append(str(request.url))
        if request.url.host != 'api.github.com':
            assert request.url.host == 'release-assets.githubusercontent.com'
            assert 'authorization' not in request.headers
            return httpx.Response(200, content=updates.json_bytes(manifest)
                                  if request.url.path == '/1' else package)
        assert request.headers['authorization'] == 'Bearer read-only-test-token'
        if '/releases/assets/' not in request.url.path:
            assert request.headers['accept'] == 'application/vnd.github+json'
            # A response-supplied URL must never receive credentials.
            return httpx.Response(200, json=[dict(tag_name='data-test', assets=[
                dict(name=updates.MANIFEST, id=1, url='https://untrusted.example/1'),
                dict(name=updates.PACKAGE, id=2, url='https://untrusted.example/2')])])
        assert request.headers['accept'] == 'application/octet-stream'
        ident = request.url.path.rsplit('/', 1)[1]
        if redirect:
            return httpx.Response(302, headers={'location': f'https://release-assets.githubusercontent.com/{ident}'})
        return httpx.Response(200, content=updates.json_bytes(manifest) if ident == '1' else package)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert updates.update_from_github(tmp_path/'db.sqlite3', 'owner/repo', client)['status'] == 'updated'
    assert len(calls) == (5 if redirect else 3)


@pytest.mark.parametrize('status', [401, 403, 404])
def test_private_auth_failure_does_not_touch_database(tmp_path, status):
    def handler(request):
        assert request.headers['authorization'] == 'Bearer invalid-token'
        return httpx.Response(status)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(httpx.HTTPStatusError):
            updates.update_from_github(tmp_path/'db.sqlite3', 'owner/repo', client, token='invalid-token')
    assert not (tmp_path/'db.sqlite3').exists()


@pytest.mark.parametrize('location', ['http://example.com/file', 'https://name:password@example.com/file'])
def test_asset_rejects_insecure_redirect(tmp_path, location):
    def handler(request):
        return httpx.Response(302, headers={'location': location})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ValueError, match='重定向地址无效'):
            updates.download(client, 'https://api.github.com/repos/owner/repo/releases/assets/1', 100,
                             {'Authorization': 'Bearer test-token'})


def test_credentials_are_stripped_even_on_same_origin_redirect():
    calls = []
    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(302, headers={'location': '/signed-download'})
        assert 'authorization' not in request.headers
        return httpx.Response(200, content=b'ok')
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert updates.download(client, 'https://api.github.com/asset', 100,
                                {'Authorization': 'Bearer test-token'}) == b'ok'


def test_missing_assets_and_oversized_download_keep_database_absent(tmp_path):
    manifest, package = bundle(tmp_path/'release')
    with github_client(manifest, package, missing=True) as client:
        with pytest.raises(ValueError, match='缺少'):
            updates.update_from_github(tmp_path/'db.sqlite3', 'owner/repo', client)
    with github_client(manifest, package+b'extra') as client:
        with pytest.raises(ValueError, match='大小限制'):
            updates.update_from_github(tmp_path/'db.sqlite3', 'owner/repo', client)
    assert not (tmp_path/'db.sqlite3').exists()


@pytest.mark.parametrize('fail_upload', [False, True])
def test_publish_only_exposes_release_after_both_uploads(tmp_path, fail_upload):
    bundle(tmp_path)
    calls = []
    def handler(request):
        calls.append((request.method, request.url.host))
        assert request.headers['authorization'] == 'Bearer test-token'
        if request.url.host == 'uploads.github.com':
            return httpx.Response(500 if fail_upload else 201, json={})
        if request.method == 'POST':
            assert json.loads(request.content)['draft'] is True
            return httpx.Response(201, json={'id': 42})
        assert len(calls) == 4
        assert json.loads(request.content)['draft'] is False
        return httpx.Response(200, json={'html_url': 'https://github.com/owner/repo/releases/tag/data-test'})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        if fail_upload:
            with pytest.raises(httpx.HTTPStatusError):
                updates.publish_bundle('owner/repo', tmp_path, 'test-token', client)
            assert all(method != 'PATCH' for method, _ in calls)
        else:
            assert updates.publish_bundle('owner/repo', tmp_path, 'test-token', client)['status'] == 'published'


class DailyAPI(FakeAPI):
    def query(self, endpoint, body):
        if endpoint == 'game_types':
            return TypesAPI().query(endpoint, body)
        return super().query(endpoint, body)


def test_daily_build_has_verified_counts_and_embedded_types(tmp_path):
    report = run_daily(DailyAPI([record(game_type=100)]), [2025], tmp_path)
    assert report['status'] == 'built'
    assert report['scans'][0]['count_check_passed']
    raw = updates.read_bundle(report['manifest'], (tmp_path/updates.PACKAGE).read_bytes())
    assert raw[0]['game_type'] == {'id': 100, 'type': 'Main Game'}
    assert json.loads((tmp_path/'daily-report.json').read_bytes())['status'] == 'built'


def test_failed_collection_never_builds_or_publishes(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('failed scan must not publish')
    monkeypatch.setattr('game_platform.daily_catalog.publish_bundle', forbidden)
    with pytest.raises(ValueError, match='计数校验'):
        run_daily(DailyAPI([record()], fail_after=0), [2025], tmp_path, 'owner/repo', 'test-token')
    assert json.loads((tmp_path/'daily-report.json').read_bytes())['status'] == 'failed'
    assert not (tmp_path/updates.MANIFEST).exists()


def test_api_auto_update_runs_on_start_and_is_observable(tmp_path, monkeypatch):
    import time
    from game_platform import update_service
    calls = []
    def background(path, repository, **kwargs):
        calls.append((path, repository))
        return {'status': 'up_to_date', 'version': '2025-01-01T00:00:00+00:00'}
    monkeypatch.setattr(update_service, 'update_from_github', background)
    monkeypatch.setattr(update_service, 'read_token', lambda *args: 'test-token')
    monkeypatch.setenv('GAME_DATA_REPOSITORY', 'owner/repo')
    monkeypatch.setenv('GAME_DATA_UPDATE_INTERVAL_SECONDS', '600')
    path = tmp_path/'db.sqlite3'
    with TestClient(create_app(path)) as client:
        for _ in range(100):
            state = client.get('/api/v1/data-updates').json()
            if state['status'] == 'up_to_date':
                break
            time.sleep(0.01)
        assert state['status'] == 'up_to_date' and state['interval_seconds'] == 600
    assert calls == [(path, 'owner/repo')]


def test_background_failure_preserves_local_catalog(tmp_path, monkeypatch):
    state = {}
    def fail(*args):
        raise httpx.ConnectError('offline')
    monkeypatch.setattr(updates, 'update_from_github', fail)
    async def run():
        task = asyncio.create_task(updates.automatic_updates(tmp_path/'db.sqlite3', 'owner/repo', 60, state))
        for _ in range(100):
            if state.get('status') == 'failed':
                break
            await asyncio.sleep(0.01)
        assert state['status'] == 'failed' and state['error'] == 'ConnectError'
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    asyncio.run(run())
    assert not (tmp_path/'db.sqlite3').exists()


def test_process_lock_prevents_overlapping_writers(tmp_path):
    with updates.operation_lock(tmp_path/'test.lock'):
        with pytest.raises(RuntimeError, match='已有更新任务'):
            with updates.operation_lock(tmp_path/'test.lock'):
                pytest.fail('lock must exclude concurrent writers')


def ign_entry(ids=None, score=8):
    return {'review': dict(name='Updated', score=score,
        review_url='https://www.ign.com/articles/updated-review',
        ign_game_url='https://www.ign.com/games/updated', platforms=['PC'],
        us_release_date='2025-06-01', review_date='2025-06-02', reviewed_on='PC',
        scope='一般评测', title='Updated Review', verdict='Example verdict', raw_json='{}'),
        'igdb_ids': [1] if ids is None else ids}


def test_v2_bootstrap_includes_ign_details_and_multiple_targets(tmp_path):
    manifest = updates.build_bundle([record(), record(2)], tmp_path/'release',
                                    ign_reviews=[ign_entry([1, 2])])
    package = (tmp_path/'release'/updates.PACKAGE).read_bytes()
    path = tmp_path/'catalog.sqlite3'
    result = updates.apply_bundle(path, manifest, package)
    assert result['ign_reviews'] == 1 and manifest['format_version'] == 2
    with TestClient(create_app(path)) as client:
        for ident in (1, 2):
            detail = client.get(f'/api/v1/games/{ident}').json()
            assert detail['ign_reviews'][0]['score'] == 8
            assert detail['ign_reviews'][0]['verdict'] == 'Example verdict'


def test_v2_preserves_existing_manual_article_binding(tmp_path):
    path = tmp_path/'catalog.sqlite3'
    manifest, package = bundle(tmp_path/'initial', [record(), record(2)])
    updates.apply_bundle(path, manifest, package)
    c = sqlite3.connect(path)
    c.row_factory = sqlite3.Row
    migrate_ign(c)
    entry = ign_entry()
    import_records(c, [entry['review']], 'manual')
    with c:
        c.execute("INSERT INTO ign_review_bindings VALUES(?,?,'manual_csv',?,?)",
                  (entry['review']['review_url'], '单人战役', updates.utc_now(), 'User decision'))
        c.execute('INSERT INTO ign_review_binding_targets VALUES(?,2)', (entry['review']['review_url'],))
    manifest = updates.build_bundle([record(), record(2)], tmp_path/'new', ign_reviews=[ign_entry(score=9)])
    result = updates.apply_bundle(path, manifest, (tmp_path/'new'/updates.PACKAGE).read_bytes())
    assert result['status'] == 'updated'
    assert c.execute('SELECT score FROM ign_reviews').fetchone()[0] == 9
    assert c.execute('SELECT igdb_id FROM ign_review_binding_targets').fetchone()[0] == 2
    assert c.execute('SELECT scope_override FROM ign_review_bindings').fetchone()[0] == '单人战役'
    c.close()


def test_v2_rolls_back_games_and_reviews_together(tmp_path):
    path = tmp_path/'catalog.sqlite3'
    c, _ = seed(path)
    migrate(c)
    migrate_ign(c)
    with c:
        c.execute("CREATE TRIGGER reject_review BEFORE INSERT ON ign_reviews BEGIN SELECT RAISE(ABORT,'reject'); END")
    manifest = updates.build_bundle([record()], tmp_path/'release', ign_reviews=[ign_entry()])
    with pytest.raises(sqlite3.IntegrityError):
        updates.apply_bundle(path, manifest, (tmp_path/'release'/updates.PACKAGE).read_bytes())
    assert c.execute('SELECT name FROM igdb_games WHERE igdb_id=1').fetchone()[0] == 'Main'
    assert c.execute('SELECT count(*) FROM ign_reviews').fetchone()[0] == 0
    assert c.execute("SELECT 1 FROM sqlite_master WHERE name='data_update_receipts'").fetchone() is None
    c.close()


@pytest.mark.parametrize('entry', [ign_entry([99]), ign_entry(score=11), ign_entry(score=True)])
def test_v2_rejects_bad_ign_before_writing(tmp_path, entry):
    with pytest.raises(ValueError):
        updates.build_bundle([record()], tmp_path, ign_reviews=[entry])


def test_v2_rejects_ign_count_or_hash_mismatch(tmp_path):
    manifest = updates.build_bundle([record()], tmp_path/'release', ign_reviews=[ign_entry()])
    package = (tmp_path/'release'/updates.PACKAGE).read_bytes()
    manifest['ign_record_count'] += 1
    with pytest.raises(ValueError, match='评测数量'):
        updates.apply_bundle(tmp_path/'db.sqlite3', manifest, package)
    manifest['ign_record_count'] -= 1
    manifest['ign_records_sha256'] = '0'*64
    with pytest.raises(ValueError, match='IGN SHA'):
        updates.apply_bundle(tmp_path/'db.sqlite3', manifest, package)
    assert not (tmp_path/'db.sqlite3').exists()


def test_v2_clears_postponed_release_date_and_api_remains_readable(tmp_path):
    from game_platform.ign_reviews import candidates
    path = tmp_path/'db.sqlite3'
    first, package = bundle(tmp_path/'initial')
    updates.apply_bundle(path, first, package)
    entry = ign_entry([])
    postponed = record()
    postponed['first_release_date'] = None
    second = updates.build_bundle([postponed], tmp_path/'postponed', ign_reviews=[entry])
    updates.apply_bundle(path, second, (tmp_path/'postponed'/updates.PACKAGE).read_bytes())
    with TestClient(create_app(path)) as client:
        assert client.get('/api/v1/games/1').json()['first_release_date_utc'] is None
        assert client.get('/api/v1/games', params={'year': 2025}).json()['total'] == 0
        assert client.get('/api/v1/filter-options').json()['available_years'] == []
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    matches = candidates(connection)
    assert matches[0]['eligible_igdb_id'] is None
    assert matches[0]['candidates'][0]['release_date'] is None
    connection.close()


def test_same_version_only_downloads_manifest(tmp_path):
    manifest, package = bundle(tmp_path/'release')
    database = tmp_path/'db.sqlite3'
    updates.apply_bundle(database, manifest, package)
    calls = []
    root = 'https://github.com/owner/repo/releases/download/data-test/'
    def handler(request):
        calls.append(str(request.url))
        if request.url.host == 'api.github.com':
            return httpx.Response(200, json=[dict(tag_name='data-test', assets=[
                dict(name=n, browser_download_url=root+n) for n in (updates.MANIFEST, updates.PACKAGE)])])
        assert request.url.path.endswith(updates.MANIFEST), 'unchanged package must not download again'
        return httpx.Response(200, json=manifest)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert updates.update_from_github(database, 'owner/repo', client, token='')['status'] == 'up_to_date'
    assert len(calls) == 2
