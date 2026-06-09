#!/bin/bash
# ──────────────────────────────────────────────────────────────
# PI Manager — Stop Script
# Usage: bash stop.sh
# ──────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PID_FILE="$SCRIPT_DIR/pi_manager.pid"

echo "========================================="
echo " PI Manager — Stopping..."
echo "========================================="

if [ ! -f "$PID_FILE" ]; then
    echo "No PID file found. PI Manager may not be running."
    echo "Checking for residual processes..."
    PIDS=$(pgrep -f "app:app\|gunicorn.*pi_manager\|python.*app.py" 2>/dev/null)
    if [ -n "$PIDS" ]; then
        echo "Found processes: $PIDS"
        kill $PIDS 2>/dev/null
        echo "Killed residual processes."
    else
        echo "No running processes found."
    fi
    exit 0
fi

PID=$(cat "$PID_FILE")

if kill -0 "$PID" 2>/dev/null; then
    echo "Stopping process $PID ..."
    kill "$PID"
    sleep 1
    if kill -0 "$PID" 2>/dev/null; then
        echo "Process still running, force killing..."
        kill -9 "$PID"
    fi
    echo " ✓ PI Manager stopped."
else
    echo "Process $PID is not running (stale PID file)."
fi

rm -f "$PID_FILE"
