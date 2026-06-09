#!/bin/bash
# ──────────────────────────────────────────────────────────────
# PI Manager — NAS Startup Script
# Usage: bash start.sh
# ──────────────────────────────────────────────────────────────

# Detect the directory where this script lives
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Configuration
PORT=5001
LOG_FILE="$SCRIPT_DIR/pi_manager.log"
PID_FILE="$SCRIPT_DIR/pi_manager.pid"

# Python path — adjust if needed (e.g. /usr/bin/python3)
PYTHON="${PYTHON:-python3}"

echo "========================================="
echo " PI Manager — Starting..."
echo " Directory: $SCRIPT_DIR"
echo " Port:      $PORT"
echo " Log:       $LOG_FILE"
echo "========================================="

# Check if already running
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE")
    if kill -0 "$OLD_PID" 2>/dev/null; then
        echo "ERROR: PI Manager is already running (PID: $OLD_PID)."
        echo "Run 'bash stop.sh' to stop it first."
        exit 1
    else
        rm -f "$PID_FILE"
    fi
fi

# Setup virtual environment (optional)
if [ -d "$SCRIPT_DIR/venv" ]; then
    echo "[*] Activating virtual environment..."
    source "$SCRIPT_DIR/venv/bin/activate"
fi

# Check dependencies
echo "[*] Checking dependencies..."
$PYTHON -c "import flask; import reportlab;" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "[!] Dependencies missing. Installing..."
    $PYTHON -m pip install -r "$SCRIPT_DIR/requirements.txt"
fi

# Ensure pdf and instance directories exist
mkdir -p "$SCRIPT_DIR/pdf" "$SCRIPT_DIR/instance"

# Start with gunicorn (production) or fallback to Flask dev server
echo "[*] Starting server on 0.0.0.0:$PORT ..."

if command -v gunicorn &> /dev/null; then
    nohup gunicorn --bind 0.0.0.0:$PORT \
          --workers 2 \
          --timeout 120 \
          --access-logfile "$LOG_FILE" \
          --error-logfile "$LOG_FILE" \
          --chdir "$SCRIPT_DIR" \
          app:app > /dev/null 2>&1 &
else
    echo "[!] gunicorn not found, using Flask dev server (not recommended for production)"
    nohup $PYTHON "$SCRIPT_DIR/app.py" > "$LOG_FILE" 2>&1 &
fi

# Save PID
echo $! > "$PID_FILE"

sleep 2

if kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    echo ""
    echo " ✓ PI Manager started successfully!"
    echo "   PID:  $(cat "$PID_FILE")"
    echo "   URL:  http://<NAS_IP>:$PORT"
    echo "   Log:  $LOG_FILE"
    echo ""
    echo " To stop:  bash $SCRIPT_DIR/stop.sh"
    echo " To view log:  tail -f $LOG_FILE"
else
    echo ""
    echo " ✗ Failed to start. Check log: $LOG_FILE"
    rm -f "$PID_FILE"
    exit 1
fi
