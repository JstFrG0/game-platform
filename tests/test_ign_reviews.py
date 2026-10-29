import csv
import json
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from game_platform.api import create_app
from game_platform.classify_games import migrate as classify, sync_types
from game_platform.ign_reviews import (
    apply_links, candidates, confirm_actions, date_value, ign_url, import_records,
    migrate, read_import, report,
)
from test_classification import seed, TypesAPI


def review(url='main-review', name='Main', game='main', score='8', platforms='PC', date='2025-06-01'):
    return {'name': name, 'score': score, 'review_url': 'https://www.ign.com/articles/'+url,
            'game_url': 'https://www.ign.com/games/'+game, 'platforms': platforms,
            'us_release_date': date, 'review_date': '2025-06-03'}


def source(tmp_path, rows):
    path = tmp_path/'reviews.csv'
    with path.open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    return path


@pytest.fixture
def catalog(tmp_path):
    path = tmp_path/'igdb.sqlite3'
    c, _ = seed(path); classify(c); sync_types(TypesAPI(), c); migrate(c)
    yield c, path
    c.close()


def test_import_preserves_igdb_and_multiple_reviews_idempotently(catalog, tmp_path):
    c, _ = catalog
    before = [tuple(r) for r in c.execute('SELECT * FROM igdb_games')]
    rows = [review('main-campaign-review', score='7'), review('main-multiplayer-review', score='6')]
    records, info = read_import(source(tmp_path, rows))
    import_records(c, records, 'reviews.csv')
    import_records(c, records, 'reviews.csv')
    assert c.execute('SELECT count(*) FROM ign_reviews').fetchone()[0] == 2
    assert [tuple(r) for r in c.execute('SELECT * FROM igdb_games')] == before
    assert {r['scope'] for r in c.execute('SELECT scope FROM ign_reviews')} == {'单人战役', '多人'}
    assert info['video_reviews'] == 2
    assert c.execute('SELECT count(*) FROM ign_links').fetchone()[0] == 0


def test_exact_candidates_require_platform_date_and_unique_identity(catalog, tmp_path):
    c, _ = catalog
    records, _ = read_import(source(tmp_path, [review()]))
    import_records(c, records, 'reviews.csv')
    match = candidates(c)[0]
    assert match['eligible_igdb_id'] == 1 and match['linked_igdb_id'] is None
    with c: c.execute("UPDATE ign_reviews SET platforms_json='[\"Nintendo Switch\"]'")
    assert candidates(c)[0]['eligible_igdb_id'] is None
    with c: c.execute("UPDATE ign_reviews SET platforms_json='[\"PC\"]',us_release_date='2025-07-01'")
    assert candidates(c)[0]['eligible_igdb_id'] is None
    with c:
        c.execute("UPDATE ign_reviews SET us_release_date='2025-06-01'")
        c.execute("UPDATE igdb_games SET name='Main' WHERE igdb_id=2")
    assert candidates(c)[0]['exact_candidate_count'] == 2
    assert candidates(c)[0]['eligible_igdb_id'] is None


def test_fuzzy_candidates_never_eligible_and_missing_local_game_is_not_invented(catalog, tmp_path):
    c, _ = catalog
    records, _ = read_import(source(tmp_path, [review(name='Unrated remak', game='remake'), review('old-game-review', name='An entirely absent title', game='absent')]))
    import_records(c, records, 'reviews.csv')
    by_name = {g['ign_name']: g for g in candidates(c)}
    assert by_name['Unrated remak']['candidates'][0]['match_method'] == 'fuzzy'
    assert by_name['Unrated remak']['eligible_igdb_id'] is None
    assert by_name['An entirely absent title']['candidates'] == []


def test_link_api_update_and_unlink_with_audit(catalog, tmp_path):
    c, path = catalog
    records, _ = read_import(source(tmp_path, [review('main-campaign-review', score='7'), review('main-multiplayer-review', score='6')]))
    import_records(c, records, 'reviews.csv')
    url = records[0]['ign_game_url']
    assert apply_links(c, [(url, 1)], 'manual_csv') == 1
    assert apply_links(c, [(url, 1)], 'manual_csv') == 0
    with TestClient(create_app(path)) as client:
        details = client.get('/api/v1/games/1').json()
        assert sorted(r['score'] for r in details['ign_reviews']) == [6, 7]
        assert details['rating'] == 0 and details['rating_count'] == 1
        assert client.get('/api/v1/games/2').json()['ign_reviews'] == []
    with pytest.raises(ValueError): apply_links(c, [(url, 2)], 'manual_csv')
    assert apply_links(c, [(url, 2)], 'manual_csv', replace=True) == 1
    assert apply_links(c, [(url, None)], 'manual_csv') == 1
    assert c.execute('SELECT count(*) FROM ign_links').fetchone()[0] == 0
    assert c.execute('SELECT count(*) FROM ign_link_events').fetchone()[0] == 3


def test_invalid_confirmation_does_not_partially_write(catalog, tmp_path):
    c, _ = catalog
    records, _ = read_import(source(tmp_path, [review(), review('another-review', game='another')]))
    import_records(c, records, 'reviews.csv')
    with pytest.raises(ValueError): apply_links(c, [(records[0]['ign_game_url'], 1), (records[1]['ign_game_url'], 999)], 'manual_csv')
    assert c.execute('SELECT count(*) FROM ign_links').fetchone()[0] == 0


def test_tabletop_exclusion_score_zero_and_date_conversion(tmp_path):
    records, info = read_import(source(tmp_path, [review(score='0'), review('board-review', game='board', platforms='Tabletop')]))
    assert len(records) == 1 and records[0]['score'] == 0
    assert info['excluded_tabletop'] == 1
    assert date_value('45666') == '2025-01-09'
    assert date_value('2025-06-01') == '2025-06-01'


@pytest.mark.parametrize('change', [
    {'score': '11'}, {'score': 'nan'}, {'score': '-1'},
    {'review_url': 'https://evil.example/articles/test'}, {'review_url': 'javascript:alert(1)'},
    {'us_release_date': 'invalid'},
])
def test_bad_import_rejected_before_writes(tmp_path, change):
    row = review(); row.update(change)
    with pytest.raises(ValueError): read_import(source(tmp_path, [row]))


def test_canonical_url_duplicate_conflicts_and_confirmation_file(catalog, tmp_path):
    assert ign_url('http://ign.com/articles/test-review/?tracking=1', 'articles') == 'https://www.ign.com/articles/test-review'
    with pytest.raises(ValueError): read_import(source(tmp_path, [review(score='8'), review(score='7')]))
    c, _ = catalog
    records, _ = read_import(source(tmp_path, [review()]))
    import_records(c, records, 'reviews.csv')
    data = report(c, tmp_path)
    assert data['review_count'] == 1 and data['linked_reviews'] == 0 and data['eligible_unlinked_games'] == 1
    template = tmp_path/'exports/ign_link_confirmations_template.csv'
    assert confirm_actions(template) == []
    rows = list(csv.DictReader(template.open(encoding='utf-8-sig')))
    rows[0]['decision'] = '关联'
    with template.open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys()); w.writeheader(); w.writerows(rows)
    assert confirm_actions(template) == [(records[0]['ign_game_url'], 1)]


def test_reimport_updates_score_but_keeps_confirmed_link(catalog, tmp_path):
    c, _ = catalog
    records, _ = read_import(source(tmp_path, [review()]))
    import_records(c, records, 'reviews.csv'); apply_links(c, [(records[0]['ign_game_url'], 1)], 'manual_csv')
    records[0]['score'] = 9
    import_records(c, records, 'updated.csv'); migrate(c)
    assert c.execute('SELECT score FROM ign_reviews').fetchone()[0] == 9
    assert c.execute('SELECT igdb_id FROM ign_links').fetchone()[0] == 1
    assert c.execute('SELECT count(*) FROM schema_versions WHERE version=3').fetchone()[0] == 1


def test_xlsx_inline_strings_shared_strings_and_numeric_dates(tmp_path):
    path = tmp_path/'reviews.xlsx'
    ns = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
    headers = ['游戏名称', 'IGN评分', '评测链接', '游戏链接', '平台（页面所列）', '美区最早发售日期（非预计）']
    header_xml = ''.join(f'<c r="{chr(65+i)}1" t="inlineStr"><is><t>{name}</t></is></c>' for i, name in enumerate(headers))
    values = '<c r="A2" t="s"><v>0</v></c><c r="B2"><v>7</v></c><c r="C2" t="inlineStr"><is><t>https://www.ign.com/articles/main-review</t></is></c><c r="D2" t="inlineStr"><is><t>https://www.ign.com/games/main</t></is></c><c r="E2" t="inlineStr"><is><t>PC</t></is></c><c r="F2"><v>45666</v></c>'
    with zipfile.ZipFile(path, 'w') as z:
        z.writestr('xl/workbook.xml', f'<workbook xmlns="{ns}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="IGN评测" r:id="rId1"/></sheets></workbook>')
        z.writestr('xl/_rels/workbook.xml.rels', '<Relationships><Relationship Id="rId1" Target="/xl/worksheets/sheet1.xml"/></Relationships>')
        z.writestr('xl/sharedStrings.xml', f'<sst xmlns="{ns}"><si><t>Main</t></si></sst>')
        z.writestr('xl/worksheets/sheet1.xml', f'<worksheet xmlns="{ns}"><sheetData><row>{header_xml}</row><row>{values}</row></sheetData></worksheet>')
    records, info = read_import(path)
    assert info['video_reviews'] == 1
    assert records[0]['name'] == 'Main' and records[0]['score'] == 7
    assert records[0]['us_release_date'] == '2025-01-09'
