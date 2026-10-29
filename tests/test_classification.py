import json
import sqlite3

import pytest

from game_platform.classify_games import (
    backup_database, export_classification, migrate, select_games, sync_types, type_key,
)
from game_platform.collect_igdb import collect, initialize
from test_collection import FakeAPI, RELEASE


def seed(path):
    connection = initialize(path)
    records = [
        {'id': 1, 'name': 'Main', 'first_release_date': RELEASE, 'game_type': 100,
         'rating': 0, 'rating_count': 1, 'platforms': [{'id': 6, 'name': 'Windows'}],
         'genres': [{'id': 12, 'name': 'RPG'}], 'game_modes': [{'id': 1, 'name': 'Single player'}]},
        {'id': 2, 'name': 'Unrated remake', 'first_release_date': RELEASE, 'category': 8},
        {'id': 3, 'name': 'DLC', 'first_release_date': RELEASE, 'game_type': 101,
         'parent_game': 900, 'rating': 90, 'rating_count': 0},
        {'id': 4, 'name': 'Unknown modern', 'first_release_date': RELEASE,
         'game_type': 0, 'category': 0},
        {'id': 5, 'name': 'Missing', 'first_release_date': RELEASE},
        {'id': 6, 'name': 'Standalone', 'first_release_date': RELEASE, 'category': 4,
         'version_parent': {'id': 901}, 'game_status': 7},
    ]
    collect(FakeAPI(records), connection, 2025, path.parent)
    return connection, records


class TypesAPI:
    def query(self, endpoint, body):
        assert endpoint == 'game_types'
        return [{'id': 100, 'type': 'Main Game'}, {'id': 101, 'type': 'DLC Addon'}] if 'id > -1;' in body else []


def test_migration_preserves_sources_ratings_membership_and_is_repeatable(tmp_path):
    path = tmp_path/'igdb.sqlite3'
    c, _ = seed(path)
    before = [tuple(r) for r in c.execute('SELECT igdb_id,rating,rating_count,raw_json,fetched_at FROM igdb_games')]
    run = [tuple(r) for r in c.execute('SELECT * FROM collection_runs')]
    backup = backup_database(path)
    with sqlite3.connect(backup) as b:
        assert b.execute('SELECT count(*) FROM igdb_games').fetchone()[0] == 6
    migrate(c); migrate(c)
    assert before == [tuple(r) for r in c.execute('SELECT igdb_id,rating,rating_count,raw_json,fetched_at FROM igdb_games')]
    assert run == [tuple(r) for r in c.execute('SELECT * FROM collection_runs')]
    assert c.execute('SELECT count(*) FROM run_members').fetchone()[0] == 6
    assert c.execute('SELECT count(*) FROM schema_versions WHERE version=2').fetchone()[0] == 1
    assert c.execute('SELECT count(*) FROM game_tags').fetchone()[0] == 3
    c.close()


def test_dictionary_opaque_ids_default_and_unknown_visibility(tmp_path):
    c, _ = seed(tmp_path/'igdb.sqlite3'); migrate(c)
    assert [r['igdb_id'] for r in select_games(c)] == [2, 6]
    sync_types(TypesAPI(), c)
    assert [r['igdb_id'] for r in select_games(c)] == [1, 2, 6]
    assert [r['igdb_id'] for r in select_games(c, scope='unknown')] == [4, 5]
    assert len(select_games(c, scope='all')) == 6
    row = c.execute('SELECT * FROM igdb_games WHERE igdb_id=6').fetchone()
    assert row['version_parent_id'] == 901 and row['game_status_id'] == 7
    assert c.execute('SELECT parent_game_id FROM igdb_games WHERE igdb_id=3').fetchone()[0] == 900
    c.close()


def test_exact_tags_optional_rating_and_missing_versus_zero(tmp_path):
    c, _ = seed(tmp_path/'igdb.sqlite3'); migrate(c); sync_types(TypesAPI(), c)
    assert [r['igdb_id'] for r in select_games(c, platform_id=6, genre_id=12, mode_id=1)] == [1]
    assert select_games(c, platform_id=60) == []
    assert [r['igdb_id'] for r in select_games(c, min_rating=0)] == [1]
    assert [r['igdb_id'] for r in select_games(c, scope='all', min_rating_count=1)] == [1]
    assert [r['igdb_id'] for r in select_games(c, scope='all', min_rating=80)] == [3]
    assert select_games(c, year=2024, scope='all') == []
    c.close()


def test_migrated_collector_keeps_classification_and_updates_tags(tmp_path):
    c, records = seed(tmp_path/'igdb.sqlite3'); migrate(c); sync_types(TypesAPI(), c)
    records[0]['platforms'] = [{'id': 167, 'name': 'PS5'}]
    records[0]['game_type'] = 101
    assert collect(FakeAPI(records), c, 2025, tmp_path, fresh=True)['count_check_passed']
    assert c.execute('SELECT game_type_key FROM igdb_games WHERE igdb_id=1').fetchone()[0] == 'dlc_addon'
    assert not select_games(c, scope='all', platform_id=6)
    assert len(select_games(c, scope='all', platform_id=167)) == 1
    c.close()


def test_corrupt_raw_json_rolls_back_schema_and_version(tmp_path):
    c, _ = seed(tmp_path/'igdb.sqlite3')
    with c: c.execute("UPDATE igdb_games SET raw_json='invalid' WHERE igdb_id=5")
    with pytest.raises(json.JSONDecodeError): migrate(c)
    assert 'game_type_key' not in {r['name'] for r in c.execute('PRAGMA table_info(igdb_games)')}
    assert not c.execute('SELECT 1 FROM schema_versions WHERE version=2').fetchone()
    c.close()


def test_failed_dictionary_retains_existing_classification(tmp_path):
    c, _ = seed(tmp_path/'igdb.sqlite3'); migrate(c); sync_types(TypesAPI(), c)
    class BrokenAPI:
        def query(self, *_): return [{'id': 100, 'type': 'DLC'}, {'id': 99, 'type': 'Main Game'}]
    with pytest.raises(ValueError): sync_types(BrokenAPI(), c)
    assert c.execute('SELECT game_type_key FROM igdb_games WHERE igdb_id=1').fetchone()[0] == 'main_game'
    assert c.execute('SELECT count(*) FROM igdb_game_types').fetchone()[0] == 2
    c.close()


def test_report_counts_reconcile_without_changing_collection_report(tmp_path):
    c, _ = seed(tmp_path/'igdb.sqlite3'); migrate(c); sync_types(TypesAPI(), c)
    original = (tmp_path/'reports/igdb_2025_report.json').read_bytes()
    r = export_classification(c, tmp_path, 2025)
    assert r['total_records'] == r['default_visible_count'] + r['optional_count'] + r['unknown_count'] == 6
    assert r['rating_present'] == 2 and r['zero_rating_count_with_rating'] == 1
    assert r['parent_references_outside_local_catalog'] == 1
    assert (tmp_path/'reports/igdb_2025_report.json').read_bytes() == original
    c.close()


def test_pack_addon_existing_dictionary_reclassified_offline(tmp_path):
    c, _ = seed(tmp_path/'igdb.sqlite3'); migrate(c)
    row = c.execute('SELECT raw_json FROM igdb_games WHERE igdb_id=4').fetchone()
    record = json.loads(row['raw_json']); record['game_type'] = 13
    with c:
        c.execute('UPDATE igdb_games SET raw_json=? WHERE igdb_id=4', (json.dumps(record),))
        c.execute("INSERT INTO igdb_game_types VALUES(13,'Pack / Addon','unknown','original-fetch-time')")
    migrate(c)
    assert type_key('Pack / Addon') == 'pack'
    assert type_key('Pack / Add-on') == 'pack'
    assert type_key('Unrecognized future type') == 'unknown'
    assert c.execute('SELECT game_type_key FROM igdb_games WHERE igdb_id=4').fetchone()[0] == 'pack'
    assert c.execute('SELECT fetched_at FROM igdb_game_types WHERE type_id=13').fetchone()[0] == 'original-fetch-time'
    assert 4 not in [r['igdb_id'] for r in select_games(c)]
    assert 4 in [r['igdb_id'] for r in select_games(c, scope='all')]
    assert 4 not in [r['igdb_id'] for r in select_games(c, scope='unknown')]
    migrate(c)
    assert c.execute('SELECT count(*) FROM igdb_games').fetchone()[0] == 6
    c.close()
