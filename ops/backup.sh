#!/bin/bash
set -euo pipefail

DATA_ROOT=/var/lib/pi-manager
BACKUP_ROOT="$DATA_ROOT/backups"
OSSUTIL_BIN="${OSSUTIL_BIN:-/usr/local/bin/ossutil2}"
OSSUTIL_CONFIG="${OSSUTIL_CONFIG:-/root/.ossutilconfig-pi-manager}"
OSS_BUCKET="${OSS_BUCKET:-pi-manager-backup}"
OSS_PREFIX="${OSS_PREFIX:-pi-manager-backups}"
LOCAL_BACKUP_KEEP="${LOCAL_BACKUP_KEEP:-5}"
STAMP="$(date +%Y%m%d_%H%M%S)"
TMP_ROOT="$(mktemp -d)"
ARCHIVE="$BACKUP_ROOT/pi-manager_$STAMP.tar.gz"
trap 'rm -rf "$TMP_ROOT"' EXIT

install -d -m 0750 -o pi-manager -g pi-manager "$BACKUP_ROOT"
mkdir -p "$TMP_ROOT/instance"

# SQLite's backup command creates a transactionally consistent copy while live.
sqlite3 "$DATA_ROOT/instance/pi_manager.db" ".timeout 30000" ".backup '$TMP_ROOT/instance/pi_manager.db'"
sqlite3 "$TMP_ROOT/instance/pi_manager.db" "PRAGMA integrity_check;" | grep -qx ok

tar -C "$DATA_ROOT" -czf "$ARCHIVE" \
    -C "$TMP_ROOT" instance \
    -C "$DATA_ROOT" uploads pdf settings.json
chmod 0640 "$ARCHIVE"

if [[ ! "$LOCAL_BACKUP_KEEP" =~ ^[0-9]+$ ]] || [ "$LOCAL_BACKUP_KEEP" -lt 3 ]; then
    echo "LOCAL_BACKUP_KEEP must be an integer of at least 3." >&2
    exit 1
fi

# If Alibaba's official OSS tool is configured, copy the archive off-server.
if [ -x "$OSSUTIL_BIN" ] && [ -f "$OSSUTIL_CONFIG" ]; then
    REMOTE_OBJECT="oss://${OSS_BUCKET}/${OSS_PREFIX}/$(hostname)/$(basename "$ARCHIVE")"
    "$OSSUTIL_BIN" cp "$ARCHIVE" "$REMOTE_OBJECT" --config-file "$OSSUTIL_CONFIG" --force
    "$OSSUTIL_BIN" ls "$REMOTE_OBJECT" \
        --config-file "$OSSUTIL_CONFIG" --short-format --limited-num 1 \
        | grep -Fqx "$REMOTE_OBJECT"

    # Only prune local copies after the new archive is verified in OSS.
    mapfile -t LOCAL_ARCHIVES < <(
        find "$BACKUP_ROOT" -maxdepth 1 -type f -name 'pi-manager_*.tar.gz' \
            -printf '%T@ %p\n' | sort -nr | cut -d' ' -f2-
    )
    if [ "${#LOCAL_ARCHIVES[@]}" -gt "$LOCAL_BACKUP_KEEP" ]; then
        for OLD_ARCHIVE in "${LOCAL_ARCHIVES[@]:$LOCAL_BACKUP_KEEP}"; do
            rm -f -- "$OLD_ARCHIVE"
        done
    fi
fi
