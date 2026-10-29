"""Copy this small entry point into D:\\hermes\\data\\scripts for Hermes cron."""
import json
import os
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import sys

ROOT = Path(r'F:\Projects\game-platform')
started = datetime.now(timezone.utc).isoformat()
result = subprocess.run([str(ROOT/'.venv/Scripts/python.exe'), '-u', '-m', 'game_platform.daily_release'],
    cwd=ROOT, env={**os.environ, 'PYTHONUTF8': '1', 'PYTHONIOENCODING': 'utf-8'}, timeout=3300)
path = ROOT/'data/daily/latest-report.json'
report = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
if result.returncode or report.get('status') != 'published' or report.get('started_at', '') < started:
    print('FAILED: daily collection/publication did not complete. Report:', path)
    sys.exit(1)
if not report.get('scans') or not all(s.get('count_check_passed') for s in report['scans']):
    print('FAILED: IGDB count verification missing')
    sys.exit(1)
print('SUCCESS:', report['publication']['url'])
print('Games:', report['manifest']['record_count'], 'IGN:', report['manifest']['ign_record_count'],
      'IGN awaiting review:', report['pending_ign_games'])
