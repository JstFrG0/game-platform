"""Prompt locally; never send credentials to chat or commit them to Git."""
import getpass
import os
import subprocess
from pathlib import Path

root=Path(__file__).resolve().parents[1]
if subprocess.run(['git','ls-files','--error-unmatch','.env'],cwd=root,capture_output=True).returncode==0:
    raise SystemExit('.env 已被 Git 跟踪，停止写入。请先执行 git rm --cached .env。')
client_id=input('IGDB / Twitch Client ID: ').strip()
secret=getpass.getpass('Client Secret（输入不显示）: ').strip()
if not client_id or not secret or any('\n' in value or '\r' in value for value in (client_id,secret)):
    raise SystemExit('凭据不能为空或包含换行。')
path=root/'.env'
path.write_text(f'IGDB_CLIENT_ID={client_id}\nIGDB_CLIENT_SECRET={secret}\n',encoding='utf-8')
if os.name!='nt':path.chmod(0o600)
print('本地凭据已保存。.env 被 Git 忽略，不要上传该文件。')
