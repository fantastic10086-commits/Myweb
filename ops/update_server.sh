#!/bin/bash
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
    echo "Run this updater as root." >&2
    exit 1
fi

SOURCE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
APP_DIR=/opt/pi-manager
RELEASE="$APP_DIR/releases/$(date +%Y%m%d%H%M%S)"
PREVIOUS="$(readlink -f "$APP_DIR/current" || true)"

# The login route can render without CSS or JavaScript.  Keep this explicit
# list so an incomplete staging upload can never be published as a usable UI.
REQUIRED_STATIC_ASSETS=(
    static/favicon.svg
    static/favicon.ico
    static/favicon.png
    static/style.css
    static/lib/bootstrap.min.css
    static/lib/bootstrap-icons.css
    static/lib/bootstrap-icons.woff2
    static/lib/bootstrap.bundle.min.js
)

require_static_assets() {
    local root="$1"
    local asset

    for asset in "${REQUIRED_STATIC_ASSETS[@]}"; do
        if [ ! -s "$root/$asset" ]; then
            echo "Required static asset is missing: $root/$asset" >&2
            return 1
        fi
    done
}

# Fail before making a release if the staging directory lost its static/ tree.
require_static_assets "$SOURCE_DIR"

mkdir -p "$RELEASE"
rsync -a --exclude '.git' --exclude 'venv' --exclude 'instance' --exclude 'static/uploads' \
    --exclude 'pdf' --exclude 'backups' --exclude 'settings.json' --exclude '*.log' \
    --exclude '*.csv' \
    --include 'assets/system_default_pi_template.xlsx' \
    --include 'assets/qisuo_legacy_pi_template.xlsx' \
    --include 'assets/packing_a4.xlsx' \
    --include 'assets/packing_compact_100x150.xlsx' \
    --include 'assets/customs_declaration_template.xlsx' \
    --include 'assets/customer_history_template.xlsx' \
    --exclude '*.xlsx' \
    --exclude '__pycache__' --exclude '.DS_Store' \
    --exclude 'auth*' --exclude 'tmp' "$SOURCE_DIR/" "$RELEASE/"

require_static_assets "$RELEASE"

"$APP_DIR/venv/bin/pip" install -r "$RELEASE/requirements.txt"
ln -sfn "$RELEASE" "$APP_DIR/current"
install -m 0644 "$RELEASE/ops/pi-manager.service" /etc/systemd/system/pi-manager.service
install -m 0644 "$RELEASE/ops/pi-manager-backup.service" /etc/systemd/system/pi-manager-backup.service
install -m 0644 "$RELEASE/ops/pi-manager-backup.timer" /etc/systemd/system/pi-manager-backup.timer
install -m 0644 "$RELEASE/ops/pi-manager-webpush.service" /etc/systemd/system/pi-manager-webpush.service
systemctl daemon-reload

health_ok=false
if systemctl restart pi-manager; then
    for attempt in $(seq 1 20); do
        if curl --fail --silent --max-time 5 http://127.0.0.1:8000/login >/dev/null \
            && curl --fail --silent --max-time 5 http://127.0.0.1:8000/favicon.ico >/dev/null \
            && curl --fail --silent --max-time 5 http://127.0.0.1:8000/static/favicon.png >/dev/null \
            && curl --fail --silent --max-time 5 http://127.0.0.1:8000/static/style.css >/dev/null \
            && curl --fail --silent --max-time 5 http://127.0.0.1:8000/static/lib/bootstrap.min.css >/dev/null; then
            health_ok=true
            break
        fi
        sleep 1
    done
fi

if [ "$health_ok" != true ]; then
    if [ -n "$PREVIOUS" ] && [ -d "$PREVIOUS" ]; then
        ln -sfn "$PREVIOUS" "$APP_DIR/current"
        systemctl restart pi-manager
    fi
    echo "Update failed and the previous release was restored." >&2
    exit 1
fi

echo "Update completed successfully."
if [ -f /etc/pi-manager/webpush.env ]; then
    systemctl enable pi-manager-webpush
    systemctl restart pi-manager-webpush
    systemctl is-active --quiet pi-manager-webpush
fi
