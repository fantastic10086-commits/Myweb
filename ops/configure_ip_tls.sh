#!/bin/bash
set -euo pipefail

if [ "$(id -u)" -ne 0 ] || [ "$#" -ne 1 ]; then
    echo "Usage: sudo $0 PUBLIC_IP" >&2
    exit 1
fi

PUBLIC_IP="$1"
if ! [[ "$PUBLIC_IP" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo "Invalid IPv4 address." >&2
    exit 1
fi

install -d -m 0750 -o root -g pi-manager /etc/pi-manager/tls
openssl req -x509 -newkey rsa:3072 -sha256 -days 365 -nodes \
    -keyout /etc/pi-manager/tls/server.key \
    -out /etc/pi-manager/tls/server.crt \
    -subj "/CN=$PUBLIC_IP" \
    -addext "subjectAltName=IP:$PUBLIC_IP"
chown root:pi-manager /etc/pi-manager/tls/server.key /etc/pi-manager/tls/server.crt
chmod 0640 /etc/pi-manager/tls/server.key
chmod 0644 /etc/pi-manager/tls/server.crt

install -m 0644 /opt/pi-manager/current/ops/nginx-pi-manager.conf /etc/nginx/sites-available/pi-manager
nginx -t
systemctl reload nginx
echo "Temporary IP-based TLS configured for https://$PUBLIC_IP/"
