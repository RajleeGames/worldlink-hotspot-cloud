#!/usr/bin/env bash
# Run as miraji AFTER first deployment: bash deploy/update.sh
# Does not replace the .env file, SQLite file, or media uploads.
set -euo pipefail
APP=/var/www/worldlink-hotspot-cloud
DATA=/var/lib/worldlink-hotspot-cloud
BACKUPS=/var/backups/worldlink-hotspot-cloud
SERVICE=worldlink-hotspot.service

cd "$APP"
mkdir -p "$BACKUPS"
if [ -f "$DATA/db.sqlite3" ]; then
  echo 'Backing up SQLite online before code update...'
  "$APP/.venv/bin/python" - "$DATA/db.sqlite3" "$BACKUPS" <<'PY'
from datetime import datetime, timezone
from pathlib import Path
import sqlite3, sys
src = Path(sys.argv[1])
dst = Path(sys.argv[2]) / f"db-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.sqlite3"
with sqlite3.connect(str(src)) as conn:
    with sqlite3.connect(str(dst)) as target:
        conn.backup(target)
print('SQLite backup:', dst)
PY
fi

echo 'Pulling reviewed code...'
git pull --ff-only

echo 'Updating Python requirements and Django tables...'
"$APP/.venv/bin/python" -m pip install -r requirements.txt
"$APP/.venv/bin/python" manage.py check
"$APP/.venv/bin/python" manage.py migrate --noinput
"$APP/.venv/bin/python" manage.py collectstatic --noinput

echo 'Restarting only the WorldLink Hotspot service...'
sudo systemctl restart "$SERVICE"
sudo systemctl --no-pager --full status "$SERVICE"
echo 'Local HTTP check (301/302 redirects are normal when HTTPS is enforced):'
curl -sS -o /dev/null -w 'HTTP %{http_code}\n' -H 'Host: wifi.worldlinksecurity.co.tz' http://127.0.0.1:8095/login/
