"""Collect all IGDB records whose global first release falls in a given year.

Uses ascending game IDs, a frozen maximum ID and transaction checkpoints.
No rating filter is applied: unrated games are included and stored as NULL.
"""
from __future__ import annotations
import argparse
import csv
import json
import math
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from .igdb_client import APIError, IGDBClient

ROOT = Path(__file__).resolve().parents[2]
FIELDS = '*,genres.name,platforms.name,cover.url,alternative_names.name,game_modes.name,involved_companies.company.name,release_dates.*,release_dates.platform.name'
RATINGS = ('rating', 'rating_count', 'aggregated_rating', 'aggregated_rating_count', 'total_rating', 'total_rating_count')


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def boundaries(year):
    return (int(datetime(year,1,1,tzinfo=timezone.utc).timestamp()),
            int(datetime(year+1,1,1,tzinfo=timezone.utc).timestamp()))


def year_filter(year, max_id=None):
    start, end = boundaries(year)
    return f'first_release_date >= {start} & first_release_date < {end}' + (f' & id <= {max_id}' if max_id is not None else '')


def load_env(path):
    if not path.exists():
        return
    for line in path.read_text(encoding='utf-8-sig').splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if '=' not in line:
            raise ValueError('.env 格式错误，请使用配置脚本重新生成。')
        key,value = line.split('=',1)
        if key.strip() in {'IGDB_CLIENT_ID','IGDB_CLIENT_SECRET'}:
            os.environ.setdefault(key.strip(),value.strip().strip('"').strip("'"))


def initialize(path):
    path.parent.mkdir(parents=True,exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute('PRAGMA foreign_keys=ON')
    connection.execute('PRAGMA journal_mode=WAL')
    connection.executescript('''
      CREATE TABLE IF NOT EXISTS schema_versions(version INTEGER PRIMARY KEY, applied_at TEXT);
      CREATE TABLE IF NOT EXISTS igdb_games(
        igdb_id INTEGER PRIMARY KEY, name TEXT NOT NULL, first_release_date INTEGER,
        rating REAL, rating_count INTEGER, aggregated_rating REAL, aggregated_rating_count INTEGER,
        total_rating REAL, total_rating_count INTEGER, platforms_json TEXT NOT NULL,
        genres_json TEXT NOT NULL, summary TEXT, raw_json TEXT NOT NULL, fetched_at TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS collection_runs(
        run_id TEXT PRIMARY KEY, year INTEGER NOT NULL, status TEXT NOT NULL,
        max_id INTEGER NOT NULL, last_id INTEGER NOT NULL DEFAULT 0,
        expected_count INTEGER NOT NULL, pages INTEGER NOT NULL DEFAULT 0,
        started_at TEXT NOT NULL, finished_at TEXT, error TEXT NOT NULL DEFAULT '');
      CREATE TABLE IF NOT EXISTS run_members(
        run_id TEXT NOT NULL REFERENCES collection_runs(run_id),
        igdb_id INTEGER NOT NULL REFERENCES igdb_games(igdb_id), PRIMARY KEY(run_id,igdb_id));
      CREATE INDEX IF NOT EXISTS ix_rating ON igdb_games(rating,rating_count);
      CREATE INDEX IF NOT EXISTS ix_release ON igdb_games(first_release_date);
    ''')
    connection.execute('INSERT OR IGNORE INTO schema_versions VALUES(1,?)',(utc_now(),))
    connection.commit()
    return connection


def numeric(record,key):
    value = record.get(key)
    if value is None:
        return None
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):
        raise ValueError(f'IGDB {record.get("id")} 的 {key} 不是合法数值。')
    if key.endswith('_count'):
        if value < 0 or int(value)!=value:
            raise ValueError(f'IGDB {record.get("id")} 的评分人数不合法。')
        return int(value)
    if not 0 <= value <= 100:
        raise ValueError(f'IGDB {record.get("id")} 的评分超出 0–100 范围。')
    return float(value)


def upsert_record(connection, record):
    """Merge source facts without touching IGN links or committing the caller's transaction."""
    names = lambda key: json.dumps([
        str(x.get('name') or x.get('id', '')) if isinstance(x, dict) else str(x)
        for x in (record.get(key) or [])], ensure_ascii=False)
    columns = ('igdb_id', 'name', 'first_release_date', *RATINGS,
               'platforms_json', 'genres_json', 'summary', 'raw_json', 'fetched_at')
    updates = ','.join(f'{key}=excluded.{key}' for key in columns if key != 'igdb_id')
    connection.execute(
        f"INSERT INTO igdb_games ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)}) "
        f'ON CONFLICT(igdb_id) DO UPDATE SET {updates}',
        (record['id'], record['name'], record['first_release_date'],
         *(numeric(record, key) for key in RATINGS), names('platforms'), names('genres'),
         record.get('summary'), json.dumps(record, ensure_ascii=False), utc_now()))
    if connection.execute('SELECT 1 FROM schema_versions WHERE version=2').fetchone():
        from .classify_games import backfill_record
        backfill_record(connection, record['id'], record)


def save_page(connection,run_id,records,year,max_id,last_id):
    start,end=boundaries(year)
    ids=[]
    for record in records:
        game_id=record.get('id')
        released=record.get('first_release_date')
        if isinstance(game_id,bool) or not isinstance(game_id,int) or game_id <= last_id or game_id > max_id:
            raise ValueError('IGDB 分页 ID 顺序异常，当前页不入库。')
        if ids and game_id <= ids[-1]:
            raise ValueError('IGDB 分页未按 ID 严格递增，当前页不入库。')
        if not isinstance(released,(int,float)) or not start <= released < end:
            raise ValueError('IGDB 返回了目标年份以外的条目，当前页不入库。')
        if not isinstance(record.get('name'),str) or not record['name']:
            raise ValueError('IGDB 返回条目缺少名称。')
        for key in RATINGS:numeric(record,key)
        ids.append(game_id)
    with connection:
        for record in records:
            upsert_record(connection, record)
            connection.execute('INSERT OR IGNORE INTO run_members VALUES(?,?)',(run_id,record['id']))
        connection.execute("UPDATE collection_runs SET last_id=?,pages=pages+1,status='running',error='' WHERE run_id=?",(ids[-1],run_id))
    return ids[-1]


def count_value(payload):
    if not isinstance(payload,dict) or isinstance(payload.get('count'),bool) or not isinstance(payload.get('count'),int) or payload['count']<0:
        raise ValueError('IGDB count 响应结构异常。')
    return payload['count']


def export_run(connection,run_id,output,count_after=None,query=None):
    run=dict(connection.execute('SELECT * FROM collection_runs WHERE run_id=?',(run_id,)).fetchone())
    rows=connection.execute('''SELECT g.* FROM igdb_games g JOIN run_members m USING(igdb_id)
      WHERE m.run_id=? ORDER BY g.igdb_id''',(run_id,)).fetchall()
    year=run['year'];exports=output/'exports';reports=output/'reports'
    exports.mkdir(parents=True,exist_ok=True);reports.mkdir(parents=True,exist_ok=True)
    csv_path=exports/f'igdb_{year}.csv';raw_path=exports/f'igdb_{year}.jsonl'
    headers=['igdb_id','name','first_release_date','first_release_date_utc',*RATINGS,'platforms','genres','summary','fetched_at']
    with csv_path.open('w',encoding='utf-8-sig',newline='') as file:
        writer=csv.writer(file);writer.writerow(headers)
        for row in rows:
            values=[row['igdb_id'],row['name'],row['first_release_date'],datetime.fromtimestamp(row['first_release_date'],timezone.utc).date().isoformat(),
                    *(row[k] for k in RATINGS),'; '.join(json.loads(row['platforms_json'])),'; '.join(json.loads(row['genres_json'])),row['summary'],row['fetched_at']]
            writer.writerow(["'"+v if isinstance(v,str) and v.lstrip().startswith(('=','+','-','@')) else v for v in values])
    with raw_path.open('w',encoding='utf-8') as file:
        for row in rows:file.write(row['raw_json']+'\n')
    report={**run,'year_basis':'IGDB first_release_date, UTC global first release; all game types, no rating filter',
            'collected_unique_games':len(rows),'count_after':count_after,
            'count_check_passed':run['status']=='completed' and len(rows)==run['expected_count']==count_after,
            'worldwide_all_games_claim':False,'rating_present':sum(r['rating'] is not None for r in rows),
            'rating_missing':sum(r['rating'] is None for r in rows),
            'rating_count_present':sum(r['rating_count'] is not None for r in rows),
            'aggregated_rating_present':sum(r['aggregated_rating'] is not None for r in rows),
            'last_query':query,'exports':{'csv':str(csv_path),'raw_jsonl':str(raw_path)}}
    path=reports/f'igdb_{year}_report.json';path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f"Collected {len(rows)} unique games; rating present: {report['rating_present']}; unrated: {report['rating_missing']}")
    print('Report:',path)
    return report


def collect(api,connection,year,output,page_size=200,fresh=False,max_pages=None):
    run=None if fresh else connection.execute("SELECT * FROM collection_runs WHERE year=? AND status IN ('running','paused','failed') ORDER BY started_at DESC LIMIT 1",(year,)).fetchone()
    if run:
        run=dict(run);run_id=run['run_id'];max_id=run['max_id'];last_id=run['last_id']
        print(f'Resuming after IGDB ID {last_id}.')
    else:
        top=api.query('games',f'fields id; where {year_filter(year)}; sort id desc; limit 1;')
        if not isinstance(top,list):raise ValueError('IGDB games 响应结构异常。')
        max_id=top[0]['id'] if top else 0
        if isinstance(max_id,bool) or not isinstance(max_id,int) or max_id<0:
            raise ValueError('IGDB 最大 ID 响应不合法。')
        expected=count_value(api.query('games/count',f'where {year_filter(year,max_id)};'))
        run_id=str(uuid.uuid4());last_id=0
        with connection:
            if fresh:connection.execute("UPDATE collection_runs SET status='superseded' WHERE year=? AND status IN ('running','paused','failed')",(year,))
            connection.execute("INSERT INTO collection_runs(run_id,year,status,max_id,expected_count,started_at) VALUES(?,?,'running',?,?,?)",(run_id,year,max_id,expected,utc_now()))
    count_after=None;query=None;pages=0
    try:
        while True:
            if max_pages is not None and pages>=max_pages:
                with connection:connection.execute("UPDATE collection_runs SET status='paused',error='本次达到测试页数上限，重跑会恢复' WHERE run_id=?",(run_id,))
                break
            query=f'fields {FIELDS}; where {year_filter(year,max_id)} & id > {last_id}; sort id asc; limit {page_size};'
            records=api.query('games',query)
            if not isinstance(records,list):raise ValueError('IGDB games 响应不是列表。')
            if not records:
                count_after=count_value(api.query('games/count',f'where {year_filter(year,max_id)};'))
                saved=connection.execute('SELECT count(*) FROM run_members WHERE run_id=?',(run_id,)).fetchone()[0]
                expected=connection.execute('SELECT expected_count FROM collection_runs WHERE run_id=?',(run_id,)).fetchone()[0]
                state='completed' if saved==expected==count_after else 'needs_reconciliation'
                with connection:connection.execute('UPDATE collection_runs SET status=?,finished_at=?,error=? WHERE run_id=?',
                    (state,utc_now(),'' if state=='completed' else '采集数量与接口计数不一致，需重新扫描核验。',run_id))
                break
            last_id=save_page(connection,run_id,records,year,max_id,last_id)
            pages+=1
            saved=connection.execute('SELECT count(*) FROM run_members WHERE run_id=?',(run_id,)).fetchone()[0]
            print(f'Page {pages}: {saved} games saved, last ID {last_id}',flush=True)
    except KeyboardInterrupt:
        with connection:connection.execute("UPDATE collection_runs SET status='paused',error='用户中断，重跑会恢复' WHERE run_id=?",(run_id,))
        print('Paused; checkpoint saved.')
    except Exception as exc:
        with connection:connection.execute("UPDATE collection_runs SET status='failed',error=? WHERE run_id=?",(str(exc)[:1500],run_id))
        print('ERROR:',str(exc))
    return export_run(connection,run_id,output,count_after,query)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--year',type=int,default=2025)
    parser.add_argument('--page-size',type=int,default=200)
    parser.add_argument('--fresh',action='store_true',help='Start a new scan, keep existing source records')
    parser.add_argument('--max-pages',type=int,help='Optional bounded smoke test; omit for full collection')
    parser.add_argument('--data-dir',type=Path,default=ROOT/'data')
    parser.add_argument('--env-file',type=Path,default=ROOT/'.env')
    args=parser.parse_args()
    if not 1950<=args.year<=2100 or not 1<=args.page_size<=500 or (args.max_pages is not None and args.max_pages<1):
        parser.error('年份1950–2100；每页1–500；测试页数必须大于0')
    try:
        load_env(args.env_file)
        client_id=os.environ.get('IGDB_CLIENT_ID','').strip();secret=os.environ.get('IGDB_CLIENT_SECRET','').strip()
        if not client_id or not secret:
            print('请先运行 scripts/configure_igdb.py，在本机配置 IGDB 凭据。');return 1
        with IGDBClient(client_id,secret) as api:
            connection=initialize(args.data_dir/'igdb.sqlite3')
            try:report=collect(api,connection,args.year,args.data_dir,args.page_size,args.fresh,args.max_pages)
            finally:connection.close()
        return 0 if report['count_check_passed'] else 2
    except (APIError,ValueError,OSError,sqlite3.Error) as exc:
        print('ERROR:',str(exc));return 1


if __name__=='__main__':raise SystemExit(main())
