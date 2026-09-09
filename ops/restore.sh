#!/bin/bash
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
    echo "Run this restore as root." >&2
    exit 1
fi
if [ "$#" -ne 1 ] || [ ! -f "$1" ]; then
    echo "Usage: $0 /path/to/pi-manager_backup.tar.gz" >&2
    exit 1
fi

ARCHIVE="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"
DATA_DIR=/var/lib/pi-manager
TMP_ROOT="$(mktemp -d)"
trap 'rm -rf "$TMP_ROOT"' EXIT

tar -xzf "$ARCHIVE" -C "$TMP_ROOT"
test -f "$TMP_ROOT/instance/pi_manager.db"
sqlite3 "$TMP_ROOT/instance/pi_manager.db" "PRAGMA integrity_check;" | grep -qx ok

# Preserve the current state before replacing it.
/opt/pi-manager/current/ops/backup.sh
systemctl stop pi-manager

install -m 0640 -o pi-manager -g pi-manager "$TMP_ROOT/instance/pi_manager.db" "$DATA_DIR/instance/pi_manager.db"
rsync -a --delete "$TMP_ROOT/uploads/" "$DATA_DIR/uploads/"
rsync -a --delete "$TMP_ROOT/pdf/" "$DATA_DIR/pdf/"
if [ -f "$TMP_ROOT/settings.json" ]; then
    install -m 0640 -o pi-manager -g pi-manager "$TMP_ROOT/settings.json" "$DATA_DIR/settings.json"
fi
chown -R pi-manager:pi-manager "$DATA_DIR"

systemctl start pi-manager
curl --fail --silent --max-time 10 http://127.0.0.1:8000/login >/dev/null
echo "Restore completed and the application health check passed."
