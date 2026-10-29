"""Local application update configuration, DPAPI credentials and background checks."""
from __future__ import annotations

import asyncio
from contextlib import suppress
import json
import logging
import os
import sqlite3
from pathlib import Path
import subprocess

import httpx

from .collect_igdb import utc_now
from .data_updates import check_repository, installed_update, update_from_github

log = logging.getLogger(__name__)


class CredentialError(RuntimeError):
    pass


def load_settings(data_directory):
    path = Path(data_directory)/'update-settings.json'
    settings = json.loads(path.read_text(encoding='utf-8-sig')) if path.exists() else {}
    if not isinstance(settings, dict):
        raise ValueError('更新配置必须为对象。')
    repository = os.environ.get('GAME_DATA_REPOSITORY', settings.get('repository', ''))
    if not isinstance(repository, str):
        raise ValueError('更新仓库必须为字符串。')
    repository = repository.strip()
    enabled = settings.get('enabled', bool(repository))
    if type(enabled) is not bool:
        raise ValueError('更新开关必须为布尔值。')
    interval = os.environ.get('GAME_DATA_UPDATE_INTERVAL_SECONDS', settings.get('interval_seconds', 21600))
    if type(interval) is bool:
        raise ValueError('更新间隔无效。')
    interval = int(interval)
    if interval < 60:
        raise ValueError('更新间隔至少60秒。')
    if repository:
        check_repository(repository)
    if enabled and not repository:
        raise ValueError('启用更新需要配置仓库。')
    credential = settings.get('credential', 'auto')
    if credential not in ('auto', 'read', 'publish', 'none'):
        raise ValueError('更新凭据配置无效。')
    return dict(enabled=enabled, repository=repository, interval_seconds=interval, credential=credential)


def read_token(data_directory, credential):
    token = os.environ.get('GAME_DATA_GITHUB_TOKEN', '').strip()
    if token:
        return token
    if credential == 'none':
        return ''
    names = ['github-read.dpapi', 'github-publish.dpapi'] if credential == 'auto' else [f'github-{credential}.dpapi']
    path = next((Path(data_directory)/'credentials'/name for name in names
                 if (Path(data_directory)/'credentials'/name).is_file()), None)
    if path is None:
        raise CredentialError('找不到 GitHub 凭据。')
    if os.name != 'nt':
        raise CredentialError('Windows 加密凭据需要在原 Windows 账户下读取。')
    # Only the path is passed in the environment. The secret is captured privately
    # from stdout, never used in a command argument, log or HTTP status response.
    command = ("$ErrorActionPreference='Stop'; "
               "$s=ConvertTo-SecureString -String (Get-Content -LiteralPath $env:GAME_DATA_CREDENTIAL_FILE -Raw).Trim(); "
               "try{[Console]::Write([System.Net.NetworkCredential]::new('', $s).Password)}finally{$s.Dispose()}")
    options = {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}
    credential_env = {**os.environ, 'GAME_DATA_CREDENTIAL_FILE': str(path.resolve())}
    # A parent PowerShell 7 session may supply its Core-only module search path.
    # Let Windows PowerShell rebuild its own path for Microsoft.PowerShell.Security.
    credential_env = {key: value for key, value in credential_env.items() if key.upper() != 'PSMODULEPATH'}
    result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', command],
        capture_output=True, text=True, timeout=20,
        env=credential_env, **options)
    if result.returncode or not result.stdout.strip():
        raise CredentialError('无法解密 GitHub 凭据，请使用保存凭据的 Windows 账户启动软件。')
    return result.stdout.strip()


def error_message(exc):
    if isinstance(exc, CredentialError):
        return '无法读取 GitHub 凭据，请使用保存凭据的 Windows 账户启动软件。'
    if isinstance(exc, httpx.HTTPStatusError):
        if exc.response.status_code in (401, 403, 404):
            return '无法访问更新仓库，请检查凭据有效期和仓库权限。'
        if exc.response.status_code == 429:
            return '更新检查暂时受限，请稍后重试。'
    if isinstance(exc, httpx.TransportError):
        return '暂时无法连接 GitHub，继续使用本地数据。'
    return '本次更新未完成，本地数据已保留，请稍后重试。'


class UpdateService:
    def __init__(self, database):
        self.database = Path(database)
        self.task = None
        self.timer = None
        self.state = {'status': 'disabled', 'enabled': False, 'version': None, 'error': None}
        try:
            self.settings = load_settings(self.database.parent)
            self.state.update(enabled=self.settings['enabled'], repository=self.settings['repository'],
                              interval_seconds=self.settings['interval_seconds'])
            receipt = installed_update(self.database)
            if receipt:
                self.state['version'] = receipt['version']
            if self.settings['enabled']:
                self.state['status'] = 'idle'
        except (ValueError, OSError, TypeError, sqlite3.Error) as exc:
            self.settings = {'enabled': False}
            self.state.update(status='configuration_error', error='更新配置无法读取，请检查本机更新设置。')
            log.warning('Data update configuration unavailable (%s)', type(exc).__name__)

    def snapshot(self):
        return dict(self.state)

    def request_check(self):
        if not self.settings['enabled']:
            return False
        if self.task is None or self.task.done():
            self.state.update(status='checking', checked_at=utc_now(), error=None)
            self.task = asyncio.create_task(self._check())
        return True

    async def _check(self):
        loop = asyncio.get_running_loop()
        def progress(status):
            loop.call_soon_threadsafe(self.state.update, {'status': status})
        def run():
            token = read_token(self.database.parent, self.settings['credential'])
            return update_from_github(self.database, self.settings['repository'], token=token, progress=progress)
        try:
            result = await asyncio.to_thread(run)
            # Only explicitly public fields leave this service; backup paths and
            # credentials remain on the backend.
            self.state.update({k: v for k, v in result.items() if k in ('status', 'version', 'records', 'ign_reviews')})
            self.state.update(error=None, finished_at=utc_now())
        except Exception as exc:
            self.state.update(status='failed', error=error_message(exc), finished_at=utc_now())
            log.warning('Data update check failed (%s)', type(exc).__name__)

    async def _schedule(self):
        while True:
            self.request_check()
            if self.task:
                await asyncio.shield(self.task)
            await asyncio.sleep(self.settings['interval_seconds'])

    def start(self):
        if self.settings['enabled']:
            self.timer = asyncio.create_task(self._schedule())

    async def close(self):
        if self.timer:
            self.timer.cancel()
            with suppress(asyncio.CancelledError):
                await self.timer
        if self.task:
            await asyncio.shield(self.task)
