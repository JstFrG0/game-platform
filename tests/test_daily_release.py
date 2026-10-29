import json
import sqlite3

import pytest

from game_platform import daily_release as daily
from game_platform.classify_games import migrate, sync_types
from game_platform.ign_reviews import apply_links, import_records, migrate as migrate_ign, read_import
from game_platform.data_updates import read_bundle_content
from test_classification import seed, TypesAPI
from test_ign_reviews import review, source


def test_daily_bundle_keeps_manual_mapping_and_refreshes_review(tmp_path, monkeypatch):
    connection, _ = seed(tmp_path/'stage.sqlite3')
    migrate(connection)
    migrate_ign(connection)
    csv = source(tmp_path, [review(score=7)])
    records, _ = read_import(csv)
    import_records(connection, records, 'manual-import')
    apply_links(connection, [(records[0]['ign_game_url'], 1)], 'manual_csv')
    csv = source(tmp_path, [review(score=9)])
    capture = tmp_path/'capture.sqlite3'
    with sqlite3.connect(capture) as db:
        db.execute('CREATE TABLE reviews(review_url TEXT, raw_json TEXT)')
        db.execute('INSERT INTO reviews VALUES (?,?)', (records[0]['review_url'], json.dumps({'review': {'verdict': 'Updated'}})))
    run_id = connection.execute('SELECT run_id FROM collection_runs').fetchone()[0]
    monkeypatch.setattr(daily, 'collect', lambda *a, **kw: dict(run_id=run_id, year=2025,
        status='completed', count_check_passed=True, collected_unique_games=6))
    result, ids = daily.assemble(TypesAPI(), connection, [2025], tmp_path, [], csv, capture, [])
    _, entries = read_bundle_content(result['manifest'], (tmp_path/'bundle/catalog-data.zip').read_bytes())
    assert len(ids) == 6
    assert entries[0]['igdb_ids'] == [1]
    assert entries[0]['review']['score'] == 9
    assert entries[0]['review']['verdict'] == 'Updated'
    assert connection.execute('SELECT method FROM ign_links').fetchone()[0] == 'manual_csv'
    connection.close()


def test_daily_rejects_partial_igdb_scan_before_packaging(tmp_path, monkeypatch):
    connection, _ = seed(tmp_path/'stage.sqlite3')
    migrate(connection)
    monkeypatch.setattr(daily, 'collect', lambda *a, **kw: dict(year=2025, status='failed',
        count_check_passed=False, collected_unique_games=2))
    with pytest.raises(ValueError, match='count validation'):
        daily.assemble(TypesAPI(), connection, [2025], tmp_path, [], None, None, [])
    assert not (tmp_path/'bundle/catalog-manifest.json').exists()
    connection.close()


def test_removed_previously_published_game_requires_review():
    class Missing:
        def query(self, *args):
            return []
    with pytest.raises(ValueError, match='disappeared'):
        daily.refresh_ids(Missing(), None, [123])


def test_refresh_game_with_removed_release_date_clears_old_value(tmp_path):
    connection, _ = seed(tmp_path/'stage.sqlite3')
    class Delayed:
        def query(self, *args):
            return [{'id': 1, 'name': 'Postponed'}]
    daily.refresh_ids(Delayed(), connection, [1])
    assert connection.execute('SELECT first_release_date FROM igdb_games WHERE igdb_id=1').fetchone()[0] is None
    connection.close()


def test_daily_automatically_links_only_strict_exact_matches(tmp_path, monkeypatch):
    connection, _ = seed(tmp_path/'stage.sqlite3')
    migrate(connection)
    sync_types(TypesAPI(), connection)
    migrate_ign(connection)
    older = review(url='older-review', game='older')
    older['review_date'] = '2024-12-31'
    csv = source(tmp_path, [review(), review(url='uncertain-review', name='Uncertain title', game='uncertain'), older])
    old_records, _ = read_import(source(tmp_path, [older]))
    import_records(connection, old_records, 'existing-archive')
    apply_links(connection, [(old_records[0]['ign_game_url'], 1)], 'manual_csv')
    csv = source(tmp_path, [review(), review(url='uncertain-review', name='Uncertain title', game='uncertain'), older])
    capture = tmp_path/'capture.sqlite3'
    with sqlite3.connect(capture) as db:
        db.execute('CREATE TABLE reviews(review_url TEXT, raw_json TEXT)')
    run_id = connection.execute('SELECT run_id FROM collection_runs').fetchone()[0]
    monkeypatch.setattr(daily, 'collect', lambda *a, **kw: dict(run_id=run_id, year=2025,
        status='completed', count_check_passed=True, collected_unique_games=6))
    result, _ = daily.assemble(TypesAPI(), connection, [2025], tmp_path, [], csv, capture, [], ign_years=[2025])
    assert result['automatic_exact_links'] == 1
    assert result['pending_ign_games'] == 1
    assert result['manifest']['ign_record_count'] == 2
    assert connection.execute("SELECT igdb_id,method FROM ign_links WHERE ign_game_url='https://www.ign.com/games/main'").fetchone()[:] == (1, 'daily_exact')
    connection.close()


def test_subprocess_failure_stops_pipeline_and_keeps_log(tmp_path):
    import sys
    with pytest.raises(RuntimeError, match='exit 3'):
        daily.execute([sys.executable, '-c', 'print("failed step"); raise SystemExit(3)'], tmp_path, tmp_path/'step.log')
    assert 'failed step' in (tmp_path/'step.log').read_text()
