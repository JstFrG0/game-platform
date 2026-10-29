import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from game_platform.api import create_app, source_url
from game_platform.classify_games import migrate, sync_types
from test_classification import seed, TypesAPI


@pytest.fixture
def detail_catalog(tmp_path):
    path = tmp_path/'igdb.sqlite3'
    c, _ = seed(path)
    row = c.execute('SELECT raw_json FROM igdb_games WHERE igdb_id=1').fetchone()
    record = json.loads(row['raw_json'])
    record.update(summary='Source summary', storyline='Story text',
                  cover={'id': 8, 'url': '//images.igdb.com/igdb/image/upload/t_thumb/cover.jpg'},
                  url='https://www.igdb.com/games/main',
                  alternative_names=[{'name': 'Alias'}, {'name': 'Alias'}, {'name': '中文别名'}],
                  involved_companies=[{'company': {'id': 7, 'name': 'Studio'}, 'developer': True, 'publisher': False}],
                  parent_game=2, version_parent=999, version_title='Gold Edition')
    with c:
        c.execute('UPDATE igdb_games SET raw_json=?,summary=? WHERE igdb_id=1', (json.dumps(record), record['summary']))
    migrate(c); sync_types(TypesAPI(), c); c.close()
    return path


def test_detail_full_source_fields_and_related_games(detail_catalog):
    with TestClient(create_app(detail_catalog)) as client:
        response = client.get('/api/v1/games/1')
        assert response.status_code == 200
        row = response.json()
        assert row['summary'] == 'Source summary' and row['storyline'] == 'Story text'
        assert row['cover_url'].startswith('https://images.igdb.com/')
        assert row['igdb_url'] == 'https://www.igdb.com/games/main'
        assert row['alternative_names'] == ['Alias', '中文别名']
        assert row['companies'] == [{'id': 7, 'name': 'Studio', 'developer': True, 'publisher': False}]
        assert row['parent_game'] == {'igdb_id': 2, 'name': 'Unrated remake', 'available_locally': True}
        assert row['version_parent'] == {'igdb_id': 999, 'name': None, 'available_locally': False}
        assert row['version_title'] == 'Gold Edition'
        assert row['rating'] == 0 and row['rating_count'] == 1
        assert row['platforms'][0]['id'] == 6 and row['game_modes'][0]['id'] == 1
        assert row['fetched_at'] and 'raw_json' not in row and row['ign_reviews'] is None
        listed = client.get('/api/v1/games', params={'q': 'Main'}).json()['items'][0]
        assert listed['cover_url'] == row['cover_url']


def test_missing_optional_data_and_hidden_dlc_still_accessible(detail_catalog):
    with TestClient(create_app(detail_catalog)) as client:
        remake = client.get('/api/v1/games/2').json()
        for key in ['summary', 'storyline', 'cover_url', 'igdb_url', 'parent_game', 'version_parent', 'version_title', 'rating']:
            assert remake[key] is None
        assert remake['alternative_names'] == [] and remake['companies'] == []
        dlc = client.get('/api/v1/games/3')
        assert dlc.status_code == 200 and dlc.json()['game_type'] == 'dlc_addon'


def test_not_found_and_invalid_ids(detail_catalog):
    with TestClient(create_app(detail_catalog)) as client:
        response = client.get('/api/v1/games/123456')
        assert response.status_code == 404 and response.json()['detail']['code'] == 'GAME_NOT_FOUND'
        for ident in ['0', '-1', 'not-an-id', '9223372036854775808']:
            assert client.get('/api/v1/games/'+ident).status_code == 422


def test_detail_read_only_and_corrupt_source_error(detail_catalog):
    with sqlite3.connect(detail_catalog) as c:
        before = list(c.execute('SELECT * FROM igdb_games'))
    with TestClient(create_app(detail_catalog)) as client:
        client.get('/api/v1/games/1')
        schema = client.get('/openapi.json').json()
        assert '/api/v1/games/{igdb_id}' in schema['paths']
    with sqlite3.connect(detail_catalog) as c:
        assert list(c.execute('SELECT * FROM igdb_games')) == before
        c.execute("UPDATE igdb_games SET raw_json='not json' WHERE igdb_id=1")
    with TestClient(create_app(detail_catalog)) as client:
        response = client.get('/api/v1/games/1')
        assert response.status_code == 503 and response.json()['detail']['code'] == 'SOURCE_DATA_INVALID'


@pytest.mark.parametrize('value', [None, '', 'javascript:alert(1)', '/relative/path', 'https://user:secret@example.com/cover'])
def test_invalid_source_urls_are_not_returned(value):
    assert source_url(value) is None
