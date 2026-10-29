import json
import re
from datetime import datetime, timezone
import pytest
from game_platform.collect_igdb import collect, initialize, numeric, save_page


RELEASE = int(datetime(2025,6,1,tzinfo=timezone.utc).timestamp())


class FakeAPI:
    def __init__(self,records,fail_after=None):
        self.records=records;self.calls=0;self.fail_after=fail_after

    def query(self,endpoint,body):
        if endpoint=='games/count':return {'count':len(self.records)}
        if 'sort id desc' in body:return [{'id':max(r['id'] for r in self.records)}] if self.records else []
        self.calls+=1
        if self.fail_after is not None and self.calls>self.fail_after:raise RuntimeError('simulated network failure')
        last=int(re.search(r'id > (\d+)',body).group(1));limit=int(re.search(r'limit (\d+)',body).group(1))
        return [r for r in self.records if r['id']>last][:limit]


def records():
    return [{'id':1,'name':'Rated','first_release_date':RELEASE,'rating':87.25,'rating_count':12,
             'aggregated_rating':91.5,'aggregated_rating_count':4,'total_rating':89.375,'total_rating_count':16,
             'platforms':[{'id':6,'name':'PC'}],'genres':[{'id':12,'name':'Role-playing'}]},
            {'id':2,'name':'Unrated','first_release_date':RELEASE},
            {'id':8,'name':'Zero is a rating','first_release_date':RELEASE,'rating':0,'rating_count':1}]


def test_all_records_and_rating_preservation(tmp_path):
    c=initialize(tmp_path/'test.sqlite3')
    report=collect(FakeAPI(records()),c,2025,tmp_path,page_size=2)
    assert report['count_check_passed']
    assert report['collected_unique_games']==3 and report['rating_missing']==1
    row=c.execute('SELECT * FROM igdb_games WHERE igdb_id=1').fetchone()
    assert row['rating']==87.25 and row['rating_count']==12 and row['aggregated_rating']==91.5
    assert c.execute('SELECT rating FROM igdb_games WHERE igdb_id=2').fetchone()[0] is None
    assert c.execute('SELECT rating FROM igdb_games WHERE igdb_id=8').fetchone()[0]==0
    raw=[json.loads(line) for line in (tmp_path/'exports/igdb_2025.jsonl').read_text().splitlines()]
    assert raw[0]['total_rating_count']==16
    c.close()


def test_interruption_resumes_and_does_not_duplicate(tmp_path):
    c=initialize(tmp_path/'test.sqlite3')
    first=collect(FakeAPI(records(),fail_after=1),c,2025,tmp_path,page_size=2)
    assert first['status']=='failed' and first['collected_unique_games']==2
    second=collect(FakeAPI(records()),c,2025,tmp_path,page_size=2)
    assert second['run_id']==first['run_id'] and second['count_check_passed']
    assert c.execute('SELECT count(*) FROM igdb_games').fetchone()[0]==3
    c.close()


def test_fresh_scan_updates_scores(tmp_path):
    c=initialize(tmp_path/'test.sqlite3')
    first=collect(FakeAPI(records()),c,2025,tmp_path)
    changed=records();changed[0]['rating']=90.1
    second=collect(FakeAPI(changed),c,2025,tmp_path,fresh=True)
    assert second['run_id']!=first['run_id']
    assert c.execute('SELECT rating FROM igdb_games WHERE igdb_id=1').fetchone()[0]==90.1
    assert c.execute('SELECT count(*) FROM igdb_games').fetchone()[0]==3
    c.close()


def test_smoke_limit_is_not_reported_complete(tmp_path):
    c=initialize(tmp_path/'test.sqlite3')
    report=collect(FakeAPI(records()),c,2025,tmp_path,page_size=1,max_pages=1)
    assert report['status']=='paused' and not report['count_check_passed']
    c.close()


def test_empty_year_is_valid(tmp_path):
    c=initialize(tmp_path/'test.sqlite3')
    report=collect(FakeAPI([]),c,2025,tmp_path)
    assert report['count_check_passed'] and report['collected_unique_games']==0
    c.close()


def test_null_optional_metadata_exports(tmp_path):
    c=initialize(tmp_path/'test.sqlite3')
    entries=records();entries[0]['platforms']=None;entries[0]['genres']=[{'id':12,'name':None}]
    report=collect(FakeAPI(entries),c,2025,tmp_path)
    assert report['count_check_passed']
    assert json.loads(c.execute('SELECT platforms_json FROM igdb_games WHERE igdb_id=1').fetchone()[0])==[]
    c.close()


def test_count_mismatch_is_reported(tmp_path):
    class ChangedCount(FakeAPI):
        counts=0
        def query(self,endpoint,body):
            if endpoint=='games/count':
                self.counts+=1;return {'count':len(self.records)+(1 if self.counts>1 else 0)}
            return super().query(endpoint,body)
    c=initialize(tmp_path/'test.sqlite3')
    report=collect(ChangedCount(records()),c,2025,tmp_path)
    assert report['status']=='needs_reconciliation' and not report['count_check_passed']
    c.close()


def test_invalid_page_does_not_partially_commit(tmp_path):
    c=initialize(tmp_path/'test.sqlite3')
    report=collect(FakeAPI(records()),c,2025,tmp_path,max_pages=1,page_size=1)
    with pytest.raises(ValueError):
        save_page(c,report['run_id'],[records()[1],{'id':8,'name':'bad','first_release_date':RELEASE,'rating':101}],2025,8,1)
    assert c.execute('SELECT count(*) FROM igdb_games').fetchone()[0]==1
    c.close()


@pytest.mark.parametrize('value',[True,float('nan'),-1,101])
def test_invalid_rating_is_rejected(value):
    with pytest.raises(ValueError):numeric({'id':1,'rating':value},'rating')
