from datetime import datetime, timedelta, timezone

import httpx
import pytest

from game_platform.data_retention import prune_releases


def release(number, **changes):
    stamp = datetime(2026, 1, 1, tzinfo=timezone.utc)+timedelta(days=number)
    return dict(id=number, tag_name='data-'+stamp.strftime('%Y%m%dT%H%M%S%fZ'),
        published_at=stamp.isoformat(), draft=False, prerelease=False,
        assets=[{'name': 'catalog-data.zip'}, {'name': 'catalog-manifest.json'}], **changes)


@pytest.mark.parametrize('count,deleted', [(2, []), (31, []), (32, [1]), (34, [1, 2, 3])])
def test_keeps_newest_31_and_deletes_oldest_release_and_tag(count, deleted):
    rows = [release(i) for i in range(1, count+1)]
    requests = []
    def respond(request):
        requests.append(request)
        if request.method == 'GET':
            return httpx.Response(200, json=list(reversed(rows)))
        return httpx.Response(204)
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        result = prune_releases('owner/repo', 'SECRET', client=client, protected_tag=rows[-1]['tag_name'])
    assert result['status'] == 'completed'
    assert [r['id'] for r in result['deleted']] == deleted
    assert result['remaining_count'] == min(count, 31)
    assert [r.url.path for r in requests if r.method == 'DELETE'] == [
        path for i in deleted for path in (f'/repos/owner/repo/releases/{i}', '/repos/owner/repo/git/refs/tags/'+rows[i-1]['tag_name'])]


def test_reads_all_pages_and_ignores_other_releases():
    unrelated = [{**release(i), 'tag_name': f'v{i}'} for i in range(100, 200)]
    rows = unrelated+[release(i) for i in range(1, 33)]
    methods = []
    def respond(request):
        methods.append(request.method)
        if request.method == 'GET':
            offset = (int(request.url.params['page'])-1)*100
            return httpx.Response(200, json=rows[offset:offset+100])
        return httpx.Response(204)
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        result = prune_releases('owner/repo', 'SECRET', client=client)
    assert methods[:2] == ['GET', 'GET']
    assert result['ignored_release_count'] == 100
    assert [r['id'] for r in result['deleted']] == [1]


@pytest.mark.parametrize('change', [{'draft': True}, {'prerelease': True}, {'assets': []}, {'tag_name': 'data-unrelated'}])
def test_drafts_prereleases_incomplete_and_unrelated_tags_are_not_counted(change):
    rows = [{**release(i), **change} for i in range(1, 40)]
    def respond(request):
        assert request.method == 'GET'
        return httpx.Response(200, json=rows)
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        result = prune_releases('owner/repo', 'SECRET', client=client)
    assert result['data_release_count'] == 0
    assert not result['deleted']


def test_missing_protected_release_aborts_without_deletion():
    def respond(request):
        assert request.method == 'GET'
        return httpx.Response(200, json=[release(i) for i in range(1, 34)])
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        result = prune_releases('owner/repo', 'SECRET', client=client, protected_tag='data-missing')
    assert result['status'] == 'failed' and not result['deleted']


def test_dry_run_makes_no_deletions():
    def respond(request):
        assert request.method == 'GET'
        return httpx.Response(200, json=[release(i) for i in range(1, 33)])
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        result = prune_releases('owner/repo', 'SECRET', client=client, dry_run=True)
    assert result['status'] == 'dry_run' and len(result['planned_deletions']) == 1
    assert not result['deleted']


def test_permission_failure_is_reported_without_secret_and_stops():
    requests = []
    def respond(request):
        requests.append(request)
        if request.method == 'GET':
            return httpx.Response(200, json=[release(i) for i in range(1, 34)])
        return httpx.Response(403)
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        result = prune_releases('owner/repo', 'SECRET', client=client)
    assert result['status'] == 'failed' and result['http_status'] == 403
    assert len(requests) == 2
    assert 'SECRET' not in str(result)
