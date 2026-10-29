import json
import sqlite3
import unittest
from datetime import datetime, timezone
import test_independent_filters as fixture

class GenreFiltersTest(unittest.TestCase):
    get = fixture.IndependentFiltersTest.get
    tearDown = fixture.IndependentFiltersTest.tearDown

    def setUp(self):
        fixture.IndependentFiltersTest.setUp(self)
        with sqlite3.connect(self.db) as c:
            for ident, tags in [(4, [12]), (5, [12, 31]), (6, [5])]:
                c.execute('''INSERT INTO igdb_games(igdb_id,name,first_release_date,
                    platforms_json,genres_json,raw_json,fetched_at,game_type_key)
                    VALUES(?,?,?,?,?,?,?,?)''', (ident, f'Game {ident}',
                    int(datetime(2016,1,1,tzinfo=timezone.utc).timestamp()),'[]','[]',json.dumps({'id':ident}), 'fixture','main_game'))
                for tag in tags:
                    c.execute('INSERT INTO game_tags VALUES(?,?,?,?)',(ident,'genre',tag,str(tag)))
                c.execute('INSERT INTO game_tags VALUES(?,?,?,?)',(ident,'platform',6,'Windows'))
        c.close()
        self.before = self.db.read_bytes()

    def test_any_match_with_deduplication_and_stable_paging(self):
        result = self.get('games',year=2016,genre_ids='31,12,31')
        self.assertEqual(result['total'],3)
        self.assertEqual([g['igdb_id'] for g in result['items']],[1,4,5])
        first=self.get('games',year=2016,genre_ids='12,31',page_size=2)
        second=self.get('games',year=2016,genre_ids='12,31',page_size=2,page=2)
        self.assertEqual(first['total'],3)
        self.assertEqual([g['igdb_id'] for g in first['items']+second['items']],[1,4,5])

    def test_legacy_union_and_empty(self):
        self.assertEqual(self.get('games',year=2016,genre_id=31)['total'],2)
        self.assertEqual(self.get('games',year=2016,genre_id=5,genre_ids='12,31')['total'],4)
        self.assertEqual(self.get('games',year=2016,genre_ids='')['total'],4)

    def test_other_filters_stay_intersections(self):
        self.assertEqual(self.get('games',year=2016,genre_ids='12,31',platform_ids='167')['total'],0)
        self.assertEqual(self.get('games',year=2026,scope='all',genre_ids='12,31')['total'],1)
        self.assertEqual(self.get('games',year=2026,scope='default',genre_ids='12,31')['total'],0)

    def test_search_boundaries(self):
        self.assertEqual(self.get('games',q='Game 6',year=2016,genre_ids='12,31',search_scope='global')['total'],1)
        self.assertEqual(self.get('games',q='Game 6',year=2016,genre_ids='12,31',search_scope='filtered')['total'],0)

    def test_bad_parameters_are_rejected(self):
        for value in ['12,','12,-1','12,1e3','１２','12,2147483648','12,1);DROP TABLE igdb_games;--',','.join(['12']*101),'9'*1101]:
            with self.subTest(value=value[:40]):
                self.assertEqual(self.client.get('/api/v1/games',params={'genre_ids':value}).status_code,422)

if __name__=='__main__':unittest.main()
