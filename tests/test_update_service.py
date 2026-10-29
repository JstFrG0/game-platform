import json
import os
from pathlib import Path
import subprocess
import threading
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from game_platform.api import create_app
from game_platform import update_service as service


def configure(tmp_path, **options):
    settings = dict(enabled=True, repository='owner/repo', interval_seconds=600, credential='auto', **options)
    (tmp_path/'update-settings.json').write_text(json.dumps(settings), encoding='utf-8')


def wait_state(client, expected):
    for _ in range(100):
        state = client.get('/api/v1/data-updates').json()
        if state['status'] == expected:
            return state
        time.sleep(0.01)
    pytest.fail(f'Expected {expected}, got {state}')


def test_settings_persist_and_environment_overrides(tmp_path, monkeypatch):
    configure(tmp_path)
    assert service.load_settings(tmp_path)['repository'] == 'owner/repo'
    monkeypatch.setenv('GAME_DATA_REPOSITORY', 'another/repo')
    monkeypatch.setenv('GAME_DATA_UPDATE_INTERVAL_SECONDS', '120')
    settings = service.load_settings(tmp_path)
    assert settings['repository'] == 'another/repo' and settings['interval_seconds'] == 120


def test_invalid_settings_leave_catalog_server_available(tmp_path):
    (tmp_path/'update-settings.json').write_text('{broken')
    with TestClient(create_app(tmp_path/'db.sqlite3')) as client:
        assert client.get('/api/v1/data-updates').json()['status'] == 'configuration_error'
        assert client.post('/api/v1/data-updates/check').status_code == 409


def test_manual_clicks_share_one_inflight_job(tmp_path, monkeypatch):
    configure(tmp_path)
    started, finish = threading.Event(), threading.Event()
    calls = []
    def run(*args, **kwargs):
        calls.append(1)
        started.set()
        assert finish.wait(3)
        return {'status': 'updated', 'version': '2026-01-01T00:00:00+00:00',
                'records': 5, 'backup': '/private/path', 'token': 'SECRET'}
    monkeypatch.setattr(service, 'read_token', lambda *args: 'SECRET')
    monkeypatch.setattr(service, 'update_from_github', run)
    try:
        with TestClient(create_app(tmp_path/'db.sqlite3')) as client:
            assert started.wait(2)
            for _ in range(3):
                response = client.post('/api/v1/data-updates/check', headers={'Origin': 'http://127.0.0.1:5173'})
                assert response.status_code == 202
            assert len(calls) == 1
            finish.set()
            state = wait_state(client, 'updated')
            assert state['records'] == 5
            assert 'SECRET' not in json.dumps(state) and 'backup' not in state and 'token' not in state
    finally:
        finish.set()


def test_update_trigger_rejects_cross_site_requests(tmp_path, monkeypatch):
    configure(tmp_path)
    monkeypatch.setattr(service, 'read_token', lambda *args: '')
    monkeypatch.setattr(service, 'update_from_github', lambda *args, **kwargs: {'status': 'no_release'})
    with TestClient(create_app(tmp_path/'db.sqlite3')) as client:
        assert client.post('/api/v1/data-updates/check', headers={'Origin': 'https://untrusted.example'}).status_code == 403
        assert client.post('/api/v1/data-updates/check', headers={'Sec-Fetch-Site': 'cross-site'}).status_code == 403


def test_invalid_token_error_is_actionable_without_exposing_secret(tmp_path, monkeypatch):
    configure(tmp_path)
    def fail(*args, **kwargs):
        request = httpx.Request('GET', 'https://api.github.com/repos/owner/repo')
        raise httpx.HTTPStatusError('SECRET', request=request, response=httpx.Response(401, request=request))
    monkeypatch.setattr(service, 'read_token', lambda *args: 'SECRET')
    monkeypatch.setattr(service, 'update_from_github', fail)
    with TestClient(create_app(tmp_path/'db.sqlite3')) as client:
        state = wait_state(client, 'failed')
        assert '仓库权限' in state['error'] and 'SECRET' not in json.dumps(state)
        assert not (tmp_path/'db.sqlite3').exists()


def test_missing_credentials_are_reported_before_network(tmp_path, monkeypatch):
    configure(tmp_path)
    monkeypatch.delenv('GAME_DATA_GITHUB_TOKEN', raising=False)
    monkeypatch.setattr(service, 'update_from_github', lambda *args, **kwargs: pytest.fail('unexpected network call'))
    with TestClient(create_app(tmp_path/'db.sqlite3')) as client:
        state = wait_state(client, 'failed')
        assert '保存凭据的 Windows 账户' in state['error']


@pytest.mark.skipif(os.name != 'nt', reason='Windows DPAPI integration')
def test_auto_credential_prefers_read_token_and_never_passes_secret_in_arguments(tmp_path, monkeypatch):
    monkeypatch.setenv('PSMODULEPATH', 'PowerShell-Core-only')
    monkeypatch.delenv('GAME_DATA_GITHUB_TOKEN', raising=False)
    credentials = tmp_path/'credentials'
    credentials.mkdir()
    for name in ('github-read.dpapi', 'github-publish.dpapi'):
        (credentials/name).write_text('encrypted')
    def run(args, **kwargs):
        assert 'SECRET' not in str(args)
        assert kwargs['capture_output']
        assert not any(key.upper() == 'PSMODULEPATH' for key in kwargs['env'])
        assert kwargs['env']['GAME_DATA_CREDENTIAL_FILE'].endswith('github-read.dpapi')
        return subprocess.CompletedProcess(args, 0, stdout='SECRET', stderr='')
    monkeypatch.setattr(subprocess, 'run', run)
    assert service.read_token(tmp_path, 'auto') == 'SECRET'


def test_environment_token_requires_no_credential_file(tmp_path, monkeypatch):
    monkeypatch.setenv('GAME_DATA_GITHUB_TOKEN', ' env-token ')
    assert service.read_token(tmp_path, 'auto') == 'env-token'
