"""Global option dictionaries and existing list-query boundaries."""
import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from fastapi.testclient import TestClient
from game_platform import api, classify_games, collect_igdb


class IndependentFiltersTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / 'catalog.sqlite3'
        connection = collect_igdb.initialize(self.db)
        classify_games.migrate(connection)
        for ident, year, kind, platform, genre, mode in [
            (1, 2016, 'main_game', 6, 31, 1),
            (2, 2026, 'dlc_addon', 167, 12, 2),
            (3, 2020, 'unknown', 7, 5, 3),
        ]:
            connection.execute('''INSERT INTO igdb_games(igdb_id,name,first_release_date,
                platforms_json,genres_json,raw_json,fetched_at,game_type_key)
                VALUES(?,?,?,?,?,?,?,?)''', (ident, f'Game {ident}',
                int(datetime(year, 1, 1, tzinfo=timezone.utc).timestamp()), '[]', '[]',
                json.dumps({'id': ident, 'name': f'Game {ident}'}), 'fixture', kind))
            for tag_kind, tag_id in [('platform', platform), ('genre', genre), ('mode', mode)]:
                connection.execute('INSERT INTO game_tags VALUES(?,?,?,?)',
                    (ident, tag_kind, tag_id, f'{tag_kind} {tag_id}'))
        connection.commit()
        connection.close()
        self.before = self.db.read_bytes()
        self.client = TestClient(api.create_app(self.db))

    def tearDown(self):
        self.client.close()
        self.assertEqual(self.before, self.db.read_bytes(), 'API must remain read-only')
        self.tmp.cleanup()

    def get(self, path, **params):
        response = self.client.get('/api/v1/' + path, params=params)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_global_options_include_every_year_and_scope(self):
        data = self.get('filter-options')
        self.assertEqual(data['available_years'], [2016, 2020, 2026])
        self.assertEqual({p['id'] for p in data['platforms']}, {6, 7, 167})
        self.assertEqual({p['id'] for p in data['genres']}, {31, 12, 5})
        self.assertEqual({p['id'] for p in data['game_modes']}, {1, 2, 3})
        self.assertEqual({t['key']: t['count'] for t in data['game_types'] if t['count']},
                         {'main_game': 1, 'dlc_addon': 1, 'unknown': 1})
        for key in ['year', 'scope']:
            self.assertNotIn(key, data)
        self.assertEqual(self.get('filter-options', year=2026, scope='unknown'), data)

    def test_old_endpoint_stays_compatible_but_new_options_are_global(self):
        local = self.get('filters', year=2016)
        self.assertEqual([p['id'] for p in local['platforms']], [6])
        self.assertEqual(len(self.get('filter-options')['platforms']), 3)

    def test_nonexistent_combination_is_an_empty_page_not_an_error(self):
        data = self.get('games', year=2026, scope='all', platform_ids='6', genre_id=31, mode_id=1)
        self.assertEqual(data['total'], 0)
        self.assertEqual(data['items'], [])

    def test_scope_and_type_remain_an_intersection(self):
        self.assertEqual(self.get('games', year=2026, scope='all', game_type='dlc_addon')['total'], 1)
        self.assertEqual(self.get('games', year=2026, scope='default', game_type='dlc_addon')['total'], 0)
        self.assertEqual(self.get('games', year=2020, scope='unknown', game_type='unknown')['total'], 1)

    def test_global_and_filtered_search_keep_their_existing_boundaries(self):
        params = dict(q='Game 2', year=2016, scope='default', platform_id=6)
        self.assertEqual(self.get('games', **params, search_scope='global')['total'], 1)
        self.assertEqual(self.get('games', **params, search_scope='filtered')['total'], 0)

    def test_missing_database_is_not_silently_created(self):
        missing = Path(self.tmp.name) / 'missing.sqlite3'
        with TestClient(api.create_app(missing)) as client:
            self.assertEqual(client.get('/api/v1/filter-options').status_code, 503)
        self.assertFalse(missing.exists())


if __name__ == '__main__':
    unittest.main()
