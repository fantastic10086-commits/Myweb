# PI Manager VPS deployment

Target: Alibaba Cloud Lightweight Application Server in Hong Kong, Ubuntu 24.04 LTS, 2 vCPU, 4 GB RAM, and a 50 GB SSD.

## Before deployment

1. Create the VPS and add an SSH public key.
2. Allow inbound TCP 22, 80, and 443 only. Restrict port 22 to trusted IPs when practical.
3. Enable Alibaba Cloud snapshots with at least seven retained copies.
4. Create a private Alibaba OSS bucket in the same Hong Kong region for off-server backups.
5. Upload the project to a temporary directory on the VPS.

Do not expose ports 5000, 5001, or 8000 to the internet.

## Initial installation

From the uploaded project directory:

```bash
sudo bash ops/install_server.sh
sudo nano /etc/pi-manager/pi-manager.env
```

The installer generates `SECRET_KEY` automatically. Keep `SESSION_COOKIE_SECURE=0` only during restricted IP acceptance testing. Change it to `1` immediately after HTTPS is enabled.

Install the document conversion component used by custom Excel PI templates and the Chinese font package:

```bash
sudo apt-get update
sudo apt-get install -y --no-install-recommends libreoffice-calc-nogui fonts-noto-cjk fonts-wqy-zenhei
```

Administrators can then manage multiple `.xlsx` PI templates from **单据模板**. Users select a template and PDF/Excel format in the export workbench. Temporary export edits never overwrite the original PI.

Migrate the final database, images, generated files, and DingTalk settings:

```bash
sudo bash ops/migrate_data.sh /path/to/uploaded-project-data
sudo systemctl start pi-manager
curl -I http://127.0.0.1:8000/login
```

Before IP-only acceptance testing, configure temporary encrypted access:

```bash
sudo bash ops/configure_ip_tls.sh SERVER_IP
```

Then visit `https://SERVER_IP/login`. The temporary self-signed certificate causes one browser warning, but protects credentials in transit. All existing users are required to change their temporary password before accessing business pages.

## Domain and HTTPS

After purchasing a domain, point an A record such as `pi.example.com` to the VPS. Replace `_` in `/etc/nginx/sites-available/pi-manager` with the domain, then install Certbot:

```bash
sudo apt-get install -y certbot python3-certbot-nginx
sudo certbot --nginx -d pi.example.com
```

Set `SESSION_COOKIE_SECURE=1` in `/etc/pi-manager/pi-manager.env` and restart the service.

## Alibaba OSS backup

The daily timer always creates a consistent local SQLite backup. Create the private bucket `pi-manager-backup` in Hong Kong and a dedicated RAM user with access only to `pi-manager-backups/*`. The server uses Alibaba's official ossutil 2.x client with Signature V4. Configure the credentials interactively so they never enter shell history:

```bash
sudo bash ops/configure_aliyun_oss.sh
sudo systemctl enable --now pi-manager-backup.timer
sudo systemctl start pi-manager-backup.service
sudo systemctl status pi-manager-backup.service
```

Perform a restore test after the first backup and at least once per month.

Restore a verified archive with:

```bash
sudo bash ops/restore.sh /path/to/pi-manager_backup.tar.gz
```

The restore command creates one final backup of the current state before replacing data.

## Updates and rollback

Upload a new code copy and run:

```bash
sudo bash ops/update_server.sh
```

The updater installs dependencies, switches to a timestamped release, checks `/login`, and restores the previous release if the health check fails. Business data remains under `/var/lib/pi-manager` and is not replaced by code updates.

## Operations

```bash
sudo systemctl status pi-manager
sudo journalctl -u pi-manager -f
sudo systemctl list-timers pi-manager-backup.timer
sudo nginx -t
```
