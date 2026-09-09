#!/bin/bash
set -euo pipefail

APP_ROOT="$(cd "$(dirname "$0")" && pwd)"
PID_FILE="$APP_ROOT/.run/pi-manager.pid"

if command -v systemctl >/dev/null 2>&1 && systemctl cat pi-manager.service >/dev/null 2>&1; then
    sudo systemctl stop pi-manager
    exit 0
fi

if [ ! -f "$PID_FILE" ]; then
    echo "PI Manager is not running."
    exit 0
fi

PID="$(cat "$PID_FILE")"
if kill -0 "$PID" 2>/dev/null; then
    kill "$PID"
fi
rm -f "$PID_FILE"
echo "PI Manager stopped."
