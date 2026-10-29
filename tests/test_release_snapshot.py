import json
import sqlite3

import pytest

from game_platform.classify_games import migrate, sync_types
from game_platform.ign_reviews import apply_links, import_records, migrate as migrate_ign, read_import
from game_platform.release_snapshot import prepare, package
from game_platform.data_updates import PACKAGE, read_bundle_content
from test_classification import seed, TypesAPI
from test_ign_reviews import review, source


def test_snapshot_carries_confirmed_links_and_refreshes_source(tmp_path):
    catalog = tmp_path/'catalog.sqlite3'
    stage = tmp_path/'stage.sqlite3'
    c, _ = seed(catalog)
    migrate(c)
    sync_types(TypesAPI(), c)
    migrate_ign(c)
    initial, _ = read_import(source(tmp_path, [review(score=7)]))
    import_records(c, initial, 'initial.csv')
    apply_links(c, [(initial[0]['ign_game_url'], 1)], 'manual_csv')
    c.close()
    s, _ = seed(stage)
    migrate(s)
    sync_types(TypesAPI(), s)
    s.close()
    csv = source(tmp_path, [review(score=9)])
    capture = tmp_path/'capture.sqlite3'
    with sqlite3.connect(capture) as connection:
        connection.execute('CREATE TABLE reviews(review_url TEXT,raw_json TEXT)')
        connection.execute('INSERT INTO reviews VALUES(?,?)',
            (initial[0]['review_url'], json.dumps({'review': {'verdict': 'New verdict'}})))
    report = prepare(stage, catalog, csv, capture, 2025, tmp_path/'bundle')
    assert report['carried_reviews'] == 1 and report['refreshed_relevant_reviews'] == 1
    assert not report['proposed_exact']
    supplemental = tmp_path/'corrections.jsonl'
    supplemental.write_text(json.dumps({'id': 99, 'name': 'Delayed'})+'\n')
    result = package(stage, 2025, tmp_path/'bundle', supplemental)
    records, reviews = read_bundle_content(result['manifest'], (tmp_path/'bundle'/PACKAGE).read_bytes())
    assert result['igdb_year_records'] == 6 and result['igdb_scope_correction_records'] == 1
    assert result['manifest']['scope']['year'] == 2025
    assert result['manifest']['scope']['correction_record_count'] == 1
    assert records[-1]['id'] == 99 and records[-1]['first_release_date'] is None
    assert reviews[0]['igdb_ids'] == [1]
    assert reviews[0]['review']['score'] == 9
    assert reviews[0]['review']['verdict'] == 'New verdict'


def test_snapshot_refuses_unverified_collection(tmp_path):
    stage = tmp_path/'stage.sqlite3'
    s, _ = seed(stage)
    migrate(s)
    with s:
        s.execute("UPDATE collection_runs SET status='paused'")
    s.close()
    with pytest.raises(ValueError, match='拒绝打包'):
        package(stage, 2025, tmp_path/'bundle')
    assert not (tmp_path/'bundle'/PACKAGE).exists()
