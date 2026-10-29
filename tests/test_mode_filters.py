import json
import sqlite3
import unittest
from datetime import datetime, timezone
import test_independent_filters as fixture


class ModeFiltersTest(unittest.TestCase):
    get = fixture.IndependentFiltersTest.get
    tearDown = fixture.IndependentFiltersTest.tearDown

    def setUp(self):
        fixture.IndependentFiltersTest.setUp(self)
        with sqlite3.connect(self.db) as c:
            for ident, modes in [(4, [3]), (5, [1, 3]), (6, [4]), (7, [])]:
                c.execute('''INSERT INTO igdb_games(igdb_id,name,first_release_date,
                    platforms_json,genres_json,raw_json,fetched_at,game_type_key)
                    VALUES(?,?,?,?,?,?,?,?)''', (ident, f'Game {ident}',
                    int(datetime(2016, 1, 1, tzinfo=timezone.utc).timestamp()),
                    '[]', '[]', json.dumps({'id': ident}), 'fixture', 'main_game'))
                for mode in modes:
                    c.execute('INSERT INTO game_tags VALUES(?,?,?,?)', (ident, 'mode', mode, f'Mode {mode}'))
                c.execute('INSERT INTO game_tags VALUES(?,?,?,?)', (ident, 'platform', 6, 'Windows'))
                c.execute('INSERT INTO game_tags VALUES(?,?,?,?)', (ident, 'genre', 31, 'Adventure'))
        c.close()
        self.before = self.db.read_bytes()

    def test_or_matching_deduplication_and_stable_pagination(self):
        first = self.get('games', year=2016, mode_ids='3,1,3', page_size=2)
        second = self.get('games', year=2016, mode_ids='1,3', page_size=2, page=2)
        self.assertEqual(first['total'], 3)
        self.assertEqual([g['igdb_id'] for g in first['items']+second['items']], [1, 4, 5])

    def test_legacy_union_and_empty_includes_missing_modes(self):
        self.assertEqual(self.get('games', year=2016, mode_id=1)['total'], 2)
        self.assertEqual(self.get('games', year=2016, mode_id=4, mode_ids='1,3')['total'], 4)
        self.assertEqual(self.get('games', year=2016, mode_ids='')['total'], 5)
        self.assertEqual(self.get('games', year=2016, mode_ids='999')['total'], 0)

    def test_other_categories_intersect_and_global_search_bypasses_modes(self):
        self.assertEqual(self.get('games', year=2016, mode_ids='1,3', platform_ids='167')['total'], 0)
        self.assertEqual(self.get('games', year=2016, mode_ids='1,3', genre_ids='31')['total'], 3)
        params = dict(q='Game 2', year=2016, mode_ids='1,3', platform_ids='6')
        self.assertEqual(self.get('games', **params, search_scope='global')['total'], 1)
        self.assertEqual(self.get('games', **params, search_scope='filtered')['total'], 0)

    def test_invalid_parameters_and_injection_are_rejected(self):
        for value in ['1,', '1,-1', '1,1e3', '１', '2147483648', '1);DROP TABLE game_tags;--', ','.join(['1']*101), '9'*1101]:
            with self.subTest(value=value[:30]):
                self.assertEqual(self.client.get('/api/v1/games', params={'mode_ids': value}).status_code, 422)


if __name__ == '__main__':
    unittest.main()
