#!/bin/bash
# ============================================================
# PI Manager — Update NAS (CODE ONLY, preserves data)
# Run this on your Mac to push code updates to NAS
# Your database, images, settings, backups will NOT be touched.
# ============================================================

NAS_USER="${NAS_USER:-姜姜}"
NAS_HOST="${NAS_HOST:-}"
NAS_PATH="${NAS_PATH:-/home/姜姜/okki}"

if [ -z "$NAS_HOST" ]; then
    echo "Usage: NAS_HOST=<NAS_IP> bash update.sh"
    echo "Example: NAS_HOST=192.168.1.100 bash update.sh"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "========================================="
echo " PI Manager — Update NAS (Code Only)"
echo " Target: ${NAS_USER}@${NAS_HOST}:${NAS_PATH}"
echo "========================================="
echo ""
echo " ⚠️  DATA SAFE: instance/ static/uploads/ settings.json backups/ are EXCLUDED"
echo ""

# 1. Stop server on NAS
echo "[1/4] Stopping server on NAS..."
ssh "${NAS_USER}@${NAS_HOST}" "cd ${NAS_PATH} && bash stop.sh 2>/dev/null || true"

# 2. Upload code files only (EXCLUDE data directories)
echo "[2/4] Uploading code..."
rsync -avz --delete \
    --exclude '.git/' \
    --exclude '__pycache__/' \
    --exclude '*.pyc' \
    --exclude '.DS_Store' \
    --exclude 'instance/' \
    --exclude 'static/uploads/' \
    --exclude 'settings.json' \
    --exclude 'backups/' \
    --exclude 'venv/' \
    --exclude 'pi_manager.log' \
    --exclude 'pi_manager.pid' \
    --exclude 'pdf/*.pdf' \
    --exclude 'pdf/*.xlsx' \
    ./ "${NAS_USER}@${NAS_HOST}:${NAS_PATH}/"

# 3. Install any new dependencies
echo "[3/4] Installing dependencies..."
ssh "${NAS_USER}@${NAS_HOST}" "cd ${NAS_PATH} && python3 -m pip install --user -r requirements.txt 2>/dev/null"

# 4. Restart server
echo "[4/4] Starting server..."
ssh "${NAS_USER}@${NAS_HOST}" "cd ${NAS_PATH} && bash start.sh"

echo ""
echo "========================================="
echo " Update complete!"
echo " Your data (database, images, settings) is preserved."
echo "========================================="
