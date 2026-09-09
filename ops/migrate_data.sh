#!/bin/bash
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
    echo "Run this migration as root." >&2
    exit 1
fi
if [ "$#" -ne 1 ]; then
    echo "Usage: $0 /path/to/uploaded-project-data" >&2
    exit 1
fi

SOURCE_DIR="$(cd "$1" && pwd)"
DATA_DIR=/var/lib/pi-manager

test -f "$SOURCE_DIR/instance/pi_manager.db"
systemctl stop pi-manager 2>/dev/null || true

install -d -m 0750 -o pi-manager -g pi-manager \
    "$DATA_DIR/instance" "$DATA_DIR/uploads" "$DATA_DIR/pdf" "$DATA_DIR/backups"
install -m 0640 -o pi-manager -g pi-manager \
    "$SOURCE_DIR/instance/pi_manager.db" "$DATA_DIR/instance/pi_manager.db"

if [ -d "$SOURCE_DIR/static/uploads" ]; then
    rsync -a "$SOURCE_DIR/static/uploads/" "$DATA_DIR/uploads/"
fi
if [ -d "$SOURCE_DIR/pdf" ]; then
    rsync -a "$SOURCE_DIR/pdf/" "$DATA_DIR/pdf/"
fi
if [ -f "$SOURCE_DIR/settings.json" ]; then
    install -m 0640 -o pi-manager -g pi-manager "$SOURCE_DIR/settings.json" "$DATA_DIR/settings.json"
else
    install -m 0640 -o pi-manager -g pi-manager /dev/null "$DATA_DIR/settings.json"
fi

chown -R pi-manager:pi-manager "$DATA_DIR"
sqlite3 "$DATA_DIR/instance/pi_manager.db" "PRAGMA integrity_check;" | grep -qx ok
echo "Data migration completed and integrity check passed."
