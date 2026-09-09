#!/bin/bash
set -euo pipefail

APP_ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$APP_ROOT"

if command -v systemctl >/dev/null 2>&1 && systemctl cat pi-manager.service >/dev/null 2>&1; then
    sudo systemctl start pi-manager
    sudo systemctl --no-pager status pi-manager
    exit 0
fi

mkdir -p "$APP_ROOT/.run"
if [ -f "$APP_ROOT/.run/pi-manager.pid" ] && kill -0 "$(cat "$APP_ROOT/.run/pi-manager.pid")" 2>/dev/null; then
    echo "PI Manager is already running."
    exit 0
fi

nohup "$APP_ROOT/venv/bin/gunicorn" --workers 1 --threads 4 --timeout 120 \
    --bind 127.0.0.1:8000 app:app > "$APP_ROOT/pi_manager.log" 2>&1 &
echo $! > "$APP_ROOT/.run/pi-manager.pid"
echo "PI Manager started on http://127.0.0.1:8000"
