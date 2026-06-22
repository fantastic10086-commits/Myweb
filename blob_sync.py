"""
Vercel Blob sync — persist SQLite database across cold starts.
Uses Vercel Blob REST API (no extra dependencies needed).
"""

import os
import json
import time
import shutil
import logging
import urllib.request
import urllib.error

log = logging.getLogger('blob_sync')

BLOB_TOKEN = os.environ.get('BLOB_READ_WRITE_TOKEN', '')
BLOB_URL = 'https://blob.vercel-storage.com'
BLOB_KEY = 'pi_manager.db'  # blob path name


def _blob_request(method, path='/', body=None, content_type=None):
    """Make a request to the Vercel Blob REST API."""
    url = f'{BLOB_URL}{path}'
    headers = {
        'Authorization': f'Bearer {BLOB_TOKEN}',
    }
    if content_type:
        headers['Content-Type'] = content_type

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
        log.error(f'Blob {method} {path} failed: {e.code} {body}')
        return None


def download_db(db_path):
    """Download the SQLite database from Vercel Blob."""
    if not BLOB_TOKEN:
        log.warning('BLOB_READ_WRITE_TOKEN not set, skipping blob download')
        return False

    # List blobs to find our database
    result = _blob_request('GET', '/')
    if not result:
        return False

    try:
        blobs = json.loads(result)
    except json.JSONDecodeError:
        return False

    # Find our database blob
    db_blob = None
    if isinstance(blobs, dict) and 'blobs' in blobs:
        for blob in blobs['blobs']:
            if blob.get('pathname') == BLOB_KEY:
                db_blob = blob
                break

    if not db_blob:
        log.info(f'No existing {BLOB_KEY} in Blob, starting fresh')
        return False

    download_url = db_blob.get('url')
    if not download_url:
        return False

    log.info(f'Downloading {BLOB_KEY} from Blob...')
    data = _blob_request('GET', download_url.replace(BLOB_URL, ''))
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
        return False

    if not os.path.exists(db_path):
        log.warning(f'{db_path} not found, skipping blob upload')
        return False

    # Make a backup copy first
    backup_path = db_path + '.blob_backup'
    shutil.copy2(db_path, backup_path)

    try:
        with open(backup_path, 'rb') as f:
            data = f.read()

        log.info(f'Uploading {BLOB_KEY} to Blob ({len(data)} bytes)...')

        # Vercel Blob put API
        put_path = f'/put/{BLOB_KEY}'
        result = _blob_request('PUT', put_path, body=data,
                               content_type='application/octet-stream')

        if result:
            log.info('Database uploaded to Blob successfully')
            # Clean up backup
            os.remove(backup_path)
            return True
        else:
            log.error('Failed to upload database to Blob')
            return False
    except Exception as e:
        log.error(f'Blob upload error: {e}')
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
