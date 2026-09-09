#!/bin/bash
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
    echo "Run this installer as root." >&2
    exit 1
fi

SOURCE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
APP_DIR=/opt/pi-manager
DATA_DIR=/var/lib/pi-manager

apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y python3 python3-venv nginx sqlite3 rsync curl unzip fonts-noto-cjk fonts-wqy-zenhei

OSSUTIL_VERSION=2.4.0
OSSUTIL_SHA256=85edf66b2fb7238f5c7e25cab820cf29312319fe4935b7c86a6b8485eb434f3c
OSSUTIL_TMP="$(mktemp -d)"
trap 'rm -rf "$OSSUTIL_TMP"' EXIT
curl -fsSLo "$OSSUTIL_TMP/ossutil.zip" \
    "https://gosspublic.alicdn.com/ossutil/v2/$OSSUTIL_VERSION/ossutil-$OSSUTIL_VERSION-linux-amd64.zip"
printf '%s  %s\n' "$OSSUTIL_SHA256" "$OSSUTIL_TMP/ossutil.zip" | sha256sum -c -
unzip -q "$OSSUTIL_TMP/ossutil.zip" -d "$OSSUTIL_TMP/unpacked"
install -m 0755 \
    "$OSSUTIL_TMP/unpacked/ossutil-$OSSUTIL_VERSION-linux-amd64/ossutil" \
    /usr/local/bin/ossutil2
rm -rf "$OSSUTIL_TMP"
trap - EXIT

id pi-manager >/dev/null 2>&1 || useradd --system --home "$DATA_DIR" --shell /usr/sbin/nologin pi-manager
install -d -m 0755 "$APP_DIR/releases"
install -d -m 0750 -o pi-manager -g pi-manager \
    "$DATA_DIR/instance" "$DATA_DIR/uploads" "$DATA_DIR/pdf" "$DATA_DIR/backups"
install -d -m 0750 /etc/pi-manager

RELEASE="$APP_DIR/releases/$(date +%Y%m%d%H%M%S)"
mkdir -p "$RELEASE"
rsync -a --exclude '.git' --exclude 'venv' --exclude 'instance' --exclude 'static/uploads' \
    --exclude 'pdf' --exclude 'backups' --exclude 'settings.json' --exclude '*.log' \
    --exclude '*.csv' --exclude '*.xlsx' --exclude '__pycache__' --exclude '.DS_Store' \
    --exclude 'auth*' "$SOURCE_DIR/" "$RELEASE/"
ln -sfn "$RELEASE" "$APP_DIR/current"

python3 -m venv "$APP_DIR/venv"
"$APP_DIR/venv/bin/pip" install --upgrade pip
"$APP_DIR/venv/bin/pip" install -r "$APP_DIR/current/requirements.txt"

if [ ! -f /etc/pi-manager/pi-manager.env ]; then
    install -m 0640 -o root -g pi-manager "$APP_DIR/current/ops/pi-manager.env.example" /etc/pi-manager/pi-manager.env
    GENERATED_SECRET="$(python3 -c 'import secrets; print(secrets.token_urlsafe(64))')"
    sed -i "s#^SECRET_KEY=.*#SECRET_KEY=$GENERATED_SECRET#" /etc/pi-manager/pi-manager.env
fi

install -m 0644 "$APP_DIR/current/ops/pi-manager.service" /etc/systemd/system/pi-manager.service
install -m 0644 "$APP_DIR/current/ops/pi-manager-backup.service" /etc/systemd/system/pi-manager-backup.service
install -m 0644 "$APP_DIR/current/ops/pi-manager-backup.timer" /etc/systemd/system/pi-manager-backup.timer
install -m 0644 "$APP_DIR/current/ops/nginx-pi-manager.conf" /etc/nginx/sites-available/pi-manager
ln -sfn /etc/nginx/sites-available/pi-manager /etc/nginx/sites-enabled/pi-manager
rm -f /etc/nginx/sites-enabled/default

systemctl daemon-reload
nginx -t
systemctl enable nginx pi-manager pi-manager-backup.timer

echo "Installation prepared with a generated secret. Migrate data, then start pi-manager."
