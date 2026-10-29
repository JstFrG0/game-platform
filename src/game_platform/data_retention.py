"""Keep the newest complete catalog releases; never prune unrelated releases."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import re

import httpx

from .collect_igdb import ROOT
from .data_updates import MANIFEST, PACKAGE, atomic_write, check_repository
from .update_service import read_token


def data_release(release):
    return (not release.get('draft') and not release.get('prerelease')
        and re.fullmatch(r'data-\d{8}T\d{12}Z', release.get('tag_name', '')) is not None
        and {a['name'] for a in release.get('assets', [])} == {MANIFEST, PACKAGE})


def prune_releases(repository, token, *, keep=31, protected_tag=None, client=None, dry_run=False, progress=None):
    check_repository(repository)
    if type(keep) is not int or keep < 1:
        raise ValueError('Release retention count must be a positive integer')
    if not token:
        raise ValueError('Release retention requires a publisher token')
    if client is None:
        with httpx.Client(timeout=60) as http:
            return prune_releases(repository, token, keep=keep, protected_tag=protected_tag,
                client=http, dry_run=dry_run, progress=progress)
    headers = {'Authorization': 'Bearer '+token, 'Accept': 'application/vnd.github+json'}
    base = f'https://api.github.com/repos/{repository}'
    report = {'status': 'checking', 'keep': keep, 'deleted': [], 'dry_run': dry_run}
    def update():
        if progress:
            progress(dict(report))
    try:
        releases, seen = [], set()
        # Finish reading every page before deleting anything, or pagination can shift.
        for page in range(1, 1001):
            response = client.get(base+'/releases', headers=headers, params={'per_page': 100, 'page': page})
            response.raise_for_status()
            rows = response.json()
            if not isinstance(rows, list):
                raise ValueError('Invalid GitHub release list')
            for row in rows:
                if type(row.get('id')) is not int or row['id'] in seen:
                    raise ValueError('Invalid or repeated GitHub release page')
                seen.add(row['id'])
                releases.append(row)
            if len(rows) < 100:
                break
        else:
            raise ValueError('Release pagination limit exceeded')
        eligible = [r for r in releases if data_release(r)]
        def publication_time(release):
            stamp = datetime.fromisoformat(release['published_at'].replace('Z', '+00:00'))
            if stamp.utcoffset() is None:
                raise ValueError('Missing release publication timezone')
            return stamp, release['id']
        eligible.sort(key=publication_time, reverse=True)
        retained, obsolete = eligible[:keep], eligible[keep:]
        if protected_tag and protected_tag not in {r['tag_name'] for r in retained}:
            raise ValueError('Just-published release was not found among retained releases')
        report.update(data_release_count=len(eligible), ignored_release_count=len(releases)-len(eligible),
                      planned_deletions=[r['tag_name'] for r in reversed(obsolete)])
        update()
        for release in reversed(obsolete):
            if dry_run:
                continue
            response = client.delete(base+f'/releases/{release["id"]}', headers=headers)
            if response.status_code != 404:
                response.raise_for_status()
            item = {'id': release['id'], 'tag': release['tag_name'], 'tag_deleted': False}
            report['deleted'].append(item)
            update()
            # Tags match our exact generated timestamp format, so this can never
            # target a branch, user version tag, or a retained catalog release.
            response = client.delete(base+'/git/refs/tags/'+release['tag_name'], headers=headers)
            if response.status_code != 404:
                response.raise_for_status()
            item['tag_deleted'] = True
            update()
        report.update(status='dry_run' if dry_run else 'completed', remaining_count=len(eligible)-len(report['deleted']))
    except Exception as exc:
        report.update(status='failed', error_type=type(exc).__name__)
        if isinstance(exc, httpx.HTTPStatusError):
            report['http_status'] = exc.response.status_code
    update()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--settings', type=Path, default=ROOT/'data/daily-settings.json')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    settings = json.loads(args.settings.read_text(encoding='utf-8-sig'))
    with httpx.Client(proxy=settings.get('proxy'), timeout=60) as client:
        report = prune_releases(settings['repository'], read_token(ROOT/'data', 'publish'),
            keep=settings.get('release_retention_count', 31), client=client, dry_run=args.dry_run)
    destination = ROOT/'data/daily/retention-report.json'
    atomic_write(destination, json.dumps(report, ensure_ascii=False, indent=2).encode('utf-8'))
    print(json.dumps(report, ensure_ascii=False))
    return 1 if report['status'] == 'failed' else 0


if __name__ == '__main__':
    raise SystemExit(main())
