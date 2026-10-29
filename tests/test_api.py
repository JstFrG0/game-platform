import sqlite3

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from game_platform.api import create_app, database
from game_platform.classify_games import migrate, sync_types
from test_classification import seed, TypesAPI


@pytest.fixture
def catalog(tmp_path):
    path = tmp_path/'igdb.sqlite3'
    c, _ = seed(path)
    migrate(c); sync_types(TypesAPI(), c)
    c.close()
    return path


@pytest.fixture
def client(catalog):
    with TestClient(create_app(catalog)) as result:
        yield result


def test_default_pagination_and_null_preserved(client):
    page = client.get('/api/v1/games', params={'page_size': 2}).json()
    assert page['total'] == 3 and page['total_pages'] == 2 and page['has_next']
    assert [r['igdb_id'] for r in page['items']] == [1, 2]
    assert page['items'][0]['rating'] == 0 and page['items'][1]['rating'] is None
    assert page['items'][0]['platforms'] == [{'id': 6, 'name': 'Windows'}]
    assert 'raw_json' not in page['items'][0]
    second = client.get('/api/v1/games', params={'page_size': 2, 'page': 2}).json()
    assert [r['igdb_id'] for r in second['items']] == [6] and not second['has_next']
    assert client.get('/api/v1/games', params={'page': 99}).json()['items'] == []


def test_exact_filters_and_scope(client):
    params = {'platform_id': 6, 'genre_id': 12, 'mode_id': 1}
    assert client.get('/api/v1/games', params=params).json()['total'] == 1
    assert client.get('/api/v1/games', params={'platform_id': 60}).json()['total'] == 0
    assert client.get('/api/v1/games', params={'scope': 'all'}).json()['total'] == 6
    assert client.get('/api/v1/games', params={'scope': 'unknown'}).json()['total'] == 2
    dlc = client.get('/api/v1/games', params={'scope': 'all', 'game_type': 'dlc_addon'}).json()
    assert [r['igdb_id'] for r in dlc['items']] == [3]
    assert client.get('/api/v1/games', params={'game_type': 'dlc_addon'}).json()['total'] == 0
    assert client.get('/api/v1/games', params={'scope': 'all', 'year': 2024}).json()['total'] == 0


def test_rating_filters_use_user_score_and_counts(client):
    result = client.get('/api/v1/games', params={'scope': 'all', 'min_rating': 0, 'min_rating_count': 1}).json()
    assert [r['igdb_id'] for r in result['items']] == [1]
    assert client.get('/api/v1/games', params={'min_rating': 1}).json()['total'] == 0
    result = client.get('/api/v1/games', params={'scope': 'all', 'min_rating': 80}).json()
    assert result['items'][0]['igdb_id'] == 3


def test_rating_sort_null_last_and_stable_ties(client):
    for sort, ids in [('rating_desc', [3, 1]), ('rating_asc', [1, 3])]:
        result = client.get('/api/v1/games', params={'scope': 'all', 'sort': sort}).json()
        assert [r['igdb_id'] for r in result['items'][:2]] == ids
        assert all(r['rating'] is None for r in result['items'][2:])


def test_name_search_is_literal_and_parameterized(client):
    result = client.get('/api/v1/games', params={'q': '  REMAKE  '}).json()
    assert result['total'] == 1 and result['items'][0]['igdb_id'] == 2
    for text in ['%', '_', "' OR 1=1 --"]:
        assert client.get('/api/v1/games', params={'q': text, 'scope': 'all'}).json()['total'] == 0
    assert client.get('/api/v1/games', params={'q': '   '}).json()['total'] == 3


@pytest.mark.parametrize('params', [
    {'page': 0}, {'page': 1000001}, {'page_size': 101}, {'page_size': 0},
    {'min_rating': 101}, {'min_rating': -1}, {'min_rating': 'nan'},
    {'min_rating_count': -1}, {'year': 1949}, {'scope': 'bad'},
    {'sort': 'g.name; DROP TABLE igdb_games'}, {'game_type': 'bad'},
    {'platform_id': -1}, {'q': 'a'*101},
])
def test_invalid_query_returns_422(client, params):
    assert client.get('/api/v1/games', params=params).status_code == 422


def test_filter_options_counts_and_available_years(client):
    r = client.get('/api/v1/filters').json()
    assert r['available_years'] == [2025]
    types = {t['key']: t for t in r['game_types']}
    assert types['dlc_addon']['count'] == 1 and not types['dlc_addon']['default_visible']
    assert types['main_game']['count'] == 1 and types['main_game']['default_visible']
    assert r['platforms'] == [{'id': 6, 'name': 'Windows', 'count': 1}]
    assert sum(t['count'] for t in r['game_types']) == 6
    assert client.get('/api/v1/filters', params={'year': 2024}).json()['platforms'] == []


def test_health_and_openapi(client):
    assert client.get('/health').json() == {'status': 'ok', 'schema_version': 2, 'read_only': True}
    schema = client.get('/openapi.json').json()
    assert '/api/v1/games' in schema['paths'] and 'GamePage' in schema['components']['schemas']
    assert client.get('/docs').status_code == 200


def test_missing_database_does_not_create_file_and_docs_still_accessible(tmp_path):
    path = tmp_path/'missing.sqlite3'
    with TestClient(create_app(path)) as c:
        assert c.get('/api/v1/games').status_code == 503
        assert c.get('/health').json()['detail']['code'] == 'DATABASE_NOT_FOUND'
        assert c.get('/docs').status_code == 200
    assert not path.exists()


def test_unmigrated_database_has_clear_error(tmp_path):
    path = tmp_path/'igdb.sqlite3'
    c, _ = seed(path); c.close()
    with TestClient(create_app(path)) as client:
        result = client.get('/api/v1/games')
        assert result.status_code == 503 and result.json()['detail']['code'] == 'SCHEMA_NOT_READY'


def test_api_does_not_write_and_database_rejects_writes(client, catalog):
    with sqlite3.connect(catalog) as c:
        before = list(c.execute('SELECT igdb_id,raw_json,rating,rating_count FROM igdb_games'))
    client.get('/api/v1/games'); client.get('/api/v1/filters'); client.get('/health')
    with sqlite3.connect(catalog) as c:
        assert list(c.execute('SELECT igdb_id,raw_json,rating,rating_count FROM igdb_games')) == before
    with pytest.raises(HTTPException) as error:
        with database(catalog) as c:
            c.execute('DELETE FROM igdb_games')
    assert error.value.status_code == 503
