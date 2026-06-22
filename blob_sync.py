"""
Vercel Blob sync — persist SQLite database across cold starts.
Uses Vercel Blob REST API (no extra dependencies needed).
"""

import os
import json
import time
import shutil
import logging
from urllib.parse import quote, urlencode
import urllib.request
import urllib.error

log = logging.getLogger('blob_sync')

BLOB_TOKEN = os.environ.get('BLOB_READ_WRITE_TOKEN', '')
BLOB_STORE_ID = os.environ.get('BLOB_STORE_ID', '')
BLOB_API_URL = 'https://vercel.com/api/blob'
BLOB_API_VERSION = '12'
BLOB_KEY = 'pi_manager.db'  # blob path name
LAST_ERROR = ''


def _set_error(message):
    global LAST_ERROR
    LAST_ERROR = message
    log.error(message)


def get_last_error():
    return LAST_ERROR


def _store_id():
    """Return the bare Blob store id used by API headers and private URLs."""
    configured = BLOB_STORE_ID.strip()
    if configured:
        return configured[6:] if configured.startswith('store_') else configured

    parts = BLOB_TOKEN.split('_')
    if len(parts) >= 5 and parts[3] == 'store':
        return parts[4]
    return parts[3] if len(parts) >= 4 else ''


def _api_request(method, path='/', body=None, content_type=None, extra_headers=None):
    """Make a request to the Vercel Blob control API."""
    store_id = _store_id()
    url = f'{BLOB_API_URL}{path}'
    headers = {
        'Authorization': f'Bearer {BLOB_TOKEN}',
        'x-api-version': BLOB_API_VERSION,
    }
    if store_id:
        headers['x-vercel-blob-store-id'] = store_id
    if content_type:
        headers['Content-Type'] = content_type
    if extra_headers:
        headers.update(extra_headers)

    data = None
    if body is not None:
        if isinstance(body, bytes):
            data = body
        elif isinstance(body, dict):
            data = json.dumps(body).encode('utf-8')
            headers['Content-Type'] = 'application/json'
        elif isinstance(body, str):
            data = body.encode('utf-8')

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        resp = urllib.request.urlopen(req, timeout=30)
        return resp.read()
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', errors='replace')
        _set_error(f'Blob API {method} {path} failed: HTTP {e.code} {body}')
        return None
    except urllib.error.URLError as e:
        _set_error(f'Blob API {method} {path} failed: {e.reason}')
        return None
    except Exception as e:
        _set_error(f'Blob API {method} {path} failed: {e}')
        return None


def download_db(db_path):
    """Download the SQLite database from Vercel Blob."""
    if not BLOB_TOKEN:
        _set_error('BLOB_READ_WRITE_TOKEN is not set')
        return False

    store_id = _store_id()
    if not store_id:
        _set_error('Cannot determine Blob store id from BLOB_STORE_ID or BLOB_READ_WRITE_TOKEN')
        return False

    log.info(f'Downloading {BLOB_KEY} from Blob...')
    url = f'https://{store_id}.private.blob.vercel-storage.com/{quote(BLOB_KEY)}?cache=0'
    req = urllib.request.Request(url, headers={'Authorization': f'Bearer {BLOB_TOKEN}'}, method='GET')
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            log.info(f'No existing {BLOB_KEY} in Blob, starting fresh')
        else:
            body = e.read().decode('utf-8', errors='replace')
            _set_error(f'Blob download failed: HTTP {e.code} {body}')
        return False
    except urllib.error.URLError as e:
        _set_error(f'Blob download failed: {e.reason}')
        return False
    except Exception as e:
        _set_error(f'Blob download failed: {e}')
        return False

    if not data:
        return False

    # Write to temp then move atomically
    tmp_path = db_path + '.tmp'
    with open(tmp_path, 'wb') as f:
        f.write(data)
    os.replace(tmp_path, db_path)

    log.info(f'Database restored from Blob ({len(data)} bytes)')
    return True


def upload_db(db_path):
    """Upload the SQLite database to Vercel Blob."""
    if not BLOB_TOKEN:
        _set_error('BLOB_READ_WRITE_TOKEN is not set')
        return False

    if not os.path.exists(db_path):
        _set_error(f'{db_path} not found, skipping blob upload')
        return False

    # Make a backup copy first
    backup_path = db_path + '.blob_backup'
    shutil.copy2(db_path, backup_path)

    try:
        with open(backup_path, 'rb') as f:
            data = f.read()

        log.info(f'Uploading {BLOB_KEY} to Blob ({len(data)} bytes)...')

        params = urlencode({'pathname': BLOB_KEY})
        result = _api_request(
            'PUT',
            f'/?{params}',
            body=data,
            content_type='application/octet-stream',
            extra_headers={
                'x-vercel-blob-access': 'private',
                'x-content-type': 'application/octet-stream',
                'x-add-random-suffix': '0',
                'x-allow-overwrite': '1',
            },
        )

        if result:
            log.info('Database uploaded to Blob successfully')
            # Clean up backup
            os.remove(backup_path)
            return True
        else:
            if not LAST_ERROR:
                _set_error('Failed to upload database to Blob')
            return False
    except Exception as e:
        _set_error(f'Blob upload error: {e}')
        return False


def init_db(db_path):
    """Initialize database — download from Blob if available."""
    if BLOB_TOKEN:
        download_db(db_path)


def sync_db(db_path):
    """Persist the database to Blob before the response finishes."""
    if not BLOB_TOKEN:
        return False
    return upload_db(db_path)


def sync_db_async(db_path):
    """
    Schedule an async database sync to Blob.
    This spawns a background thread to avoid blocking the request.
    """
    if not BLOB_TOKEN:
        return
    import threading
    t = threading.Thread(target=upload_db, args=(db_path,), daemon=True)
    t.start()
