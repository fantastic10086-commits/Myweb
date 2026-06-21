#!/bin/bash
# ============================================================
# PI Manager — Initial NAS Deployment
# Run this on your Mac to upload the full project to NAS
# ============================================================

NAS_USER="${NAS_USER:-姜姜}"
NAS_HOST="${NAS_HOST:-}"           # NAS IP or hostname
NAS_PATH="${NAS_PATH:-/home/姜姜/okki}"

if [ -z "$NAS_HOST" ]; then
    echo "Usage: NAS_HOST=<NAS_IP> bash deploy.sh"
    echo "Example: NAS_HOST=192.168.1.100 bash deploy.sh"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "========================================="
echo " PI Manager — Deploy to NAS"
echo " Target: ${NAS_USER}@${NAS_HOST}:${NAS_PATH}"
echo "========================================="
echo ""

# 1. Create remote directory
echo "[1/4] Creating remote directory..."
ssh "${NAS_USER}@${NAS_HOST}" "mkdir -p ${NAS_PATH}"

# 2. Upload project files (exclude local-only stuff)
echo "[2/4] Uploading project files..."
rsync -avz --progress \
    --exclude '.git/' \
    --exclude '__pycache__/' \
    --exclude '*.pyc' \
    --exclude '.DS_Store' \
    --exclude 'instance/' \
    --exclude 'settings.json' \
    --exclude 'backups/' \
    --exclude 'venv/' \
    --exclude 'pi_manager.log' \
    --exclude 'pi_manager.pid' \
    ./ "${NAS_USER}@${NAS_HOST}:${NAS_PATH}/"

# 3. Setup on NAS
echo ""
echo "[3/4] Setting up on NAS..."
ssh "${NAS_USER}@${NAS_HOST}" "bash -s" << 'ENDSSH'
cd /home/姜姜/okki

# Create necessary directories
mkdir -p instance static/uploads pdf backups

# Set permissions
chmod 755 *.sh

# Check Python
echo "Python version:"
python3 --version 2>/dev/null || python --version 2>/dev/null

# Install/upgrade dependencies
echo "Installing Python dependencies..."
python3 -m pip install --user -r requirements.txt 2>/dev/null || pip3 install --user -r requirements.txt 2>/dev/null

echo ""
echo "Setup complete on NAS!"
ENDSSH

# 4. Copy data files SEPARATELY (only if not already on NAS)
echo ""
echo "[4/4] Uploading database & uploads (skip if already exists)..."
ssh "${NAS_USER}@${NAS_HOST}" "test -f ${NAS_PATH}/instance/pi_manager.db" && echo "  Database already exists on NAS, skipping." || \
    rsync -avz --progress instance/ "${NAS_USER}@${NAS_HOST}:${NAS_PATH}/instance/"

ssh "${NAS_USER}@${NAS_HOST}" "ls ${NAS_PATH}/static/uploads/ 2>/dev/null | head -1" && echo "  Uploads already exist on NAS, skipping." || \
    rsync -avz --progress static/uploads/ "${NAS_USER}@${NAS_HOST}:${NAS_PATH}/static/uploads/"

# Copy settings if exists locally
[ -f settings.json ] && scp settings.json "${NAS_USER}@${NAS_HOST}:${NAS_PATH}/settings.json"

echo ""
echo "========================================="
echo " Deployment complete!"
echo ""
echo " Next steps on NAS:"
echo "   1. SSH into NAS:  ssh ${NAS_USER}@${NAS_HOST}"
echo "   2. Start server:  cd ${NAS_PATH} && bash start.sh"
echo "   3. Check status:  tail -f ${NAS_PATH}/pi_manager.log"
echo "   4. Access at:     http://${NAS_HOST}:5001/login"
echo "========================================="
