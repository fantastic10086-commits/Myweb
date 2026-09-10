"""
Flask PI Management System
Foreign Trade Proforma Invoice Generator
Run with: python app.py
"""

import os
import sys
import uuid
import zipfile
import shutil
import time
import threading
import sqlite3
import tempfile
import math
import json
import re
from io import BytesIO
from types import SimpleNamespace
from datetime import datetime, date, timedelta
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, send_file, jsonify, current_app, session, make_response,
    g, has_request_context, abort
)
from flask_wtf.csrf import CSRFProtect
from werkzeug.middleware.proxy_fix import ProxyFix
from sqlalchemy import event, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.engine import Engine
from sqlalchemy.orm import joinedload, selectinload
from sqlalchemy.orm.exc import StaleDataError
from models import (
    db, Customer, Product, PI, PIItem, Salesperson, User, Account,
    FieldOption, Payment, Expense, Supplier, Procurement, AuditLog,
    DocumentTemplate, PackingList, PackingBox, PackingItem,
)
from pdf_generator import generate_pi_pdf
from excel_generator import generate_pi_excel
from document_export import (
    PLACEHOLDER_GROUPS, TemplateError, apply_system_default_page_setup,
    convert_excel_to_pdf,
    create_placeholder_template,
    render_excel_template, validate_template,
)
from supplier_statement_pdf import generate_supplier_statement
from procurement_export import generate_supplier_purchase_order
from packing_list_export import (
    apply_packing_template_style,
    generate_compact_packing_list_pdf,
    generate_compact_packing_list_workbook,
    generate_packing_list_workbook,
)

# ── Configuration ────────────────────────────────────────────────────
# Detect the app root directory (where this file lives)
APP_ROOT = os.path.dirname(os.path.abspath(__file__))
SYSTEM_DEFAULT_TEMPLATE_FILENAME = 'system-default.xlsx'
SYSTEM_DEFAULT_TEMPLATE_SOURCE = os.path.join(
    APP_ROOT, 'assets', 'system_default_pi_template.xlsx'
)
QISUO_LEGACY_TEMPLATE_FILENAME = 'qisuo-legacy.xlsx'
QISUO_LEGACY_TEMPLATE_SOURCE = os.path.join(
    APP_ROOT, 'assets', 'qisuo_legacy_pi_template.xlsx'
)
PACKING_TEMPLATE_DEFINITIONS = {
    'packing-a4': ('标准完整装箱单', 'packing_a4.xlsx', 'packing_a4'),
    'packing-compact-100x150': (
        '精简 100×150 装箱单', 'packing_compact_100x150.xlsx', 'packing_compact'
    ),
}

# Sales-performance reporting deliberately uses a stable rate so changing the
# quotation/profit rate never rewrites a salesperson's historical performance.
PERFORMANCE_EXCHANGE_RATE = 7.0

MANAGED_FIELD_LABELS = {
    'shipping_note': '客户费用/折扣类型',
    'expense_category': '订单真实成本类别',
    'price_terms': '价格条款',
    'delivery_time': '交货期',
}
MANAGED_FIELDS_WITH_ENGLISH = {'shipping_note'}

import blob_sync

_LOGIN_ATTEMPTS = {}
_ACCOUNT_LOOKUPS = {}
_LOGIN_LOCK = threading.Lock()

@event.listens_for(Engine, 'connect')
def _set_sqlite_pragmas(dbapi_connection, connection_record):
    if dbapi_connection.__class__.__module__.startswith('sqlite3'):
        cursor = dbapi_connection.cursor()
        cursor.execute('PRAGMA foreign_keys=ON')
        cursor.execute('PRAGMA busy_timeout=30000')
        cursor.close()

def _migrate_db():
    """Auto-add missing columns to existing tables without data loss."""
    from sqlalchemy import inspect, text
    inspector = inspect(db.engine)
    pi_columns_before = (
        {c['name'] for c in inspector.get_columns('pis')}
        if inspector.has_table('pis') else set()
    )
    pi_exchange_rate_was_missing = 'exchange_rate' not in pi_columns_before
    expected = {
        'customers': {'salesperson': 'VARCHAR(100)', 'created_at': 'DATETIME', 'total_deal_usd': 'FLOAT', 'image': 'VARCHAR(500)', 'deleted_at': ('DATETIME', 'NULL'), 'version': ('INTEGER', '1')},
        'products': {
            'image': 'VARCHAR(500)',
            'chinese_name': 'VARCHAR(200)',
            'unit_price_rmb': 'FLOAT',
            'active': ('BOOLEAN', '1'),
        },
        'pis': {'salesperson': 'VARCHAR(100)', 'currency': 'VARCHAR(3)', 'exchange_rate': ('FLOAT', '7.0'), 'company': 'VARCHAR(50)', 'excel_path': 'VARCHAR(500)', 'paid': 'BOOLEAN', 'received_amount': 'FLOAT', 'shipping_address': 'TEXT', 'shipping_note_en': 'TEXT', 'price_terms': 'VARCHAR(200)', 'delivery_time': 'VARCHAR(200)', 'bank_beneficiary_name': 'VARCHAR(300)', 'bank_account_no': 'VARCHAR(100)', 'bank_country_region': 'VARCHAR(100)', 'bank_beneficiary_address': 'TEXT', 'bank_name': 'VARCHAR(200)', 'bank_address': 'TEXT', 'bank_swift_code': 'VARCHAR(50)', 'bank_code': 'VARCHAR(50)', 'bank_branch_code': 'VARCHAR(50)', 'bank_currency': 'VARCHAR(3)', 'actual_shipping_cost': 'FLOAT', 'procurement_confirmed': 'BOOLEAN', 'shipping_completed': ('BOOLEAN', '0'), 'shipping_date': ('DATE', 'NULL'), 'shipping_tracking_no': ('VARCHAR(200)', "''"), 'shipping_record_note': ('TEXT', "''"), 'shipping_recorded_at': ('DATETIME', 'NULL'), 'shipping_recorded_by': ('VARCHAR(100)', "''"), 'procurement_status': ('VARCHAR(20)', "'未回款'"), 'customs_required': ('BOOLEAN', 'NULL'), 'customs_note': ('TEXT', "''"), 'customs_recorded_at': ('DATETIME', 'NULL'), 'customs_recorded_by': ('VARCHAR(100)', "''"), 'deleted_at': ('DATETIME', 'NULL'), 'version': ('INTEGER', '1')},
        'salespersons': {'phone': 'VARCHAR(50)', 'email': 'VARCHAR(200)', 'dingtalk_user_id': 'VARCHAR(100)'},
        'payments': {
            'order_no': 'VARCHAR(200)',
            'order_no_normalized': 'VARCHAR(200)',
            'idempotency_key': 'VARCHAR(64)',
            'receiving_account_id': ('INTEGER', 'NULL'),
            'receiving_account_name': ('VARCHAR(200)', "''"),
            'receiving_account_currency': ('VARCHAR(3)', "''"),
            'attachment': ('VARCHAR(500)', "''"),
            'deleted_at': ('DATETIME', 'NULL'),
        },
        'expenses': {'attachment': 'VARCHAR(500)'},
        'accounts': {
            'country_region': 'VARCHAR(100)',
            'beneficiary_address': 'TEXT',
            'bank_address': 'TEXT',
            'bank_code': 'VARCHAR(50)',
            'branch_code': 'VARCHAR(50)',
        },
        'field_options': {'english_value': 'VARCHAR(200)'},
        'suppliers': {},  # table auto-created by create_all
        'procurements': {},  # table auto-created by create_all
        'packing_lists': {},  # tables auto-created by create_all
        'packing_boxes': {},
        'packing_items': {'note': 'VARCHAR(500)'},
        'users': {
            'account': ('VARCHAR(100)', "''"),
            'active': ('BOOLEAN', '1'),
            'must_change_password': ('BOOLEAN', '1'),
            'auth_version': ('INTEGER', '1'),
        },
    }
    for table, columns in expected.items():
        if not inspector.has_table(table): continue
        existing_cols = {c['name'] for c in inspector.get_columns(table)}
        for col_name, col_info in columns.items():
            if col_name not in existing_cols:
                # col_info can be a string (type only, DEFAULT '') or a tuple (type, default_sql)
                if isinstance(col_info, tuple):
                    col_type, col_default = col_info
                else:
                    col_type, col_default = col_info, "''"
                try:
                    db.session.execute(text(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_type} DEFAULT {col_default}"))
                    db.session.commit()
                except Exception:
                    db.session.rollback()
    if inspector.has_table('users'):
        # Keep every existing user able to sign in after introducing a
        # separate login account.  Existing usernames become the initial
        # account and administrators may change them later.
        db.session.execute(text("""
            UPDATE users
               SET account = username
             WHERE account IS NULL OR trim(account) = ''
        """))
        db.session.execute(text("""
            CREATE UNIQUE INDEX IF NOT EXISTS ux_users_account_nocase
            ON users(account COLLATE NOCASE)
        """))
        db.session.commit()
    # Earlier releases added nullable datetime columns with an empty-string
    # default. SQLAlchemy correctly expects either NULL or an ISO datetime, so
    # normalize the legacy empty values before ORM queries read them.
    for table in ('customers', 'pis', 'payments'):
        if inspector.has_table(table) and 'deleted_at' in {c['name'] for c in inspector.get_columns(table)}:
            db.session.execute(text(
                f"UPDATE {table} SET deleted_at = NULL "
                "WHERE deleted_at IS NOT NULL AND trim(CAST(deleted_at AS TEXT)) = ''"
            ))
    if inspector.has_table('pis'):
        # Existing PIs did not previously carry a rate.  Snapshot the current
        # system default once during migration, then only repair invalid rows.
        default_business_rate = _get_exchange_rate()
        if pi_exchange_rate_was_missing:
            db.session.execute(
                text("UPDATE pis SET exchange_rate = :rate"),
                {'rate': default_business_rate},
            )
        else:
            db.session.execute(text("""
                UPDATE pis
                   SET exchange_rate = :rate
                 WHERE exchange_rate IS NULL OR exchange_rate <= 0
            """), {'rate': default_business_rate})
        db.session.execute(text("""
            UPDATE pis
               SET shipping_completed = 1
             WHERE coalesce(received_amount, 0) > 0
               AND coalesce(procurement_confirmed, 0) = 1
               AND procurement_status IN ('已发货', '已完成', '发货完成')
        """))
        # Payment, procurement and shipment records are independent business
        # facts. Startup migrations must never silently roll back downstream
        # records because a payment changed or a legacy row is incomplete.
        db.session.execute(text("""
            UPDATE pis
               SET procurement_status = CASE
                   WHEN coalesce(shipping_completed, 0) = 1 AND coalesce(procurement_confirmed, 0) = 1 THEN '发货完成'
                   WHEN coalesce(procurement_confirmed, 0) = 1 THEN '采购完成'
                   WHEN procurement_status = '部分采购' THEN '部分采购'
                   ELSE '待采购'
               END
        """))
    db.session.commit()
    # Backfill normalized payment references before enforcing uniqueness.  The
    # production database was checked for duplicates before this migration.
    if inspector.has_table('payments'):
        db.session.execute(text("""
            UPDATE payments
               SET order_no_normalized = lower(replace(replace(replace(trim(order_no), ' ', ''), char(9), ''), char(10), ''))
             WHERE coalesce(order_no_normalized, '') = '' AND trim(coalesce(order_no, '')) <> ''
        """))
        db.session.execute(text("""
            CREATE UNIQUE INDEX IF NOT EXISTS ux_payments_order_no_active
            ON payments(order_no_normalized)
            WHERE deleted_at IS NULL AND order_no_normalized IS NOT NULL AND order_no_normalized <> ''
        """))
        db.session.execute(text("""
            CREATE UNIQUE INDEX IF NOT EXISTS ux_payments_idempotency_key
            ON payments(idempotency_key)
            WHERE idempotency_key IS NOT NULL AND idempotency_key <> ''
        """))
        db.session.commit()

    # Keep the stored customer total aligned with the current accounting rule:
    # every active payment contributes amount + fee, RMB is converted at the
    # fixed performance rate, and each PI contributes no more than its total.
    # Running this during migration also corrects historical partial payments
    # immediately after an upgrade without changing any payment or PI record.
    if all(inspector.has_table(table) for table in ('customers', 'pis', 'payments')):
        db.session.execute(text("""
            UPDATE customers
               SET total_deal_usd = round(coalesce((
                   SELECT sum(
                       CASE WHEN upper(coalesce(pi.currency, 'USD')) = 'RMB'
                            THEN min(
                                max(coalesce(payment_totals.received_with_fee, 0), 0),
                                max(coalesce(pi.total_amount, 0) + coalesce(pi.shipping_cost, 0), 0)
                            ) / :performance_rate
                            ELSE min(
                                max(coalesce(payment_totals.received_with_fee, 0), 0),
                                max(coalesce(pi.total_amount, 0) + coalesce(pi.shipping_cost, 0), 0)
                            )
                       END
                   )
                     FROM pis AS pi
                     JOIN (
                         SELECT pi_id, sum(coalesce(amount, 0) + coalesce(fee, 0)) AS received_with_fee
                           FROM payments
                          WHERE deleted_at IS NULL
                          GROUP BY pi_id
                     ) AS payment_totals ON payment_totals.pi_id = pi.id
                    WHERE pi.customer_id = customers.id
                      AND pi.deleted_at IS NULL
               ), 0), 2)
        """), {'performance_rate': PERFORMANCE_EXCHANGE_RATE})
        db.session.commit()


# Company info — edit these to match your business
COMPANY_CONFIG = {
    'name': 'CHANGZHOU KLISTA INTERNATIONAL TRADE CO., LTD.',
    'address': 'No. 158 Jinchuang Road, Yaoguan Town, Changzhou City, China',
    'phone': '+86 17712333882',
    'email': 'fantastic10086@gmail.com',
    'dingtalk_webhook': '',  # DingTalk robot webhook URL
}


SETTINGS_FILE = os.environ.get('SETTINGS_FILE', os.path.join(APP_ROOT, 'settings.json'))

def _load_settings():
    import json as _json
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, 'r') as f:
                return _json.load(f)
        except Exception:
            pass
    return {}

def _save_settings(data):
    import json as _json
    settings_dir = os.path.dirname(SETTINGS_FILE) or '.'
    os.makedirs(settings_dir, exist_ok=True)
    # Atomic replacement prevents a crash during save from leaving a truncated
    # credentials file.  Restrictive permissions keep service secrets private.
    fd, tmp_path = tempfile.mkstemp(prefix='.settings-', dir=settings_dir, text=True)
    try:
        with os.fdopen(fd, 'w') as f:
            _json.dump(data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp_path, 0o600)
        os.replace(tmp_path, SETTINGS_FILE)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

def _get_exchange_rate():
    """Return the validated default business rate for newly created PIs."""
    try:
        rate = float(_load_settings().get('exchange_rate', '7.0') or '7.0')
    except (TypeError, ValueError):
        return 7.0
    return rate if math.isfinite(rate) and rate > 0 else 7.0


def _pi_exchange_rate(pi):
    """Return the immutable-per-PI USD→RMB rate, with a safe legacy fallback."""
    try:
        rate = float(getattr(pi, 'exchange_rate', None))
    except (TypeError, ValueError):
        rate = 0
    return rate if math.isfinite(rate) and rate > 0 else PERFORMANCE_EXCHANGE_RATE

def _setting_enabled(settings, key, default=True):
    """Read a persisted on/off setting while keeping legacy installs enabled."""
    value = settings.get(key)
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {'1', 'true', 'yes', 'on'}


def _get_webhook(settings=None):
    """Get DingTalk webhook URL from settings file or env."""
    settings = settings if settings is not None else _load_settings()
    return settings.get('dingtalk_webhook', COMPANY_CONFIG.get('dingtalk_webhook', '')).strip()


def _dingtalk_report_webhook(salesperson_name, settings=None):
    """Choose the report group; Shu Kei has an optional dedicated robot."""
    settings = settings if settings is not None else _load_settings()
    if not _setting_enabled(settings, 'dingtalk_report_enabled'):
        return ''
    default_webhook = _get_webhook(settings)
    normalized_name = ''.join((salesperson_name or '').casefold().split())
    if normalized_name == 'shukei':
        return (settings.get('dingtalk_shu_kei_webhook', '') or '').strip() or default_webhook
    return default_webhook


def _send_dingtalk(title, text, webhook=None):
    """Send a markdown message to DingTalk via webhook."""
    import json as _json
    from urllib import request as _req
    if webhook is None:
        webhook = _get_webhook()
    if not webhook:
        return False
    payload = _json.dumps({
        'msgtype': 'markdown',
        'markdown': {'title': title, 'text': text},
    }).encode('utf-8')
    try:
        # Verify DingTalk's TLS certificate using the system CA store.
        import ssl as _ssl
        ctx = _ssl.create_default_context()
        _req.urlopen(_req.Request(webhook, data=payload, headers={'Content-Type': 'application/json'}), timeout=10, context=ctx)
        return True
    except Exception:
        return False


_DT_CACHE = {'token': '', 'expires': 0, 'unionid': {}}

def _dingtalk_token():
    """Get DingTalk access_token using AppKey/AppSecret."""
    import json as _json, time as _time
    from urllib import request as _req
    settings = _load_settings()
    appkey = settings.get('dingtalk_appkey', '')
    appsecret = settings.get('dingtalk_appsecret', '')
    if not appkey or not appsecret:
        return ''
    now = _time.time()
    if _DT_CACHE['token'] and _DT_CACHE['expires'] > now:
        return _DT_CACHE['token']
    try:
        import ssl as _ssl
        ctx = _ssl.create_default_context()
        url = f'https://oapi.dingtalk.com/gettoken?appkey={appkey}&appsecret={appsecret}'
        resp = _req.urlopen(_req.Request(url), timeout=10, context=ctx)
        data = _json.loads(resp.read().decode('utf-8'))
        if data.get('errcode') == 0:
            _DT_CACHE['token'] = data['access_token']
            _DT_CACHE['expires'] = now + data.get('expires_in', 7200) - 300
            return _DT_CACHE['token']
    except Exception:
        pass
    return ''


def _dingtalk_userid_to_unionid(user_id):
    """Convert DingTalk userid to unionid using the user/get API."""
    import json as _json
    from urllib import request as _req
    import ssl as _ssl

    # Check cache
    cached = _DT_CACHE['unionid'].get(user_id)
    if cached:
        return cached

    token = _dingtalk_token()
    if not token or not user_id:
        return ''

    try:
        ctx = _ssl.create_default_context()
        url = f'https://oapi.dingtalk.com/user/get?access_token={token}&userid={user_id}'
        resp = _req.urlopen(_req.Request(url), timeout=10, context=ctx)
        data = _json.loads(resp.read().decode('utf-8'))
        if data.get('errcode') == 0:
            unionid = data.get('unionid', '')
            if unionid:
                _DT_CACHE['unionid'][user_id] = unionid
                return unionid
    except Exception:
        pass
    return ''


def _dingtalk_create_task(executor_user_ids, subject, description):
    """Create a DingTalk task (待办).

    executor_user_ids: list of DingTalk userids. First one used as creator.
    The function auto-converts userid → unionid internally.
    """
    import json as _json, time as _time
    from urllib import request as _req

    if not executor_user_ids:
        return ''

    # Convert all userids to unionids (dedup, keep order)
    union_ids = []
    seen = set()
    for uid in executor_user_ids:
        if not uid:
            continue
        u = _dingtalk_userid_to_unionid(uid)
        if u and u not in seen:
            union_ids.append(u)
            seen.add(u)
    if not union_ids:
        return ''

    token = _dingtalk_token()
    if not token:
        return ''

    payload = {
        'sourceId': f'pi_manager_{int(_time.time() * 1000)}',
        'subject': subject[:200],
        'description': description[:4000],
        'creatorId': union_ids[0],
        'executorIds': union_ids,
    }

    try:
        import ssl as _ssl
        ctx = _ssl.create_default_context()
        url = f'https://api.dingtalk.com/v1.0/todo/users/{union_ids[0]}/tasks?operatorId={union_ids[0]}'
        data = _json.dumps(payload).encode('utf-8')
        req = _req.Request(url, data=data, method='POST')
        req.add_header('Content-Type', 'application/json')
        req.add_header('x-acs-dingtalk-access-token', token)
        resp = _req.urlopen(req, timeout=15, context=ctx)
        result = _json.loads(resp.read().decode('utf-8'))
        if result.get('id'):
            return result['id']
    except Exception:
        pass
    return ''


def _dingtalk_send_notification(user_ids, title, text):
    """Send a work notification (工作通知) to DingTalk users via the enterprise app.

    user_ids: single user_id string or list of user_id strings.
    """
    import json as _json
    from urllib import request as _req
    import ssl as _ssl

    settings = _load_settings()
    agent_id = settings.get('dingtalk_agent_id', '').strip()
    if not agent_id or not user_ids:
        return False

    # Support both single user_id and list of user_ids
    if isinstance(user_ids, list):
        user_id_str = ','.join([u for u in user_ids if u])
    else:
        user_id_str = user_ids
    if not user_id_str:
        return False

    token = _dingtalk_token()
    if not token:
        return False

    payload = {
        'agent_id': agent_id,
        'userid_list': user_id_str,
        'msg': {
            'msgtype': 'markdown',
            'markdown': {
                'title': title[:50],
                'text': text[:4000],
            }
        }
    }

    try:
        ctx = _ssl.create_default_context()
        url = 'https://oapi.dingtalk.com/topapi/message/corpconversation/asyncsend_v2?access_token=' + token
        data = _json.dumps(payload).encode('utf-8')
        req = _req.Request(url, data=data, method='POST')
        req.add_header('Content-Type', 'application/json')
        resp = _req.urlopen(req, timeout=15, context=ctx)
        result = _json.loads(resp.read().decode('utf-8'))
        return result.get('errcode') == 0
    except Exception:
        pass
    return False


def _dingtalk_send_file(user_ids, filepath):
    """Upload and send a file (PDF) to DingTalk users via work notification.

    user_ids: single user_id string or list of user_id strings.
    filepath: absolute path to the file to send.
    """
    import json as _json
    from urllib import request as _req
    import ssl as _ssl

    if not user_ids or not filepath or not os.path.exists(filepath):
        return False

    settings = _load_settings()
    agent_id = settings.get('dingtalk_agent_id', '').strip()
    if not agent_id:
        return False

    token = _dingtalk_token()
    if not token:
        return False

    # Upload the file to DingTalk media
    media_id = _dingtalk_upload_media(token, filepath)
    if not media_id:
        return False

    # Re-fetch token (upload may have refreshed it)
    token = _dingtalk_token()
    if not token:
        return False

    # Support both single user_id and list
    if isinstance(user_ids, list):
        user_id_str = ','.join([u for u in user_ids if u])
    else:
        user_id_str = user_ids
    if not user_id_str:
        return False

    try:
        ctx = _ssl.create_default_context()
        url = 'https://oapi.dingtalk.com/topapi/message/corpconversation/asyncsend_v2?access_token=' + token
        payload = {
            'agent_id': agent_id,
            'userid_list': user_id_str,
            'msg': {
                'msgtype': 'file',
                'file': {'media_id': media_id}
            }
        }
        data = _json.dumps(payload).encode('utf-8')
        req = _req.Request(url, data=data, method='POST')
        req.add_header('Content-Type', 'application/json')
        resp = _req.urlopen(req, timeout=15, context=ctx)
        result = _json.loads(resp.read().decode('utf-8'))
        return result.get('errcode') == 0
    except Exception:
        pass
    return False


def _dingtalk_upload_media(token, filepath):
    """Upload a file to DingTalk, return media_id."""
    import json as _json
    from urllib import request as _req

    import ssl as _ssl
    ctx = _ssl.create_default_context()

    # Read file directly since we know it's a PDF
    try:
        with open(filepath, 'rb') as f:
            file_data = f.read()
    except Exception:
        return ''

    boundary = '----FormBoundary7MA4YWxk'
    body = []
    body.append('--' + boundary)
    body.append('Content-Disposition: form-data; name="media"; filename="pi.pdf"')
    body.append('Content-Type: application/pdf')
    body.append('')
    # Add bytes
    body_bytes = []
    for line in body:
        body_bytes.append(line.encode('utf-8'))
    body_bytes.append(file_data)
    body_bytes.append(('--' + boundary + '--').encode('utf-8'))
    full_body = b'\r\n'.join(body_bytes)

    url = f'https://oapi.dingtalk.com/media/upload?access_token={token}&type=file'
    req = _req.Request(url, data=full_body)
    req.add_header('Content-Type', 'multipart/form-data; boundary=' + boundary)
    try:
        resp = _req.urlopen(req, timeout=30, context=ctx)
        result = _json.loads(resp.read().decode('utf-8'))
        if result.get('errcode') == 0:
            return result.get('media_id', '')
    except Exception:
        pass
    return ''


def _seed_products_from_csv():
    """Seed products from bundled CSV files on first startup."""
    import csv, re
    for fname in ['产品信息202606111_1.csv', '产品信息202606111_2.csv', '产品信息202606111_3.csv']:
        csv_path = os.path.join(APP_ROOT, fname)
        if not os.path.exists(csv_path):
            continue
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            next(reader)
            for row in reader:
                try:
                    name = (row[0] or '').strip().replace('\n', ' ').replace('\r', '')[:200]
                    if not name: continue
                    code = (row[1] or '').strip()[:100]
                    spec = (row[2] or '').strip()[:200]
                    price_str = (row[5] or '').strip()
                    price = 0.0
                    if price_str:
                        nums = re.findall(r'[\d.]+', price_str.replace(',', ''))
                        if nums:
                            try: price = float(nums[0])
                            except: pass
                    db.session.add(Product(name=name, product_code=code, specification=spec, unit_price=price))
                except Exception:
                    pass
    db.session.commit()


def _seed_customers_from_csv():
    """Seed customers from bundled CSV file on first startup."""
    import csv
    csv_path = os.path.join(APP_ROOT, 'CUSTOMER_EXPORT_56677547_1_1781157273.csv')
    if not os.path.exists(csv_path):
        return
    count = 0
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        next(reader)
        for row in reader:
            try:
                name = (row[0] or '').strip()
                if not name or name.startswith('NA_') or name.startswith('nocompany_'):
                    contact = (row[3] or '').strip()
                    name = contact if (contact and not contact.startswith('NA_')) else f'Customer_{row[2]}'
                contact_person = (row[3] or '').strip()[:100]
                email = (row[4] or '').strip() if len(row) > 4 else ''
                salesperson = (row[5] or '').strip() if len(row) > 5 else ''
                country = (row[6] or '').strip() if len(row) > 6 else ''
                address = (row[7] or '').strip() if len(row) > 7 else ''
                phone_raw = (row[9] or '').strip() if len(row) > 9 else ''
                phone = ''
                if phone_raw:
                    for p in phone_raw.replace("'", '').split(';'):
                        p = p.strip().strip('"+').strip()
                        if p and any(c.isdigit() for c in p):
                            phone = p[:50]; break
                deal_str = row[-1].strip() if row[-1] else '0'
                try:
                    total_deal = float(deal_str) if deal_str else 0.0
                except ValueError:
                    total_deal = 0.0
                name = name.replace('&amp;', '&')[:200]
                db.session.add(Customer(
                    name=name, country=country, contact_person=contact_person,
                    email=email, phone=phone, address=address,
                    salesperson=salesperson, total_deal_usd=total_deal,
                ))
                count += 1
                if count % 500 == 0: db.session.commit()
            except Exception:
                pass
    db.session.commit()


def _ensure_system_default_template(app_instance):
    """Install or migrate the protected system template to editable Excel."""
    template = DocumentTemplate.query.filter_by(code='system-default').first()
    template_dir = app_instance.config['DOCUMENT_TEMPLATE_DIR']
    current_path = ''
    if template and template.template_type == 'xlsx' and template.filename:
        filename = os.path.basename(template.filename)
        if filename == template.filename:
            current_path = os.path.join(template_dir, filename)

    # Preserve an administrator-replaced source file across every restart.
    # The built-in filename itself is safe to refresh during an application
    # upgrade so newly supported placeholders become available in production.
    if current_path and os.path.isfile(current_path):
        if os.path.basename(current_path) == SYSTEM_DEFAULT_TEMPLATE_FILENAME:
            if not os.path.isfile(SYSTEM_DEFAULT_TEMPLATE_SOURCE):
                raise RuntimeError('Built-in system default Excel template is missing.')
            validate_template(SYSTEM_DEFAULT_TEMPLATE_SOURCE)
            shutil.copy2(SYSTEM_DEFAULT_TEMPLATE_SOURCE, current_path)
            validate_template(current_path)
        template.active = True
        db.session.commit()
        return template

    if not os.path.isfile(SYSTEM_DEFAULT_TEMPLATE_SOURCE):
        raise RuntimeError('Built-in system default Excel template is missing.')
    validate_template(SYSTEM_DEFAULT_TEMPLATE_SOURCE)

    installed_path = os.path.join(template_dir, SYSTEM_DEFAULT_TEMPLATE_FILENAME)
    if not os.path.isfile(installed_path):
        shutil.copy2(SYSTEM_DEFAULT_TEMPLATE_SOURCE, installed_path)
    validate_template(installed_path)

    if not template:
        template = DocumentTemplate(
            name='系统默认 PI 模板',
            code='system-default',
            template_type='xlsx',
            filename=SYSTEM_DEFAULT_TEMPLATE_FILENAME,
            active=True,
            is_default=DocumentTemplate.query.filter_by(is_default=True).count() == 0,
            notes='与系统默认 PDF 同版式，可下载编辑后替换。',
            created_by='system',
        )
        db.session.add(template)
    else:
        template.template_type = 'xlsx'
        template.filename = SYSTEM_DEFAULT_TEMPLATE_FILENAME
        template.active = True
        if not template.notes or '无需上传' in template.notes:
            template.notes = '与系统默认 PDF 同版式，可下载编辑后替换。'
    db.session.commit()
    return template


def _ensure_qisuo_legacy_template(app_instance):
    """Install the optional QISUO legacy layout without changing the default."""
    if not os.path.isfile(QISUO_LEGACY_TEMPLATE_SOURCE):
        return None
    validate_template(QISUO_LEGACY_TEMPLATE_SOURCE)
    template = DocumentTemplate.query.filter_by(code='qisuo-legacy').first()
    template_dir = app_instance.config['DOCUMENT_TEMPLATE_DIR']
    current_path = ''
    if template and template.template_type == 'xlsx' and template.filename:
        filename = os.path.basename(template.filename)
        if filename == template.filename:
            current_path = os.path.join(template_dir, filename)

    # An administrator may replace this template later.  Keep that uploaded
    # copy. Refresh only the known built-in filename during upgrades.
    if current_path and os.path.isfile(current_path):
        if os.path.basename(current_path) == QISUO_LEGACY_TEMPLATE_FILENAME:
            shutil.copy2(QISUO_LEGACY_TEMPLATE_SOURCE, current_path)
            validate_template(current_path)
        template.active = True
        template.is_default = False
        db.session.commit()
        return template

    if not current_path or not os.path.isfile(current_path):
        installed_path = os.path.join(template_dir, QISUO_LEGACY_TEMPLATE_FILENAME)
        if not os.path.isfile(installed_path):
            shutil.copy2(QISUO_LEGACY_TEMPLATE_SOURCE, installed_path)
        validate_template(installed_path)
        if not template:
            template = DocumentTemplate(
                name='QISUO 旧版格式',
                code='qisuo-legacy',
                template_type='xlsx',
                filename=QISUO_LEGACY_TEMPLATE_FILENAME,
                active=True,
                is_default=False,
                notes='QISUO 旧版 Excel 单据，可下载编辑后替换。',
                created_by='system',
            )
            db.session.add(template)
        else:
            template.template_type = 'xlsx'
            template.filename = QISUO_LEGACY_TEMPLATE_FILENAME
            template.active = True
            template.is_default = False
    db.session.commit()
    return template


def _validate_packing_template(path, compact=False):
    """Validate a packing master without accepting macros or arbitrary files."""
    from openpyxl import load_workbook
    try:
        workbook = load_workbook(path, read_only=True, data_only=False)
        sheet = workbook.active
        if compact and (sheet.max_column < 6 or sheet.max_row < 11):
            raise TemplateError('100×150 装箱单模板结构不完整。')
        if not compact and (sheet.max_column < 14 or sheet.max_row < 12):
            raise TemplateError('标准装箱单模板结构不完整。')
        workbook.close()
    except TemplateError:
        raise
    except Exception as exc:
        raise TemplateError(f'无法读取装箱单模板：{exc}') from exc


def _ensure_packing_templates(app_instance):
    """Install editable packing masters while preserving admin replacements."""
    template_dir = app_instance.config['DOCUMENT_TEMPLATE_DIR']
    for code, (name, asset_name, template_type) in PACKING_TEMPLATE_DEFINITIONS.items():
        source_path = os.path.join(APP_ROOT, 'assets', asset_name)
        if not os.path.isfile(source_path):
            raise RuntimeError(f'Built-in packing template is missing: {asset_name}')
        compact = template_type == 'packing_compact'
        _validate_packing_template(source_path, compact)
        template = DocumentTemplate.query.filter_by(code=code).first()
        if template and template.filename:
            current_path = os.path.join(template_dir, os.path.basename(template.filename))
            # Uploaded UUID filenames are administrator replacements and survive upgrades.
            if os.path.isfile(current_path) and template.filename != asset_name:
                continue
        installed_path = os.path.join(template_dir, asset_name)
        shutil.copy2(source_path, installed_path)
        if not template:
            template = DocumentTemplate(code=code, name=name, created_by='system')
            db.session.add(template)
        template.template_type = template_type
        template.filename = asset_name
        template.active = True
        template.is_default = False
        template.notes = (
            '每箱一页，白底黑字，显示 PI、业务员、品名、规格和尺寸重量。'
            if compact else '完整字段版式，适合归档和常规打印。'
        )
    db.session.commit()


def create_app():
    app = Flask(__name__)
    secret_key = os.environ.get('SECRET_KEY', '').strip()
    if secret_key == 'replace-with-a-long-random-value':
        secret_key = ''
    if not secret_key:
        if os.environ.get('FLASK_ENV') == 'production':
            raise RuntimeError('SECRET_KEY must be set in production')
        secret_key = 'development-only-change-before-production'
    app.config['SECRET_KEY'] = secret_key
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE='Lax',
        SESSION_COOKIE_SECURE=os.environ.get('SESSION_COOKIE_SECURE', '0') == '1',
        PERMANENT_SESSION_LIFETIME=timedelta(hours=12),
        WTF_CSRF_TIME_LIMIT=12 * 60 * 60,
    )
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
    CSRFProtect(app)

    # Database — use env var DATABASE_DIR for Vercel, default to instance/
    db_dir = os.environ.get('DATABASE_DIR', os.path.join(APP_ROOT, 'instance'))
    db_path = os.path.join(db_dir, 'pi_manager.db')
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {'connect_args': {'timeout': 30}}
    app.config['TEMPLATES_AUTO_RELOAD'] = os.environ.get('FLASK_ENV') != 'production'

    # PDF output directory — use env var PDF_DIR for Vercel
    pdf_dir = os.environ.get('PDF_DIR', os.path.join(APP_ROOT, 'pdf'))
    app.config['PDF_DIR'] = pdf_dir
    upload_dir = os.environ.get('UPLOAD_DIR', os.path.join(APP_ROOT, 'static', 'uploads'))
    app.config['UPLOAD_DIR'] = upload_dir
    document_template_dir = os.path.join(upload_dir, 'document_templates')
    app.config['DOCUMENT_TEMPLATE_DIR'] = document_template_dir
    backup_dir = os.environ.get('BACKUP_DIR', os.path.join(APP_ROOT, 'backups'))
    app.config['BACKUP_DIR'] = backup_dir
    app.config['MAX_CONTENT_LENGTH'] = int(os.environ.get('MAX_UPLOAD_MB', '32')) * 1024 * 1024
    os.makedirs(pdf_dir, exist_ok=True)
    os.makedirs(upload_dir, exist_ok=True)
    os.makedirs(document_template_dir, exist_ok=True)
    os.makedirs(backup_dir, exist_ok=True)
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    # Restore database from Vercel Blob if available
    blob_sync.init_db(db_path)

    db.init_app(app)

    with app.app_context():
        with db.engine.connect() as connection:
            connection.exec_driver_sql('PRAGMA journal_mode=WAL')
        db.create_all()
        _migrate_db()

        # The built-in design is a real editable Excel source.  Excel download
        # and PDF conversion both use this same file, so their layouts match.
        _ensure_system_default_template(app)
        _ensure_qisuo_legacy_template(app)
        _ensure_packing_templates(app)

        # Seed default salespersons
        default_sp = [
            ('Shu Kei', '+86 17712333882', 'fantastic10086@gmail.com', '01075605503423165909'),
            ('Limon', '+86 15301506008', 'limon@qisuowelding.com', '0302320103321509442'),
            ('Kristi', '+86 18112500618', 'kristi@qisuowelding.com', '03236802374626412929'),
            ('Lu Yan', '+86 18019696608', 'luyan@qisuowelding.com', '0354364226451227898'),
            ('Yuna', '', '', ''),
            ('Delia', '', '', ''),
            ('Bai.', '', '', ''),
            ('Ma jilan', '', '', '036944123839016306'),
            ('QinQin', '18118336008', '', '2248391749772992006'),
        ]
        for name, phone, email, dt_uid in default_sp:
            if not Salesperson.query.filter_by(name=name).first():
                db.session.add(Salesperson(name=name, phone=phone, email=email, dingtalk_user_id=dt_uid))
        db.session.commit()

        # Seed default accounts (by name, won't overwrite existing)
        default_accounts = [
            ('克利斯达-农行', 'CHANGZHOU KLISTA INTERNATIONAL TRADE CO.LTD', 'AGRICULTURAL BANK OF CHINA H.O.BEIJING', '10618114040004700', 'ABOCCNBJ', 'klista', 'USD'),
            ('QISUO-花旗', 'Changzhou Q1 Suo Welding And Cutting Equipment Co., Ltd.', 'CITIBANK N. A. HONG KONG BRANCH', '39740000004173', 'CITIHKHXXXX', 'qisuo', 'USD'),
            ('姜舒棋的支付宝', 'CHANGZHOU KLISTA INTERNATIONAL TRADE CO.LTD', 'Alipay', '17712333882', '', 'klista', 'RMB'),
            ('姜舒棋的微信', 'CHANGZHOU KLISTA INTERNATIONAL TRADE CO.LTD', 'Wechat', '17712333882', '', 'klista', 'RMB'),
            ('戚所-阿里链接', 'Changzhou Q1 Suo Welding And Cutting Equipment Co., Ltd.', 'Alibaba', '', '', 'qisuo', 'USD'),
            ('克利斯达-阿里链接', 'CHANGZHOU KLISTA INTERNATIONAL TRADE CO.LTD', 'Alibaba', '', '', 'klista', 'USD'),
        ]
        for name, co_name, bank_name, acct_no, swift, brand, currency in default_accounts:
            if not Account.query.filter_by(name=name).first():
                db.session.add(Account(name=name, company_name=co_name, bank_name=bank_name, account_no=acct_no, swift_code=swift, brand=brand, currency=currency))
        db.session.commit()

        # Customer-facing PI adjustments and internal order costs are two
        # independent concepts.  A PI adjustment changes the amount charged to
        # the customer and therefore needs an English label for exported
        # documents.  An expense is an internal cost and only affects profit.
        default_shipping_notes = [
            ('运费', 'Freight'),
            ('国际运费', 'International Freight'),
            ('国内运费', 'Domestic Freight'),
            ('折扣', 'Discount'),
            ('样品费', 'Sample Fee'),
            ('手续费', 'Handling Fee'),
            ('其他调整', 'Other Adjustment'),
        ]
        legacy_shipping_notes = [
            row[0].strip() for row in
            db.session.query(PI.shipping_note).filter(
                PI.shipping_note.isnot(None), PI.shipping_note != ''
            ).distinct().all()
            if row[0] and row[0].strip()
        ]
        shipping_note_english = dict(default_shipping_notes)
        shipping_note_values = [value for value, _english in default_shipping_notes]
        for position, value in enumerate(shipping_note_values + legacy_shipping_notes, 1):
            option = FieldOption.query.filter_by(
                field_key='shipping_note', value=value
            ).first()
            if not option:
                option = FieldOption(
                    field_key='shipping_note', value=value,
                    english_value=shipping_note_english.get(value, value),
                    sort_order=position * 10,
                )
                db.session.add(option)
            elif not (option.english_value or '').strip():
                option.english_value = shipping_note_english.get(value, value)

        default_expense_categories = [
            '实际运费', '报关费', '保险费', '平台服务费',
            '仓储费', '检验费', '其他成本',
        ]
        legacy_expense_categories = [
            row[0].strip() for row in
            db.session.query(Expense.category).filter(
                Expense.category.isnot(None), Expense.category != ''
            ).distinct().all()
            if row[0] and row[0].strip()
        ]
        for position, value in enumerate(
            default_expense_categories + legacy_expense_categories, 1
        ):
            if not FieldOption.query.filter_by(
                field_key='expense_category', value=value
            ).first():
                db.session.add(FieldOption(
                    field_key='expense_category', value=value,
                    sort_order=position * 10,
                ))

        default_price_terms = [
            'EXW Changzhou', 'FOB Shanghai', 'CFR', 'CIF', 'DAP', 'DDP',
        ]
        default_delivery_times = [
            '7-15 days after receipt of payment',
            '15-20 days after receipt of payment',
            '20-30 days after receipt of payment',
        ]
        for field_key, values in (
            ('price_terms', default_price_terms),
            ('delivery_time', default_delivery_times),
        ):
            for position, value in enumerate(values, 1):
                if not FieldOption.query.filter_by(
                    field_key=field_key, value=value
                ).first():
                    db.session.add(FieldOption(
                        field_key=field_key, value=value,
                        sort_order=position * 10,
                    ))
        db.session.commit()

        # Store the English label on each PI as a historical snapshot.  Editing
        # a field option later must not silently change an issued document.
        english_by_value = {
            option.value: (option.english_value or option.value)
            for option in FieldOption.query.filter_by(
                field_key='shipping_note'
            ).all()
        }
        for pi in PI.query.filter(
            PI.shipping_note.isnot(None), PI.shipping_note != '',
            (PI.shipping_note_en.is_(None)) | (PI.shipping_note_en == ''),
        ).all():
            pi.shipping_note_en = english_by_value.get(pi.shipping_note, pi.shipping_note)
        db.session.commit()

        # Seed default customers from CSV (only if empty)
        if Customer.query.count() == 0:
            _seed_customers_from_csv()

        # Seed default products from CSV (only if empty)
        if Product.query.count() == 0:
            _seed_products_from_csv()

        # Never create accounts with a known default password.
        default_users = []
        if User.query.count() == 0:
            initial_password = os.environ.get('INITIAL_ADMIN_PASSWORD', '').strip()
            if len(initial_password) < 10:
                raise RuntimeError('INITIAL_ADMIN_PASSWORD (10+ characters) is required for an empty database')
            default_users.append(('admin', 'admin', initial_password, 'admin', ''))
        for account, uname, pwd, role, sp in default_users:
            if not User.query.filter_by(account=account).first():
                db.session.add(User(
                    account=account,
                    username=uname,
                    password_hash=generate_password_hash(pwd),
                    role=role,
                    salesperson_name=sp,
                    must_change_password=True,
                ))
        db.session.commit()

    @event.listens_for(db.session, 'after_commit')
    def _mark_db_dirty_after_commit(session_):
        if has_request_context():
            g.db_dirty = True

    # Auto-sync database to Vercel Blob after write requests
    @app.after_request
    def _sync_to_blob(response):
        blob_enabled = bool(os.environ.get('BLOB_READ_WRITE_TOKEN', '').strip())
        if blob_enabled and getattr(g, 'db_dirty', False) and 200 <= response.status_code < 400:
            db_path = os.environ.get('DATABASE_DIR', os.path.join(APP_ROOT, 'instance'))
            db_path = os.path.join(db_path, 'pi_manager.db')
            if not blob_sync.sync_db(db_path):
                error = blob_sync.get_last_error()
                current_app.logger.error('Database changed but Blob sync failed: %s', error)
                message = 'Database saved locally, but cloud persistence failed.'
                if error:
                    message = f'{message} {error}'
                flash(message, 'danger')
        return response

    @app.after_request
    def _security_headers(response):
        response.headers.setdefault('X-Content-Type-Options', 'nosniff')
        response.headers.setdefault('X-Frame-Options', 'DENY')
        response.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
        response.headers.setdefault('Permissions-Policy', 'camera=(), microphone=(), geolocation=()')
        # Cache application assets and derived product thumbnails in the
        # browser.  They contain no customer or financial data and their URLs
        # are stable, so forcing them through the server on every page made the
        # authenticated application unnecessarily slow.
        if request.endpoint == 'static':
            response.headers['Cache-Control'] = 'public, max-age=3600, must-revalidate'
            response.headers.pop('Pragma', None)
            response.headers.pop('Expires', None)
        elif request.endpoint == 'uploaded_product_thumbnail':
            response.headers['Cache-Control'] = 'private, max-age=604800, immutable'
            response.headers.pop('Pragma', None)
            response.headers.pop('Expires', None)
            response.vary.add('Cookie')
        # Business pages, JSON responses, original uploads and generated files
        # can contain customer and financial data.  Keep those out of caches.
        elif session.get('user_id'):
            response.headers['Cache-Control'] = 'private, no-store, max-age=0, must-revalidate'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
        if request.is_secure:
            response.headers.setdefault('Strict-Transport-Security', 'max-age=31536000; includeSubDomains')
        return response

    return app


app = create_app()

@app.errorhandler(StaleDataError)
def handle_stale_data(_error):
    db.session.rollback()
    flash('其他用户已先保存该记录，系统已阻止旧页面覆盖新数据。', 'warning')
    return redirect(request.referrer or url_for('index'))

@app.before_request
def enforce_password_change():
    if 'user_id' not in session:
        return None
    user = get_current_user()
    if not user or not user.active or session.get('auth_version') != user.auth_version:
        session.clear()
        return redirect(url_for('login'))
    if request.endpoint in {'profile', 'logout', 'static'}:
        return None
    if user and user.must_change_password:
        flash('请先修改临时密码后再继续使用。', 'warning')
        return redirect(url_for('profile'))
    return None


# ── Helper ─────────────────────────────────────────────────────────────
def _generate_pi_number():
    """Generate sequential PI number: PI-YYYYMMDD-NNN"""
    today = date.today()
    prefix = f"PI-{today.strftime('%Y%m%d')}-"
    # Find the max existing number instead of just counting (handles gaps from deletions)
    last = PI.query.filter(PI.pi_number.like(f'{prefix}%')).order_by(PI.pi_number.desc()).first()
    if last and last.pi_number.startswith(prefix):
        try:
            num = int(last.pi_number[len(prefix):]) + 1
        except ValueError:
            num = 1
    else:
        num = 1
    return f"{prefix}{num:03d}"

def _nonnegative_float(value, field_name):
    try:
        number = float(str(value or '0').strip() or '0')
    except (TypeError, ValueError):
        raise ValueError(f'{field_name}必须是有效数字。')
    if not math.isfinite(number) or number < 0:
        raise ValueError(f'{field_name}不能为负数或无效值。')
    return number

def _signed_float(value, field_name):
    """Parse a finite signed amount; negative adjustments represent discounts."""
    try:
        number = float(str(value or '0').strip() or '0')
    except (TypeError, ValueError):
        raise ValueError(f'{field_name}必须是有效数字。')
    if not math.isfinite(number):
        raise ValueError(f'{field_name}必须是有效数字。')
    return number

def _positive_int(value, field_name):
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        raise ValueError(f'{field_name}必须是整数。')
    if number <= 0:
        raise ValueError(f'{field_name}必须大于 0。')
    return number

def _submitted_pi_items(form, allow_inactive_ids=None):
    """Load selected products in the explicit order maintained by the UI."""
    allow_inactive_ids = set(allow_inactive_ids or ())
    product_ids = []
    seen = set()

    # Numeric object keys in JavaScript are enumerated by numeric value, not by
    # click order.  The PI forms therefore submit a separate ordered id list.
    # Keep the selected_* fallback for old clients and saved browser pages.
    raw_order = str(form.get('product_order', '') or '').strip()
    if raw_order:
        ordered_values = []
        if raw_order.startswith('['):
            try:
                parsed = json.loads(raw_order)
                ordered_values = parsed if isinstance(parsed, list) else []
            except (TypeError, ValueError, json.JSONDecodeError):
                ordered_values = []
        else:
            ordered_values = raw_order.split(',')
        for value in ordered_values:
            try:
                product_id = int(value)
            except (TypeError, ValueError):
                continue
            if (
                product_id > 0
                and product_id not in seen
                and form.get(f'selected_{product_id}') == 'on'
            ):
                seen.add(product_id)
                product_ids.append(product_id)

    for key in form.keys():
        if not key.startswith('selected_') or form.get(key) != 'on':
            continue
        try:
            product_id = int(key[len('selected_'):])
        except (TypeError, ValueError):
            continue
        if product_id > 0 and product_id not in seen:
            seen.add(product_id)
            product_ids.append(product_id)

    products_by_id = {}
    # Chunk the lookup so even unusually large PIs stay below SQLite's bound
    # parameter limit.  Normal PIs execute only one small query.
    for start in range(0, len(product_ids), 500):
        chunk = product_ids[start:start + 500]
        for product in Product.query.filter(Product.id.in_(chunk)).all():
            if product.active or product.id in allow_inactive_ids:
                products_by_id[product.id] = product

    selected_items = []
    total_amount = 0.0
    for product_id in product_ids:
        product = products_by_id.get(product_id)
        if not product:
            continue
        try:
            quantity = int(form.get(f'qty_{product_id}', '1').strip() or '1')
        except (AttributeError, TypeError, ValueError):
            quantity = 1
        unit_price_raw = form.get(f'unit_price_{product_id}', '')
        try:
            unit_price = _nonnegative_float(
                unit_price_raw if str(unit_price_raw or '').strip() else product.unit_price,
                '产品单价',
            )
        except ValueError:
            continue
        if quantity <= 0:
            continue
        amount = round(unit_price * quantity, 2)
        selected_items.append({
            'product': product,
            'quantity': quantity,
            'unit_price': unit_price,
            'amount': amount,
        })
        total_amount += amount
    return selected_items, round(total_amount, 2)

BANK_SNAPSHOT_FIELDS = (
    'bank_beneficiary_name', 'bank_account_no', 'bank_country_region',
    'bank_beneficiary_address', 'bank_name', 'bank_address',
    'bank_swift_code', 'bank_code', 'bank_branch_code', 'bank_currency',
)


def _apply_bank_snapshot(pi, account, freeform='', preserve_existing=False):
    """Apply a complete, historical receiving-account snapshot to one PI."""
    if account:
        pi.bank_info = account.bank_info()
        for field, value in account.snapshot().items():
            setattr(pi, field, value)
        return
    if is_admin():
        pi.bank_info = (freeform or '').strip() or (
            pi.bank_info if preserve_existing else ''
        )
        if not preserve_existing:
            for field in BANK_SNAPSHOT_FIELDS:
                setattr(pi, field, '')


def _legacy_account_bank_info(account):
    """Return the short bank text generated by releases before full snapshots."""
    parts = []
    if account.bank_name:
        parts.append(account.bank_name)
    if account.account_no:
        parts.append(f'A/C: {account.account_no}')
    if account.swift_code:
        parts.append(f'SWIFT: {account.swift_code}')
    return '\n'.join(parts)

def _matching_account_for_pi(pi):
    """Return the account originally saved on the PI when it still exists."""
    pi_currency = (pi.currency or 'USD').upper()
    saved_bank_info = (pi.bank_info or '').strip()
    saved_account_no = (getattr(pi, 'bank_account_no', '') or '').strip()
    for account in Account.query.filter_by(currency=pi_currency).order_by(Account.name).all():
        if saved_account_no and saved_account_no == (account.account_no or '').strip():
            return account
        if saved_bank_info in {
            account.bank_info().strip(), _legacy_account_bank_info(account).strip()
        }:
            return account
    return None

def _normalize_payment_reference(value):
    return ''.join(str(value or '').split()).casefold()

def _snapshot(obj, fields):
    result = {}
    for field in fields:
        value = getattr(obj, field, None)
        if isinstance(value, (datetime, date)):
            value = value.isoformat()
        result[field] = value
    return result

def _audit(action, entity_type, entity_id=None, summary='', before=None, after=None):
    """Add an append-only audit event to the current database transaction."""
    user = get_current_user() if has_request_context() else None
    db.session.add(AuditLog(
        user_id=user.id if user else None,
        username=user.username if user else 'system',
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        summary=summary[:300],
        before_json=json.dumps(before or {}, ensure_ascii=False, default=str),
        after_json=json.dumps(after or {}, ensure_ascii=False, default=str),
        ip_address=(request.remote_addr or '')[:64] if has_request_context() else '',
    ))

def _require_current_password():
    user = get_current_user()
    password = request.form.get('current_password', '')
    if not user or not check_password_hash(user.password_hash, password):
        flash('当前管理员密码不正确。', 'danger')
        return False
    return True

def _submitted_version(obj):
    try:
        return int(request.form.get('version', '0'))
    except (TypeError, ValueError):
        return 0

def _active_payments(pi_id):
    return Payment.query.filter_by(pi_id=pi_id).filter(Payment.deleted_at.is_(None)).order_by(Payment.created_at).all()

def _recalculate_pi_payments(pi):
    """Recalculate payment aggregates without changing downstream records."""
    payments = _active_payments(pi.id)
    total_paid = sum(p.amount + (p.fee or 0) for p in payments)
    pi.received_amount = round(sum(p.amount for p in payments), 2)
    pi.paid = total_paid >= pi.grand_total
    pi.version = (pi.version or 1) + 1
    return total_paid

def _recalculate_customer_deal(customer):
    pis = PI.query.filter_by(customer_id=customer.id).filter(PI.deleted_at.is_(None)).all()
    total = 0.0
    for pi in pis:
        received_with_fee = sum(
            (payment.amount or 0) + (payment.fee or 0)
            for payment in pi.active_payments
        )
        # A customer cannot receive more deal credit from one PI than the
        # amount invoiced, even when an overpayment or fee crosses the total.
        deal_amount = min(max(received_with_fee, 0), max(pi.grand_total, 0))
        total += deal_amount / PERFORMANCE_EXCHANGE_RATE if (pi.currency or 'USD').upper() == 'RMB' else deal_amount
    customer.total_deal_usd = round(total, 2)

def _save_upload(file):
    """Save an uploaded file and return the filename."""
    if not file or file.filename == '':
        return ''
    filename = secure_filename(file.filename)
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ('.jpg', '.jpeg', '.png', '.gif', '.webp'):
        return ''
    unique_name = f"{uuid.uuid4().hex}{ext}"
    target = os.path.join(current_app.config['UPLOAD_DIR'], unique_name)
    file.save(target)
    try:
        from PIL import Image
        with Image.open(target) as image:
            image.verify()
        with Image.open(target) as image:
            if image.width * image.height > 25_000_000:
                raise ValueError('Image dimensions are too large')
    except Exception:
        if os.path.exists(target):
            os.remove(target)
        return ''
    return unique_name

def _remove_upload(filename):
    """Remove one app-managed upload without allowing path traversal."""
    safe_name = secure_filename(filename or '')
    if not safe_name or safe_name != filename:
        return
    path = os.path.join(current_app.config['UPLOAD_DIR'], safe_name)
    if os.path.isfile(path):
        os.remove(path)

def _copy_product_image(filename):
    """Copy a product image so the new product owns a separate file."""
    safe_name = secure_filename(filename or '')
    if not safe_name or safe_name != filename:
        return ''
    source_path = os.path.join(current_app.config['UPLOAD_DIR'], safe_name)
    if not os.path.isfile(source_path):
        return ''
    extension = os.path.splitext(safe_name)[1].lower()
    new_name = f'{uuid.uuid4().hex}{extension}'
    shutil.copy2(source_path, os.path.join(current_app.config['UPLOAD_DIR'], new_name))
    return new_name

def _remove_product_image_if_unused(filename):
    """Delete an image only after no product record points to it."""
    safe_name = secure_filename(filename or '')
    if not safe_name or safe_name != filename:
        return
    if Product.query.filter_by(image=safe_name).first():
        return
    try:
        _remove_upload(safe_name)
    except OSError:
        # The database change is already committed. A leftover orphan is safer
        # than turning a successful product operation into a visible failure.
        pass
    thumbnail_path = _product_thumbnail_path(safe_name)
    try:
        if os.path.isfile(thumbnail_path):
            os.remove(thumbnail_path)
    except OSError:
        pass

def _product_reference_count(product_id):
    """Count every historical PI item that references the product."""
    return PIItem.query.filter_by(product_id=product_id).count()

def _retire_or_delete_product(product):
    """Disable referenced products; hard-delete only products never used by a PI."""
    reference_count = _product_reference_count(product.id)
    before = _snapshot(product, ['name', 'product_code', 'image', 'active'])
    if reference_count:
        product.active = False
        _audit(
            'disable', 'product', product.id,
            f'停用产品：{product.name}（关联 {reference_count} 条 PI 明细）',
            before=before,
            after=_snapshot(product, ['name', 'product_code', 'image', 'active']),
        )
        return 'disabled', reference_count, ''

    image_filename = product.image or ''
    _audit(
        'delete', 'product', product.id, f'删除未被引用的产品：{product.name}',
        before=before,
    )
    db.session.delete(product)
    return 'deleted', 0, image_filename

def _product_thumbnail_path(filename):
    stem = os.path.splitext(filename)[0]
    return os.path.join(current_app.config['UPLOAD_DIR'], '.thumbs', f'{stem}.webp')

def _ensure_product_thumbnail(filename, source_path):
    """Create a small cached derivative without modifying the original image."""
    thumb_path = _product_thumbnail_path(filename)
    try:
        if (os.path.isfile(thumb_path)
                and os.path.getmtime(thumb_path) >= os.path.getmtime(source_path)):
            return thumb_path
        from PIL import Image, ImageOps
        os.makedirs(os.path.dirname(thumb_path), exist_ok=True)
        temp_path = f'{thumb_path}.{uuid.uuid4().hex}.tmp'
        try:
            with Image.open(source_path) as source:
                image = ImageOps.exif_transpose(source)
                if image.mode not in ('RGB', 'RGBA'):
                    image = image.convert('RGBA' if 'transparency' in image.info else 'RGB')
                image.thumbnail((320, 320), Image.Resampling.LANCZOS)
                image.save(temp_path, format='WEBP', quality=82, method=4)
            os.replace(temp_path, thumb_path)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        return thumb_path
    except Exception:
        current_app.logger.warning('Could not create product thumbnail for %s', filename)
        return source_path

ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png', 'gif', 'webp'}


# ── Auth helpers ─────────────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        user = get_current_user()
        if not user or not user.active or session.get('auth_version') != user.auth_version:
            session.clear()
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def get_current_user():
    if 'current_user' not in g:
        user_id = session.get('user_id')
        g.current_user = db.session.get(User, user_id) if user_id else None
    return g.current_user

def is_admin():
    user = get_current_user()
    return bool(user and user.active and user.role == 'admin')

def current_salesperson_name():
    user = get_current_user()
    return user.salesperson_name if user and user.active else ''


def _find_user_by_account(account):
    """Look up an account without making login identifiers case-sensitive."""
    account = (account or '').strip()
    if not account:
        return None
    return User.query.filter(func.lower(User.account) == account.lower()).first()


def _valid_account(account):
    """Reject empty, overly long or control-character login identifiers."""
    return bool(
        account
        and len(account) <= 64
        and not re.search(r'[\x00-\x1f\x7f]', account)
    )


def _allow_account_lookup(client_ip):
    """Limit anonymous display-name lookups to reduce account enumeration."""
    now = time.time()
    cutoff = now - 60
    with _LOGIN_LOCK:
        recent = [stamp for stamp in _ACCOUNT_LOOKUPS.get(client_ip, []) if stamp >= cutoff]
        if len(recent) >= 20:
            _ACCOUNT_LOOKUPS[client_ip] = recent
            return False
        recent.append(now)
        _ACCOUNT_LOOKUPS[client_ip] = recent
    return True

def admin_required(f):
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        if not is_admin():
            abort(403)
        return f(*args, **kwargs)
    return decorated

def can_access_customer(customer):
    return is_admin() or (
        bool(current_salesperson_name()) and
        customer.salesperson == current_salesperson_name()
    )

def can_access_pi(pi):
    return is_admin() or (
        bool(current_salesperson_name()) and
        pi.salesperson == current_salesperson_name()
    )

def require_customer_access(customer):
    if getattr(customer, 'deleted_at', None) is not None:
        abort(404)
    if not can_access_customer(customer):
        abort(403)
    return customer

def require_pi_access(pi):
    if getattr(pi, 'deleted_at', None) is not None:
        abort(404)
    if not can_access_pi(pi):
        abort(403)
    return pi

def filter_by_user(query, model, salesperson_field='salesperson'):
    """Filter query by current user's salesperson if not admin."""
    if hasattr(model, 'deleted_at'):
        query = query.filter(getattr(model, 'deleted_at').is_(None))
    if is_admin():
        return query
    sp = current_salesperson_name()
    if sp and hasattr(model, salesperson_field):
        return query.filter(getattr(model, salesperson_field) == sp)
    return query.filter(db.false())


# ═══════════════════════════════════════════════════════════════════════
#  ROUTES — Auth
# ═══════════════════════════════════════════════════════════════════════

@app.route('/favicon.ico')
def favicon():
    """兼容仍会固定请求 /favicon.ico 的浏览器。"""
    return redirect(url_for('static', filename='favicon.svg', v='20260902'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    login_account = ''
    if request.method == 'POST':
        client_ip = request.remote_addr or 'unknown'
        now = time.time()
        with _LOGIN_LOCK:
            failures, blocked_until = _LOGIN_ATTEMPTS.get(client_ip, (0, 0))
        if blocked_until > now:
            flash('登录失败次数过多，请稍后再试。', 'danger')
            return render_template('login.html', login_account=login_account), 429
        # Keep accepting the old field name for a short compatibility window,
        # but always authenticate against the new account column.
        login_account = request.form.get(
            'account', request.form.get('username', '')
        ).strip()
        password = request.form.get('password', '')
        user = _find_user_by_account(login_account)
        if user and user.active and check_password_hash(user.password_hash, password):
            # Clear any pre-login state to prevent session fixation.
            session.clear()
            session['user_id'] = user.id
            session['username'] = user.username
            session['role'] = user.role
            session['salesperson_name'] = user.salesperson_name
            session['auth_version'] = user.auth_version
            session.permanent = True
            with _LOGIN_LOCK:
                _LOGIN_ATTEMPTS.pop(client_ip, None)
            flash(f'欢迎，{user.username}！', 'success')
            return redirect(url_for('profile' if user.must_change_password else 'index'))
        # Use one message for wrong, missing and disabled accounts so the login
        # endpoint does not disclose account status.
        flash('账号或密码错误。', 'danger')
        with _LOGIN_LOCK:
            failures += 1
            _LOGIN_ATTEMPTS[client_ip] = (failures, now + 900 if failures >= 5 else 0)
    return render_template('login.html', login_account=login_account)


@app.route('/login/account-name', methods=['POST'])
def login_account_name():
    """Return the display name used by the login form's read-only preview."""
    client_ip = request.remote_addr or 'unknown'
    if not _allow_account_lookup(client_ip):
        return jsonify({'ok': False, 'username': '', 'message': '查询过于频繁，请稍后再试。'}), 429
    payload = request.get_json(silent=True) or {}
    account = str(payload.get('account', '')).strip()
    user = _find_user_by_account(account) if _valid_account(account) else None
    if not user or not user.active:
        return jsonify({'ok': False, 'username': ''})
    return jsonify({'ok': True, 'username': user.username})


@app.route('/logout')
def logout():
    session.clear()
    flash('已安全退出。', 'info')
    return redirect(url_for('login'))


@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    user = get_current_user()
    sp = None
    if not is_admin() and user.salesperson_name:
        sp = Salesperson.query.filter_by(name=user.salesperson_name).first()
        # Auto-create salesperson record if missing
        if not sp:
            sp = Salesperson(name=user.salesperson_name)
            db.session.add(sp)
            db.session.commit()

    if request.method == 'POST':
        action = request.form.get('action', '')
        if action == 'change_password':
            current_pw = request.form.get('current_password', '').strip()
            new_pw = request.form.get('new_password', '').strip()
            confirm_pw = request.form.get('confirm_password', '').strip()
            if not current_pw or not new_pw:
                flash('请填写所有密码字段。', 'danger')
            elif not check_password_hash(user.password_hash, current_pw):
                flash('当前密码不正确。', 'danger')
            elif len(new_pw) < 10:
                flash('新密码至少需要 10 个字符。', 'danger')
            elif new_pw != confirm_pw:
                flash('两次输入的新密码不一致。', 'danger')
            else:
                user.password_hash = generate_password_hash(new_pw)
                user.must_change_password = False
                user.auth_version += 1
                db.session.commit()
                # Keep this freshly authenticated password-change session valid;
                # every other session still carries the old version.
                session['auth_version'] = user.auth_version
                flash('密码修改成功。', 'success')
                return redirect(url_for('profile'))
            return redirect(url_for('profile'))
        elif sp:
            sp.phone = request.form.get('phone', '').strip()
            sp.email = request.form.get('email', '').strip()
            sp.notes = request.form.get('notes', '').strip()
            db.session.commit()
            flash('个人资料已更新。', 'success')
            return redirect(url_for('profile'))

    # Stats for salesperson
    stats = None
    pi_list = []
    if sp:
        saved_pi_rate = func.coalesce(
            func.nullif(PI.exchange_rate, 0), PERFORMANCE_EXCHANGE_RATE
        )
        stats = db.session.query(
            func.count(PI.id).label('pi_count'),
            func.coalesce(func.sum(
                db.case(
                    (PI.currency == 'RMB', (PI.total_amount + func.coalesce(PI.shipping_cost, 0)) / saved_pi_rate),
                    else_=(PI.total_amount + func.coalesce(PI.shipping_cost, 0))
                )
            ), 0).label('total_amount'),
        ).filter(PI.salesperson == sp.name, PI.deleted_at.is_(None)).first()
        pi_list = PI.query.options(joinedload(PI.customer)).filter_by(salesperson=sp.name).filter(PI.deleted_at.is_(None)).order_by(PI.created_at.desc()).limit(10).all()

    return render_template('profile.html', sp=sp, stats=stats, pi_list=pi_list)


@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings_page():
    """Admin settings — DingTalk webhook & app config."""
    if not is_admin():
        flash('仅管理员可操作。', 'danger')
        return redirect(url_for('profile'))

    if request.method == 'POST':
        settings = _load_settings()
        import json as _json
        webhook = request.form.get('dingtalk_webhook', '').strip()
        shu_kei_webhook = request.form.get('dingtalk_shu_kei_webhook', '').strip()
        appkey = request.form.get('dingtalk_appkey', '').strip()
        appsecret = request.form.get('dingtalk_appsecret', '').strip()
        agent_id = request.form.get('dingtalk_agent_id', '').strip()
        default_execs = request.form.getlist('default_executors')
        if webhook:
            settings['dingtalk_webhook'] = webhook
        if shu_kei_webhook:
            settings['dingtalk_shu_kei_webhook'] = shu_kei_webhook
        if appkey:
            settings['dingtalk_appkey'] = appkey
        if appsecret:
            settings['dingtalk_appsecret'] = appsecret
        if agent_id:
            settings['dingtalk_agent_id'] = agent_id
        settings['dingtalk_report_enabled'] = '1' if request.form.get('dingtalk_report_enabled') else '0'
        settings['dingtalk_task_enabled'] = '1' if request.form.get('dingtalk_task_enabled') else '0'
        settings['dingtalk_default_executors'] = _json.dumps(default_execs)
        exchange_rate = request.form.get('exchange_rate', '').strip()
        if exchange_rate:
            try:
                parsed_rate = _nonnegative_float(exchange_rate, '默认业务汇率')
            except ValueError as exc:
                flash(str(exc), 'danger')
                return redirect(url_for('settings_page'))
            if parsed_rate <= 0:
                flash('默认业务汇率必须大于 0。', 'danger')
                return redirect(url_for('settings_page'))
            settings['exchange_rate'] = str(parsed_rate)
        _save_settings(settings)
        flash('设置已保存。', 'success')
        return redirect(url_for('settings_page'))

    settings = _load_settings()
    import json as _json
    # Get salespersons with DT user IDs for default executor selection
    dt_sps = Salesperson.query.filter(Salesperson.dingtalk_user_id != '').filter(Salesperson.dingtalk_user_id.isnot(None)).all()
    default_execs = _json.loads(settings.get('dingtalk_default_executors', '[]'))
    return render_template('settings.html',
                           # Never render stored secrets back into HTML.  Blank
                           # fields mean "keep current value" on POST.
                           dingtalk_webhook='',
                           dingtalk_shu_kei_webhook='',
                           dingtalk_appkey=settings.get('dingtalk_appkey', ''),
                           dingtalk_appsecret='',
                           dingtalk_agent_id=settings.get('dingtalk_agent_id', ''),
                           exchange_rate=settings.get('exchange_rate', '7.0'),
                           webhook_ok=bool(settings.get('dingtalk_webhook')),
                           shu_kei_webhook_ok=bool(settings.get('dingtalk_shu_kei_webhook')),
                           report_enabled=_setting_enabled(settings, 'dingtalk_report_enabled'),
                           task_enabled=_setting_enabled(settings, 'dingtalk_task_enabled'),
                           task_ok=bool(settings.get('dingtalk_appkey') and settings.get('dingtalk_appsecret')),
                           dt_sps=dt_sps,
                           default_execs=default_execs)


# ═══════════════════════════════════════════════════════════════════════
#  ROUTES — Dashboard
# ═══════════════════════════════════════════════════════════════════════

@app.route('/')
@login_required
def index():
    cust_q = filter_by_user(Customer.query, Customer, 'salesperson')
    customer_count = cust_q.count()
    product_count = Product.query.filter(Product.active.is_(True)).count()
    pi_q = filter_by_user(PI.query, PI, 'salesperson')
    pi_count = pi_q.count()
    recent_pis = pi_q.order_by(PI.created_at.desc()).limit(5).all()
    return render_template('index.html',
                           customer_count=customer_count,
                           product_count=product_count,
                           pi_count=pi_count,
                           recent_pis=recent_pis)


# ═══════════════════════════════════════════════════════════════════════
#  ROUTES — Customers
# ═══════════════════════════════════════════════════════════════════════

@app.route('/customers')
@login_required
def customer_list():
    search = request.args.get('search', '').strip()
    sort = request.args.get('sort', '').strip()
    sp_filter = request.args.get('sp', '').strip()
    deal_min_str = request.args.get('deal_min', '').strip()
    deal_max_str = request.args.get('deal_max', '').strip()
    date_from = request.args.get('date_from', '').strip()
    date_to = request.args.get('date_to', '').strip()

    query = filter_by_user(Customer.query, Customer, 'salesperson')
    if search:
        query = query.filter(
            db.or_(
                Customer.name.ilike(f'%{search}%'),
                Customer.country.ilike(f'%{search}%'),
                Customer.contact_person.ilike(f'%{search}%'),
                Customer.email.ilike(f'%{search}%'),
            )
        )
    if sp_filter:
        query = query.filter(Customer.salesperson == sp_filter)
    if deal_min_str:
        try:
            query = query.filter(Customer.total_deal_usd >= float(deal_min_str))
        except ValueError:
            pass
    if deal_max_str:
        try:
            query = query.filter(Customer.total_deal_usd <= float(deal_max_str))
        except ValueError:
            pass
    if date_from:
        try:
            query = query.filter(Customer.created_at >= datetime.strptime(date_from, '%Y-%m-%d'))
        except ValueError:
            pass
    if date_to:
        try:
            query = query.filter(Customer.created_at <= datetime.strptime(date_to, '%Y-%m-%d'))
        except ValueError:
            pass

    if sort == 'deal_desc':
        query = query.order_by(Customer.total_deal_usd.desc())
    elif sort == 'deal_asc':
        query = query.order_by(Customer.total_deal_usd.asc())
    else:
        query = query.order_by(Customer.created_at.desc())

    # Pagination
    page = request.args.get('page', 1, type=int)
    per_page = 50
    total = query.count()
    total_pages = max(1, (total + per_page - 1) // per_page)
    if page < 1: page = 1
    if page > total_pages: page = total_pages

    # Totals for current filter
    filter_total_deal = query.with_entities(func.coalesce(func.sum(Customer.total_deal_usd), 0)).scalar() or 0

    customers = query.limit(per_page).offset((page - 1) * per_page).all()
    return render_template('customers.html', customers=customers, search=search, sort=sort,
                           sp_filter=sp_filter, deal_min=deal_min_str, deal_max=deal_max_str,
                           date_from=date_from, date_to=date_to, page=page,
                           total_pages=total_pages, total=total,
                           filter_total_deal=filter_total_deal)


@app.route('/customers/add', methods=['GET', 'POST'])
@login_required
def customer_add():
    if request.method == 'POST':
        image_file = request.files.get('image')
        customer = Customer(
            name=request.form.get('name', '').strip(),
            country=request.form.get('country', '').strip(),
            contact_person=request.form.get('contact_person', '').strip(),
            email=request.form.get('email', '').strip(),
            phone=request.form.get('phone', '').strip(),
            address=request.form.get('address', '').strip(),
            salesperson=(request.form.get('salesperson', '').strip() if is_admin()
                         else current_salesperson_name()),
            image=_save_upload(image_file) if image_file else '',
            notes=request.form.get('notes', '').strip(),
        )
        if not customer.name:
            flash('客户名称不能为空。', 'danger')
            return render_template('customer_form.html', customer=customer, editing=False)
        if not customer.salesperson:
            flash('请选择业务员。', 'danger')
            return render_template('customer_form.html', customer=customer, editing=False)
        db.session.add(customer)
        db.session.flush()
        _audit('create', 'customer', customer.id, f'新增客户：{customer.name}', after=_snapshot(customer, ['name', 'country', 'contact_person', 'email', 'phone', 'salesperson']))
        db.session.commit()
        flash('客户添加成功。', 'success')
        return redirect(url_for('customer_list'))
    return render_template('customer_form.html', customer=None, editing=False)


@app.route('/customers/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def customer_edit(id):
    customer = Customer.query.get_or_404(id)
    require_customer_access(customer)
    if request.method == 'POST':
        if _submitted_version(customer) != (customer.version or 1):
            db.session.rollback()
            flash('该客户已被其他人修改，已重新加载最新版本，请核对后再次提交。', 'warning')
            return redirect(url_for('customer_edit', id=id))
        before = _snapshot(customer, ['name', 'country', 'contact_person', 'email', 'phone', 'address', 'salesperson', 'notes', 'version'])
        image_file = request.files.get('image')
        if image_file and image_file.filename:
            new_img = _save_upload(image_file)
            if new_img:
                # Delete old image
                if customer.image:
                    old_path = os.path.join(current_app.config['UPLOAD_DIR'], customer.image)
                    if os.path.exists(old_path):
                        os.remove(old_path)
                customer.image = new_img
        customer.name = request.form.get('name', '').strip()
        customer.country = request.form.get('country', '').strip()
        customer.contact_person = request.form.get('contact_person', '').strip()
        customer.email = request.form.get('email', '').strip()
        customer.phone = request.form.get('phone', '').strip()
        customer.address = request.form.get('address', '').strip()
        if is_admin():
            customer.salesperson = request.form.get('salesperson', '').strip()
        customer.notes = request.form.get('notes', '').strip()
        if not customer.name:
            flash('客户名称不能为空。', 'danger')
            return render_template('customer_form.html', customer=customer, editing=True)
        if not customer.salesperson:
            flash('请选择业务员。', 'danger')
            return render_template('customer_form.html', customer=customer, editing=True)
        customer.version = (customer.version or 1) + 1
        _audit('update', 'customer', customer.id, f'修改客户：{customer.name}', before=before,
               after=_snapshot(customer, ['name', 'country', 'contact_person', 'email', 'phone', 'address', 'salesperson', 'notes', 'version']))
        db.session.commit()
        flash('客户更新成功。', 'success')
        return redirect(url_for('customer_list'))
    return render_template('customer_form.html', customer=customer, editing=True)


@app.route('/api/customers/add', methods=['POST'])
@login_required
def api_customer_add():
    """AJAX endpoint — add a customer and return JSON."""
    name = request.form.get('name', '').strip()
    if not name:
        return jsonify({'success': False, 'error': '客户名称不能为空。'}), 400

    salesperson = (request.form.get('salesperson', '').strip() if is_admin()
                   else current_salesperson_name())
    if not salesperson:
        return jsonify({'success': False, 'error': '必须指定业务员。'}), 400
    if is_admin() and not Salesperson.query.filter_by(name=salesperson).first():
        return jsonify({'success': False, 'error': '请选择有效的业务员。'}), 400

    customer = Customer(
        name=name,
        country=request.form.get('country', '').strip(),
        contact_person=request.form.get('contact_person', '').strip(),
        email=request.form.get('email', '').strip(),
        phone=request.form.get('phone', '').strip(),
        address=request.form.get('address', '').strip(),
        salesperson=salesperson,
        notes=request.form.get('notes', '').strip(),
    )
    db.session.add(customer)
    db.session.flush()
    _audit('create', 'customer', customer.id, f'快速新增客户：{customer.name}', after=_snapshot(customer, ['name', 'country', 'contact_person', 'email', 'phone', 'salesperson']))
    db.session.commit()

    return jsonify({
        'success': True,
        'customer': customer.to_dict(),
    })


@app.route('/api/customers/<int:id>/copy', methods=['POST'])
@login_required
def api_customer_copy(id):
    """Duplicate a customer with same info."""
    original = Customer.query.get_or_404(id)
    require_customer_access(original)
    new_customer = Customer(
        name=original.name + ' (Copy)',
        country=original.country,
        contact_person=original.contact_person,
        email=original.email,
        phone=original.phone,
        address=original.address,
        salesperson=original.salesperson,
        notes=original.notes,
        image=original.image,
    )
    db.session.add(new_customer)
    db.session.flush()
    _audit('create', 'customer', new_customer.id, f'复制客户：{original.name}', after=_snapshot(new_customer, ['name', 'country', 'contact_person', 'email', 'phone', 'salesperson']))
    db.session.commit()
    return jsonify({
        'success': True,
        'customer': new_customer.to_dict(),
    })


@app.route('/customers/<int:id>')
@login_required
def customer_detail(id):
    customer = Customer.query.get_or_404(id)
    require_customer_access(customer)
    pi_number = request.args.get('pi_number', '').strip()
    date_from = request.args.get('date_from', '').strip()
    date_to = request.args.get('date_to', '').strip()
    product = request.args.get('product', '').strip()
    amount_min = request.args.get('amount_min', '').strip()
    amount_max = request.args.get('amount_max', '').strip()

    query = PI.query.options(
        joinedload(PI.items).joinedload(PIItem.product)
    ).filter_by(customer_id=id).filter(PI.deleted_at.is_(None))

    if pi_number:
        query = query.filter(PI.pi_number.contains(pi_number))
    if date_from:
        try:
            d_from = datetime.strptime(date_from, '%Y-%m-%d').date()
            query = query.filter(PI.issue_date >= d_from)
        except ValueError:
            pass
    if date_to:
        try:
            d_to = datetime.strptime(date_to, '%Y-%m-%d').date()
            query = query.filter(PI.issue_date <= d_to)
        except ValueError:
            pass
    if amount_min:
        try:
            query = query.filter((PI.total_amount + func.coalesce(PI.shipping_cost, 0)) >= float(amount_min))
        except ValueError:
            pass
    if amount_max:
        try:
            query = query.filter((PI.total_amount + func.coalesce(PI.shipping_cost, 0)) <= float(amount_max))
        except ValueError:
            pass
    if product:
        query = query.join(PI.items).join(PIItem.product).filter(
            Product.name.ilike(f'%{product}%')
        ).distinct()

    pis = query.order_by(PI.created_at.desc()).all()
    resp = make_response(render_template('customer_detail.html', customer=customer, pis=pis,
                                          pi_number=pi_number, date_from=date_from, date_to=date_to,
                                          product=product, amount_min=amount_min, amount_max=amount_max))
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return resp


@app.route('/sales-stats')
@login_required
def sales_stats():
    """Payment received stats — paid PIs only, filterable by salesperson."""
    date_from = request.args.get('date_from', '').strip()
    date_to = request.args.get('date_to', '').strip()
    preset = request.args.get('preset', '').strip()
    sp_filter = request.args.get('sp', '').strip()

    # Apply preset date ranges
    today = date.today()
    if preset == 'this_month':
        date_from = today.replace(day=1).strftime('%Y-%m-%d')
        date_to = today.strftime('%Y-%m-%d')
    elif preset == 'last_month':
        first_of_this_month = today.replace(day=1)
        last_of_last_month = first_of_this_month - timedelta(days=1)
        date_from = last_of_last_month.replace(day=1).strftime('%Y-%m-%d')
        date_to = last_of_last_month.strftime('%Y-%m-%d')
    elif preset == 'this_year':
        date_from = today.replace(month=1, day=1).strftime('%Y-%m-%d')
        date_to = today.strftime('%Y-%m-%d')

    paid_filter = (PI.received_amount > 0)  # include partial payments

    # Performance conversion is intentionally fixed and independent from each
    # PI's quotation/profit rate and the editable system default.
    amount_usd = func.sum(
        db.case(
            (PI.currency == 'RMB', PI.received_amount / PERFORMANCE_EXCHANGE_RATE),
            else_=PI.received_amount
        )
    )
    base_q = db.session.query(
        func.coalesce(db.func.nullif(PI.salesperson, ''), '(未分配)').label('salesperson'),
        func.count(PI.id).label('pi_count'),
        func.coalesce(amount_usd, 0).label('total_amount'),
        func.count(db.distinct(PI.customer_id)).label('customer_count'),
    ).filter(paid_filter, PI.deleted_at.is_(None))
    if not is_admin():
        base_q = base_q.filter(PI.salesperson == current_salesperson_name())
    if sp_filter:
        base_q = base_q.filter(PI.salesperson == sp_filter)
    if date_from:
        try:
            base_q = base_q.filter(PI.issue_date >= datetime.strptime(date_from, '%Y-%m-%d').date())
        except ValueError:
            pass
    if date_to:
        try:
            base_q = base_q.filter(PI.issue_date <= datetime.strptime(date_to, '%Y-%m-%d').date())
        except ValueError:
            pass
    results = base_q.group_by(PI.salesperson).order_by(amount_usd.desc()).all()

    grand_total = sum(r.total_amount for r in results)
    grand_pi_count = sum(r.pi_count for r in results)

    # Detailed PI list for the same filter (paid only) — eager load payments for fee display
    pi_detail_q = PI.query.options(
        joinedload(PI.customer),
        joinedload(PI.payments)
    ).filter(paid_filter, PI.deleted_at.is_(None)).order_by(PI.created_at.desc())
    if not is_admin():
        pi_detail_q = pi_detail_q.filter(PI.salesperson == current_salesperson_name())
    if sp_filter:
        pi_detail_q = pi_detail_q.filter(PI.salesperson == sp_filter)
    if date_from:
        try: pi_detail_q = pi_detail_q.filter(PI.issue_date >= datetime.strptime(date_from, '%Y-%m-%d').date())
        except: pass
    if date_to:
        try: pi_detail_q = pi_detail_q.filter(PI.issue_date <= datetime.strptime(date_to, '%Y-%m-%d').date())
        except: pass
    all_filtered_pis = pi_detail_q.all()

    # Check if any PI is in RMB
    has_rmb = any(pi.currency == 'RMB' for pi in all_filtered_pis)

    return render_template('sales_stats.html',
                           stats=results,
                           grand_total=grand_total,
                           grand_pi_count=grand_pi_count,
                           date_from=date_from,
                           date_to=date_to,
                           preset=preset,
                           sp_filter=sp_filter,
                           all_pis=all_filtered_pis,
                           has_rmb=has_rmb,
                           performance_exchange_rate=PERFORMANCE_EXCHANGE_RATE)


def _report_filter_values():
    """Return normalized salesperson/date filters shared by admin PI reports."""
    salesperson_filter = request.args.get('salesperson', '').strip()
    date_from = request.args.get('date_from', '').strip()
    date_to = request.args.get('date_to', '').strip()
    preset = request.args.get('preset', '').strip()

    today = date.today()
    if preset == 'this_month':
        date_from = today.replace(day=1).isoformat()
        date_to = today.isoformat()
    elif preset == 'last_month':
        last_day = today.replace(day=1) - timedelta(days=1)
        date_from = last_day.replace(day=1).isoformat()
        date_to = last_day.isoformat()
    elif preset == 'this_year':
        date_from = today.replace(month=1, day=1).isoformat()
        date_to = today.isoformat()
    else:
        preset = ''

    def normalized_date(value):
        if not value:
            return ''
        try:
            return datetime.strptime(value, '%Y-%m-%d').date().isoformat()
        except ValueError:
            return ''

    date_from = normalized_date(date_from)
    date_to = normalized_date(date_to)
    if date_from and date_to and date_from > date_to:
        date_from, date_to = date_to, date_from
    return salesperson_filter, date_from, date_to, preset


def _apply_report_filters(query, salesperson_filter, date_from, date_to):
    """Apply the shared report filters to a PI query using PI issue dates."""
    if salesperson_filter:
        query = query.filter(PI.salesperson == salesperson_filter)
    if date_from:
        query = query.filter(PI.issue_date >= date.fromisoformat(date_from))
    if date_to:
        query = query.filter(PI.issue_date <= date.fromisoformat(date_to))
    return query


@app.route('/fees')
@app.route('/profit-report')
@admin_required
def fees_report():
    """Administrator-only per-order profit report, normalized to RMB."""
    default_exchange_rate = _get_exchange_rate()
    salesperson_filter, date_from, date_to, preset = _report_filter_values()

    # An order enters this report after any payment. Profit is calculated from
    # the full order revenue, but is only shown once all PI items have purchase
    # quantities so an incomplete purchase order cannot inflate profit.
    pi_query = PI.query.options(
        joinedload(PI.customer),
        selectinload(PI.items),
        selectinload(PI.procurements),
        selectinload(PI.payments),
        selectinload(PI.expenses),
    ).filter(
        PI.received_amount > 0,
        PI.deleted_at.is_(None),
    )
    pi_query = _apply_report_filters(
        pi_query, salesperson_filter, date_from, date_to
    )
    pis = pi_query.order_by(PI.created_at.desc()).all()

    def finite_amount(amount):
        try:
            value = float(amount or 0)
        except (TypeError, ValueError):
            return 0.0
        return value if math.isfinite(value) else 0.0

    def to_rmb(amount, currency, exchange_rate):
        value = finite_amount(amount)
        return value if (currency or 'USD').upper() == 'RMB' else value * exchange_rate

    pi_list = []
    for pi in pis:
        exchange_rate = _pi_exchange_rate(pi)
        currency = (pi.currency or 'USD').upper()
        sym = '¥' if currency == 'RMB' else '$'
        product_revenue_rmb = to_rmb(pi.product_subtotal, currency, exchange_rate)
        adjustment_rmb = to_rmb(pi.other_charges, currency, exchange_rate)
        order_revenue_rmb = product_revenue_rmb + adjustment_rmb

        purchased_by_item = {}
        procurement_cost_rmb = 0.0
        for procurement in pi.procurements:
            purchased_by_item[procurement.pi_item_id] = (
                purchased_by_item.get(procurement.pi_item_id, 0)
                + int(procurement.quantity or 0)
            )
            procurement_cost_rmb += finite_amount(procurement.total)
        procurement_data_complete = bool(pi.items) and all(
            int(item.quantity or 0) > 0
            and purchased_by_item.get(item.id, 0) >= int(item.quantity or 0)
            for item in pi.items
        )

        active_payments = [payment for payment in pi.payments if payment.deleted_at is None]
        payment_fee_rmb = sum(
            to_rmb(payment.fee, payment.receiving_account_currency or currency, exchange_rate)
            for payment in active_payments
        )
        expense_lines = []
        recorded_expense_rmb = 0.0
        for expense in sorted(pi.expenses, key=lambda item: item.created_at or datetime.min, reverse=True):
            expense_currency = (expense.currency or 'RMB').upper()
            amount_rmb = to_rmb(expense.amount, expense_currency, exchange_rate)
            recorded_expense_rmb += amount_rmb
            expense_lines.append({
                'id': expense.id,
                'category': expense.category,
                'amount': finite_amount(expense.amount),
                'currency': expense_currency,
                'symbol': '¥' if expense_currency == 'RMB' else '$',
                'amount_rmb': round(amount_rmb, 2),
                'note': expense.note or '',
                'has_attachment': bool(expense.attachment),
            })
        supplier_freight_rmb = finite_amount(pi.supplier_freight_cost)
        # A receiving fee reduces the cash income from the order. It is kept in
        # the income structure instead of being counted again as an order cost.
        net_income_rmb = order_revenue_rmb - payment_fee_rmb
        actual_expense_rmb = recorded_expense_rmb + supplier_freight_rmb
        total_actual_cost_rmb = procurement_cost_rmb + actual_expense_rmb
        potential_duplicate_freight = supplier_freight_rmb > 0 and any(
            '运费' in line['category'].strip() for line in expense_lines
        )

        profit_rmb = None
        margin_pct = None
        if procurement_data_complete:
            profit_rmb = net_income_rmb - total_actual_cost_rmb
            if net_income_rmb:
                margin_pct = profit_rmb / net_income_rmb * 100

        pi_list.append({
            'id': pi.id,
            'pi_number': pi.pi_number,
            'customer': pi.customer.name if pi.customer else '未知客户',
            'country': pi.customer.country if pi.customer else '',
            'currency': currency,
            'exchange_rate': exchange_rate,
            'sym': sym,
            'product_revenue': pi.product_subtotal,
            'adjustment': pi.other_charges,
            'adjustment_abs': abs(finite_amount(pi.other_charges)),
            'order_revenue': pi.grand_total,
            'received': float(pi.received_amount or 0),
            'product_revenue_rmb': round(product_revenue_rmb, 2),
            'adjustment_rmb': round(adjustment_rmb, 2),
            'order_revenue_rmb': round(order_revenue_rmb, 2),
            'net_income_rmb': round(net_income_rmb, 2),
            'procurement_cost_rmb': round(procurement_cost_rmb, 2),
            'procurement_data_complete': procurement_data_complete,
            'procurement_confirmed': bool(pi.procurement_confirmed),
            'payment_fee_rmb': round(payment_fee_rmb, 2),
            'actual_freight_rmb': round(supplier_freight_rmb, 2),
            'recorded_expense_rmb': round(recorded_expense_rmb, 2),
            'actual_expense_rmb': round(actual_expense_rmb, 2),
            'total_actual_cost_rmb': round(total_actual_cost_rmb, 2),
            'expense_lines': expense_lines,
            'potential_duplicate_freight': potential_duplicate_freight,
            'profit_rmb': round(profit_rmb, 2) if profit_rmb is not None else None,
            'margin_pct': round(margin_pct, 1) if margin_pct is not None else None,
            'date': pi.issue_date.strftime('%Y-%m-%d') if pi.issue_date else '',
            'paid': pi.paid,
        })

    calculable = [row for row in pi_list if row['profit_rmb'] is not None]
    summary = {
        'total_count': len(pi_list),
        'calculable_count': len(calculable),
        'pending_count': len(pi_list) - len(calculable),
        'product_revenue_rmb': round(sum(row['product_revenue_rmb'] for row in calculable), 2),
        'adjustment_rmb': round(sum(row['adjustment_rmb'] for row in calculable), 2),
        'order_revenue_rmb': round(sum(row['order_revenue_rmb'] for row in calculable), 2),
        'payment_fee_rmb': round(sum(row['payment_fee_rmb'] for row in calculable), 2),
        'net_income_rmb': round(sum(row['net_income_rmb'] for row in calculable), 2),
        'procurement_cost_rmb': round(sum(row['procurement_cost_rmb'] for row in calculable), 2),
        'actual_expense_rmb': round(sum(row['actual_expense_rmb'] for row in calculable), 2),
        'total_actual_cost_rmb': round(sum(row['total_actual_cost_rmb'] for row in calculable), 2),
        'profit_rmb': round(sum(row['profit_rmb'] for row in calculable), 2),
    }
    summary['margin_pct'] = round(
        summary['profit_rmb'] / summary['net_income_rmb'] * 100, 1
    ) if summary['net_income_rmb'] else None

    resp = make_response(render_template(
        'fees.html',
        pi_list=pi_list,
        summary=summary,
        default_exchange_rate=default_exchange_rate,
        salesperson_filter=salesperson_filter,
        date_from=date_from,
        date_to=date_to,
        preset=preset,
    ))
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'
    return resp


@app.route('/api/expenses', methods=['GET', 'POST'])
@login_required
def api_expenses():
    if request.method == 'POST':
        category_raw = request.form.get('category', '').strip()
        amount_str = request.form.get('amount', '0').strip()
        currency = request.form.get('currency', 'RMB').strip().upper()
        note = request.form.get('note', '').strip()[:1000]
        pi_id_str = request.form.get('pi_id', '').strip()
        try:
            pi_id = int(pi_id_str) if pi_id_str else None
        except ValueError:
            pi_id = None
        if not pi_id:
            return jsonify({'success': False, 'error': '订单真实成本必须关联一份 PI。'}), 400
        pi = PI.query.get_or_404(pi_id)
        require_pi_access(pi)
        if not category_raw:
            return jsonify({'success': False, 'error': '请选择订单真实成本类别。'}), 400
        try:
            category = _managed_field_value('expense_category', category_raw)
        except ValueError as exc:
            return jsonify({'success': False, 'error': str(exc)}), 400
        try:
            amount = _nonnegative_float(amount_str, '真实成本金额')
        except ValueError as exc:
            return jsonify({'success': False, 'error': str(exc)}), 400
        if amount <= 0:
            return jsonify({'success': False, 'error': '金额必须大于 0。'}), 400
        if currency not in {'RMB', 'USD'}:
            return jsonify({'success': False, 'error': '费用币种只能选择人民币或美元。'}), 400
        attachment_file = request.files.get('attachment')
        attachment_name = ''
        if attachment_file and attachment_file.filename:
            try:
                attachment_file.stream.seek(0, os.SEEK_END)
                attachment_size = attachment_file.stream.tell()
                attachment_file.stream.seek(0)
            except (AttributeError, OSError):
                attachment_size = 0
            if attachment_size > 12 * 1024 * 1024:
                return jsonify({'success': False, 'error': '凭证图片不能超过 12 MB。'}), 400
            attachment_name = _save_upload(attachment_file)
            if not attachment_name:
                return jsonify({
                    'success': False,
                    'error': '附件必须是有效的 JPG、PNG、WebP 或 GIF 图片。',
                }), 400
        exp = Expense(
            pi_id=pi_id,
            category=category[:200],
            amount=amount,
            currency=currency,
            note=note,
            attachment=attachment_name,
        )
        try:
            db.session.add(exp)
            db.session.flush()
            _audit(
                'create', 'expense', exp.id,
                f'为 PI {pi.pi_number} 新增订单真实成本 {category}',
                after=_snapshot(exp, ['pi_id', 'category', 'amount', 'currency', 'note', 'attachment']),
            )
            db.session.commit()
        except Exception:
            db.session.rollback()
            _remove_upload(attachment_name)
            raise
        return jsonify({'success': True, 'expense': exp.to_dict()})
    # GET
    pi_id = request.args.get('pi_id', type=int)
    q = Expense.query
    if pi_id:
        require_pi_access(PI.query.get_or_404(pi_id))
        q = q.filter_by(pi_id=pi_id)
    elif not is_admin():
        abort(403)
    expenses = q.order_by(Expense.created_at.desc()).all()
    return jsonify([e.to_dict() for e in expenses])


@app.route('/api/expenses/<int:id>', methods=['DELETE'])
@admin_required
def api_expense_delete(id):
    exp = Expense.query.get_or_404(id)
    pi = None
    if exp.pi_id:
        pi = PI.query.get_or_404(exp.pi_id)
        require_pi_access(pi)
    elif not is_admin():
        abort(403)
    attachment_name = exp.attachment or ''
    before = _snapshot(exp, ['pi_id', 'category', 'amount', 'currency', 'note', 'attachment'])
    _audit(
        'delete', 'expense', exp.id,
        f'删除 PI {pi.pi_number if pi else "未关联"} 的订单真实成本 {exp.category}',
        before=before,
    )
    db.session.delete(exp)
    db.session.commit()
    _remove_upload(attachment_name)
    return jsonify({'success': True})


@app.route('/expenses/<int:id>/attachment')
@login_required
def expense_attachment(id):
    """Serve an expense receipt only to users who may access its PI."""
    exp = Expense.query.get_or_404(id)
    if not exp.pi_id:
        abort(404)
    pi = PI.query.get_or_404(exp.pi_id)
    require_pi_access(pi)
    safe_name = secure_filename(exp.attachment or '')
    if not safe_name or safe_name != exp.attachment:
        abort(404)
    filepath = os.path.join(current_app.config['UPLOAD_DIR'], safe_name)
    if not os.path.isfile(filepath):
        abort(404)
    extension = os.path.splitext(safe_name)[1].lower()
    return send_file(
        filepath,
        conditional=True,
        download_name=f'{secure_filename(pi.pi_number) or "PI"}-真实成本凭证{extension}',
    )


@app.route('/customers/<int:id>/delete', methods=['POST'])
@login_required
def customer_delete(id):
    customer = Customer.query.get_or_404(id)
    require_customer_access(customer)
    if request.form.get('confirm_value', '').strip() != customer.name:
        flash('输入内容与客户名称不一致，未执行删除。', 'danger')
        return redirect(url_for('customer_list'))
    now = datetime.utcnow()
    before = _snapshot(customer, ['name', 'salesperson', 'deleted_at'])
    customer.deleted_at = now
    customer.version = (customer.version or 1) + 1
    related = PI.query.filter_by(customer_id=customer.id).filter(PI.deleted_at.is_(None)).all()
    for pi in related:
        pi.deleted_at = now
        pi.version = (pi.version or 1) + 1
    _audit('soft_delete', 'customer', customer.id, f'将客户 {customer.name} 及 {len(related)} 份 PI 移入回收站', before=before,
           after=_snapshot(customer, ['name', 'salesperson', 'deleted_at']))
    db.session.commit()
    flash('客户已移入回收站。', 'success')
    return redirect(url_for('customer_list'))


@app.route('/customers/<int:id>/reassign', methods=['POST'])
@login_required
def customer_reassign(id):
    if not is_admin():
        flash('无权执行此操作。', 'danger')
        return redirect(url_for('customer_list'))
    customer = Customer.query.get_or_404(id)
    new_sp = request.form.get('salesperson', '').strip()
    old_sp = customer.salesperson
    before = _snapshot(customer, ['name', 'salesperson', 'version'])
    if not new_sp:
        flash('请选择业务员。', 'danger')
        return redirect(url_for('customer_edit', id=id))
    # Update customer
    customer.salesperson = new_sp
    customer.version = (customer.version or 1) + 1
    # Update all PIs under this customer
    count = PI.query.filter_by(customer_id=id).update({'salesperson': new_sp})
    _audit('reassign', 'customer', customer.id, f'将客户从 {old_sp or "未分配"} 转交给 {new_sp}', before=before,
           after=_snapshot(customer, ['name', 'salesperson', 'version']))
    db.session.commit()
    old_label = old_sp or 'unassigned'
    flash(f'客户及其 {count} 份 PI 已从“{old_label}”转交给“{new_sp}”。', 'success')
    return redirect(url_for('customer_list'))


# ═══════════════════════════════════════════════════════════════════════
#  ROUTES — Products
# ═══════════════════════════════════════════════════════════════════════

@app.route('/products')
@login_required
def product_list():
    search = request.args.get('search', '').strip()
    filter_type = request.args.get('filter', '').strip()
    sort = request.args.get('sort', '').strip()
    page = request.args.get('page', 1, type=int)
    per_page = 50

    query = Product.query
    if filter_type == 'all':
        pass
    elif filter_type == 'inactive':
        query = query.filter(Product.active.is_(False))
    else:
        query = query.filter(Product.active.is_(True))
    if search:
        query = query.filter(
            db.or_(
                Product.name.ilike(f'%{search}%'),
                Product.product_code.ilike(f'%{search}%'),
                Product.specification.ilike(f'%{search}%'),
                Product.chinese_name.ilike(f'%{search}%'),
            )
        )
    if filter_type == 'no_image':
        query = query.filter((Product.image == None) | (Product.image == ''))

    # Sorting
    sort_map = {
        'name_asc': Product.name.asc(),
        'name_desc': Product.name.desc(),
        'code_asc': Product.product_code.asc(),
        'code_desc': Product.product_code.desc(),
        'spec_asc': Product.specification.asc(),
        'spec_desc': Product.specification.desc(),
        'cn_asc': Product.chinese_name.asc(),
        'cn_desc': Product.chinese_name.desc(),
        'price_asc': Product.unit_price.asc(),
        'price_desc': Product.unit_price.desc(),
    }
    order_by = sort_map.get(sort, Product.created_at.desc())

    total = query.count()
    total_pages = max(1, (total + per_page - 1) // per_page)
    if page < 1: page = 1
    if page > total_pages: page = total_pages

    products = query.order_by(order_by).limit(per_page).offset((page - 1) * per_page).all()
    return render_template('products.html', products=products, search=search, filter=filter_type,
                           sort=sort, page=page, total_pages=total_pages, total=total)


@app.route('/products/import', methods=['GET', 'POST'])
@admin_required
def product_import():
    """Import products from Excel file with floating images."""
    from openpyxl import load_workbook

    if request.method == 'POST':
        use_path = request.form.get('server_path', '').strip()
        own_tmp = False

        if use_path:
            # Import from server-side file path
            tmp_path = use_path
            if not os.path.exists(tmp_path):
                flash(f'找不到文件：{tmp_path}', 'danger')
                return redirect(url_for('product_import'))
            if not tmp_path.lower().endswith(('.xlsx', '.xlsm')):
                flash('文件必须为 .xlsx 或 .xlsm 格式。', 'danger')
                return redirect(url_for('product_import'))
            own_tmp = False
        else:
            # Uploaded file
            file = request.files.get('excel_file')
            if not file or not file.filename:
                flash('请选择 Excel 文件或输入服务器路径。', 'danger')
                return redirect(url_for('product_import'))

            if not file.filename.lower().endswith(('.xlsx', '.xlsm')):
                flash('请上传 .xlsx 或 .xlsm 文件。', 'danger')
                return redirect(url_for('product_import'))

            tmp_path = os.path.join(app.config['UPLOAD_DIR'], f'_import_{uuid.uuid4().hex}.xlsx')
            file.save(tmp_path)
            own_tmp = True

        created_images = []
        replaced_images = []
        try:
            wb = load_workbook(tmp_path)
            ws = wb.active

            # ── Extract floating images and map to rows ──
            row_images = {}  # row -> list of image objects
            for img in ws._images:
                try:
                    anchor = img.anchor
                    # TwoCellAnchor or OneCellAnchor
                    if hasattr(anchor, '_from'):
                        row = anchor._from.row  # 0-indexed
                        col = anchor._from.col
                        if row not in row_images:
                            row_images[row] = []
                        row_images[row].append(img)
                except Exception:
                    pass

            # ── Parse data rows (starting from row 2, 0-indexed row 1) ──
            imported = 0
            with_images = 0
            skipped = 0

            for row_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=False)):
                excel_row = row_idx + 1  # 0-indexed row number

                # Read cell values (columns A-E = indices 0-4)
                # A: No, B: Name, C: Code, D: Specification, E: Unit Price
                name = str(row[1].value).strip() if row[1].value else ''
                if not name or name == 'None':
                    skipped += 1
                    continue
                if len(name) > 200:
                    name = name[:200]

                code = str(row[2].value).strip() if len(row) > 2 and row[2].value else ''
                if len(code) > 100:
                    code = code[:100]

                spec = str(row[3].value).strip() if len(row) > 3 and row[3].value else ''
                if len(spec) > 200:
                    spec = spec[:200]

                # Parse price
                price = 0.0
                if len(row) > 4 and row[4].value is not None:
                    try:
                        price = float(str(row[4].value).strip().replace(',', ''))
                    except (ValueError, TypeError):
                        price = 0.0

                # ── Extract image for this row ──
                image_filename = ''
                if excel_row in row_images:
                    for img in row_images[excel_row]:
                        try:
                            # Save image data
                            img_data = img._data()
                            ext = img.format.lower() if img.format else 'png'
                            if ext in ('jpeg', 'jpg'):
                                ext = 'jpg'
                            elif ext not in ('png', 'gif', 'webp', 'bmp'):
                                ext = 'png'
                            unique_name = f"{uuid.uuid4().hex}.{ext}"
                            img_path = os.path.join(app.config['UPLOAD_DIR'], unique_name)
                            with open(img_path, 'wb') as f:
                                f.write(img_data)
                            image_filename = unique_name
                            created_images.append(unique_name)
                            with_images += 1
                            break  # take first image per row
                        except Exception:
                            pass

                # Check if product already exists (same name + code)
                existing = Product.query.filter_by(name=name, product_code=code).first()
                if existing:
                    # Update existing product
                    existing.specification = spec or existing.specification
                    existing.unit_price = price if price > 0 else existing.unit_price
                    if image_filename:
                        if existing.image:
                            replaced_images.append(existing.image)
                        existing.image = image_filename
                    imported += 1
                else:
                    product = Product(
                        name=name,
                        product_code=code,
                        specification=spec,
                        unit_price=price,
                        image=image_filename,
                    )
                    db.session.add(product)
                    imported += 1

            db.session.commit()
            for old_image in set(replaced_images):
                _remove_product_image_if_unused(old_image)
            flash(f'已导入 {imported} 个产品（其中 {with_images} 个带图片），跳过 {skipped} 个空行。', 'success')

        except Exception as e:
            db.session.rollback()
            for created_image in set(created_images):
                _remove_upload(created_image)
            flash(f'读取 Excel 文件失败：{str(e)}', 'danger')
        finally:
            # Clean up temp file (only if we created it)
            if own_tmp and os.path.exists(tmp_path):
                os.remove(tmp_path)

        return redirect(url_for('product_list'))

    return render_template('product_import.html')


@app.route('/products/add', methods=['GET', 'POST'])
@login_required
def product_add():
    if request.method == 'POST':
        try:
            unit_price = float(request.form.get('unit_price', '0').strip() or '0')
        except ValueError:
            unit_price = 0.0
        try:
            unit_price_rmb = float(request.form.get('unit_price_rmb', '0').strip() or '0')
        except ValueError:
            unit_price_rmb = 0.0
        image_file = request.files.get('image')
        image_filename = _save_upload(image_file) if image_file else ''
        product = Product(
            name=request.form.get('name', '').strip(),
            product_code=request.form.get('product_code', '').strip(),
            specification=request.form.get('specification', '').strip(),
            chinese_name=request.form.get('chinese_name', '').strip(),
            unit_price=unit_price,
            unit_price_rmb=unit_price_rmb,
            notes=request.form.get('notes', '').strip(),
            image=image_filename,
        )
        if not product.name:
            _remove_upload(image_filename)
            flash('产品名称不能为空。', 'danger')
            return render_template('product_form.html', product=product, editing=False)
        try:
            db.session.add(product)
            db.session.flush()
            _audit('create', 'product', product.id, f'新增产品：{product.name}',
                   after=_snapshot(product, [
                       'name', 'chinese_name', 'product_code', 'specification',
                       'unit_price', 'unit_price_rmb', 'notes', 'image', 'active',
                   ]))
            db.session.commit()
        except Exception:
            db.session.rollback()
            _remove_upload(image_filename)
            raise
        flash('产品添加成功。', 'success')
        return redirect(url_for('product_list'))
    return render_template('product_form.html', product=None, editing=False)


@app.route('/products/<int:id>/edit', methods=['GET', 'POST'])
@admin_required
def product_edit(id):
    product = Product.query.get_or_404(id)
    if request.method == 'POST':
        new_name = request.form.get('name', '').strip()
        if not new_name:
            flash('产品名称不能为空。', 'danger')
            return render_template('product_form.html', product=product, editing=True)
        before = _snapshot(product, [
            'name', 'chinese_name', 'product_code', 'specification',
            'unit_price', 'unit_price_rmb', 'notes', 'image', 'active',
        ])
        old_image = product.image or ''
        new_image = ''
        image_file = request.files.get('image')
        if image_file and image_file.filename:
            new_image = _save_upload(image_file)

        product.name = new_name
        product.product_code = request.form.get('product_code', '').strip()
        product.specification = request.form.get('specification', '').strip()
        product.chinese_name = request.form.get('chinese_name', '').strip()
        try:
            product.unit_price_rmb = float(request.form.get('unit_price_rmb', '0').strip() or '0')
        except ValueError:
            product.unit_price_rmb = 0.0
        try:
            product.unit_price = float(request.form.get('unit_price', '0').strip() or '0')
        except ValueError:
            product.unit_price = 0.0
        product.notes = request.form.get('notes', '').strip()
        if new_image:
            product.image = new_image
        try:
            _audit('update', 'product', product.id, f'更新产品：{product.name}',
                   before=before, after=_snapshot(product, [
                       'name', 'chinese_name', 'product_code', 'specification',
                       'unit_price', 'unit_price_rmb', 'notes', 'image', 'active',
                   ]))
            db.session.commit()
        except Exception:
            db.session.rollback()
            _remove_upload(new_image)
            raise
        if new_image and old_image != new_image:
            _remove_product_image_if_unused(old_image)
        flash('产品更新成功。', 'success')
        return redirect(url_for('product_list'))
    return render_template('product_form.html', product=product, editing=True)


@app.route('/products/<int:id>/delete', methods=['POST'])
@admin_required
def product_delete(id):
    product = Product.query.get_or_404(id)
    action, reference_count, image_filename = _retire_or_delete_product(product)
    db.session.commit()
    if action == 'disabled':
        flash(f'产品已有 {reference_count} 条 PI 明细引用，已停用并保留历史数据。', 'warning')
    else:
        _remove_product_image_if_unused(image_filename)
        flash('产品未被业务引用，已删除。', 'success')
    return redirect(url_for('product_list'))


@app.route('/products/batch-delete', methods=['POST'])
@admin_required
def product_batch_delete():
    """Batch delete selected products."""
    ids_str = request.form.get('ids', '')
    if not ids_str:
        flash('未选择产品。', 'danger')
        return redirect(url_for('product_list'))
    ids = list(dict.fromkeys(
        int(i) for i in ids_str.split(',') if i.strip().isdigit()
    ))
    if not ids:
        flash('没有有效的产品编号。', 'danger')
        return redirect(url_for('product_list'))
    disabled_count = 0
    deleted_count = 0
    deleted_images = []
    for pid in ids:
        product = Product.query.get(pid)
        if product:
            action, _reference_count, image_filename = _retire_or_delete_product(product)
            if action == 'disabled':
                disabled_count += 1
            else:
                deleted_count += 1
                deleted_images.append(image_filename)
    db.session.commit()
    for image_filename in set(deleted_images):
        _remove_product_image_if_unused(image_filename)
    flash(f'处理完成：停用 {disabled_count} 个有业务引用的产品，删除 {deleted_count} 个未引用产品。', 'success')
    return redirect(url_for('product_list'))


@app.route('/api/products/add', methods=['POST'])
@login_required
def api_product_add():
    """AJAX endpoint — add a product and return JSON."""
    try:
        unit_price = float(request.form.get('unit_price', '0').strip() or '0')
    except ValueError:
        unit_price = 0.0
    try:
        unit_price_rmb = float(request.form.get('unit_price_rmb', '0').strip() or '0')
    except ValueError:
        unit_price_rmb = 0.0

    image_file = request.files.get('image')
    product = Product(
        name=request.form.get('name', '').strip(),
        product_code=request.form.get('product_code', '').strip(),
        specification=request.form.get('specification', '').strip(),
        chinese_name=request.form.get('chinese_name', '').strip(),
        unit_price=unit_price,
        unit_price_rmb=unit_price_rmb,
        notes=request.form.get('notes', '').strip(),
        image=_save_upload(image_file) if image_file else '',
    )
    if not product.name:
        _remove_upload(product.image)
        return jsonify({'success': False, 'error': '产品名称不能为空。'}), 400

    try:
        db.session.add(product)
        db.session.flush()
        _audit('create', 'product', product.id, f'快速新增产品：{product.name}',
               after=_snapshot(product, [
                   'name', 'chinese_name', 'product_code', 'specification',
                   'unit_price', 'unit_price_rmb', 'notes', 'image', 'active',
               ]))
        db.session.commit()
    except Exception:
        db.session.rollback()
        _remove_upload(product.image)
        raise

    return jsonify({
        'success': True,
        'product': product.to_dict(),
    })


@app.route('/api/products/search')
@login_required
def api_product_search():
    q = request.args.get('q', '').strip()
    picker_mode = request.args.get('picker') == '1'

    def serialize(product):
        code = product.product_code or ''
        return {
            'id': product.id,
            'name': product.name,
            'chinese_name': product.chinese_name or '',
            'code': code,
            'product_code': code,
            'spec': product.specification or '',
            'price': product.unit_price or 0,
            'price_usd': product.unit_price or 0,
            'price_rmb': product.unit_price_rmb or 0,
            'img': product.image or '',
        }

    query = Product.query.filter(Product.active.is_(True))
    if q:
        pattern = f'%{q}%'
        query = query.filter(db.or_(
            Product.name.ilike(pattern),
            Product.chinese_name.ilike(pattern),
            Product.product_code.ilike(pattern),
            Product.specification.ilike(pattern),
        ))
    elif not picker_mode:
        return jsonify([])

    if picker_mode:
        try:
            page = max(1, int(request.args.get('page', 1)))
        except (TypeError, ValueError):
            page = 1
        try:
            per_page = int(request.args.get('per_page', 40))
        except (TypeError, ValueError):
            per_page = 40
        per_page = min(60, max(12, per_page))
        total = query.count()
        pages = max(1, (total + per_page - 1) // per_page)
        page = min(page, pages)
        products = query.order_by(Product.name.asc(), Product.id.asc()).offset(
            (page - 1) * per_page
        ).limit(per_page).all()
        return jsonify({
            'items': [serialize(product) for product in products],
            'page': page,
            'pages': pages,
            'per_page': per_page,
            'total': total,
        })

    products = query.order_by(Product.name.asc(), Product.id.asc()).limit(50).all()
    return jsonify([serialize(product) for product in products])


@app.route('/api/products/<int:id>/update', methods=['POST'])
@admin_required
def api_product_update(id):
    """Inline update product fields. Accepts JSON: {field: value}"""
    product = Product.query.get_or_404(id)
    data = request.get_json(silent=True) or {}
    allowed = {'name', 'product_code', 'specification', 'chinese_name', 'unit_price', 'unit_price_rmb'}
    for field, value in data.items():
        if field not in allowed:
            continue
        if field in ('unit_price', 'unit_price_rmb'):
            try:
                value = float(str(value).replace(',', ''))
            except (ValueError, TypeError):
                return jsonify({'success': False, 'error': '价格格式不正确。'}), 400
        else:
            value = str(value).strip()
            if field == 'name' and not value:
                return jsonify({'success': False, 'error': '名称不能为空。'}), 400
        setattr(product, field, value)
    db.session.commit()
    return jsonify({
        'success': True,
        'product': product.to_dict(),
    })


@app.route('/api/products/<int:id>/copy', methods=['POST'])
@admin_required
def api_product_copy(id):
    """Duplicate a product with same info."""
    original = Product.query.get_or_404(id)
    # Generate unique name and code to avoid conflicts
    new_name = original.name + ' (Copy)'
    new_code = original.product_code + '_copy' if original.product_code else 'copy'
    new_image = _copy_product_image(original.image)
    new_product = Product(
        name=new_name,
        product_code=new_code,
        specification=original.specification,
        chinese_name=original.chinese_name,
        unit_price=original.unit_price,
        unit_price_rmb=original.unit_price_rmb,
        notes=original.notes,
        image=new_image,
    )
    try:
        db.session.add(new_product)
        db.session.flush()
        _audit('copy', 'product', new_product.id,
               f'复制产品：{original.name} → {new_product.name}',
               after=_snapshot(new_product, [
                   'name', 'chinese_name', 'product_code', 'specification',
                   'unit_price', 'unit_price_rmb', 'notes', 'image', 'active',
               ]))
        db.session.commit()
    except Exception:
        db.session.rollback()
        _remove_upload(new_image)
        raise
    return jsonify({
        'success': True,
        'product': new_product.to_dict(),
    })


@app.route('/api/products/<int:id>/delete', methods=['POST'])
@admin_required
def api_product_delete(id):
    """Disable referenced products; delete only products without PI history."""
    product = Product.query.get_or_404(id)
    action, reference_count, image_filename = _retire_or_delete_product(product)
    db.session.commit()
    if action == 'deleted':
        _remove_product_image_if_unused(image_filename)
        message = '产品未被业务引用，已删除。'
    else:
        message = f'产品已有 {reference_count} 条 PI 明细引用，已停用。'
    return jsonify({
        'success': True,
        'action': action,
        'reference_count': reference_count,
        'message': message,
    })


@app.route('/api/products/<int:id>/enable', methods=['POST'])
@admin_required
def api_product_enable(id):
    product = Product.query.get_or_404(id)
    before = _snapshot(product, ['name', 'product_code', 'active'])
    product.active = True
    _audit('enable', 'product', product.id, f'重新启用产品：{product.name}',
           before=before, after=_snapshot(product, ['name', 'product_code', 'active']))
    db.session.commit()
    return jsonify({'success': True, 'message': '产品已重新启用。'})


@app.route('/api/translate', methods=['POST'])
@login_required
def api_translate():
    """Translate English text to Chinese using Google Translate API."""
    import urllib.request
    import json
    text = request.form.get('text', '').strip()
    if not text:
        return jsonify({'success': False, 'error': '未提供文本。'}), 400
    try:
        url = 'https://translate.googleapis.com/translate_a/single?client=gtx&sl=en&tl=zh-CN&dt=t&q=' + urllib.parse.quote(text)
        import ssl
        ctx = ssl.create_default_context()
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5, context=ctx) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        # Extract translated sentences from response
        result = ''.join([s[0] for s in data[0] if s[0]]) if data and data[0] else text
        return jsonify({'success': True, 'translated': result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/uploads/<filename>')
@login_required
def uploaded_file(filename):
    safe_name = secure_filename(filename)
    if not safe_name:
        abort(404)
    product_image = Product.query.filter_by(image=safe_name).first()
    customer_images = Customer.query.filter_by(image=safe_name).all()
    if not product_image and not any(can_access_customer(c) for c in customer_images):
        abort(404)
    filepath = os.path.join(current_app.config['UPLOAD_DIR'], safe_name)
    if not os.path.isfile(filepath):
        abort(404)
    return send_file(filepath)


@app.route('/uploads/thumb/<filename>')
@login_required
def uploaded_product_thumbnail(filename):
    """Serve a small product-list image while retaining the original for documents."""
    safe_name = secure_filename(filename)
    if not safe_name or not Product.query.filter_by(image=safe_name).first():
        abort(404)
    source_path = os.path.join(current_app.config['UPLOAD_DIR'], safe_name)
    if not os.path.isfile(source_path):
        abort(404)
    return send_file(
        _ensure_product_thumbnail(safe_name, source_path),
        conditional=True,
        max_age=604800,
    )


# ═══════════════════════════════════════════════════════════════════════
#  ROUTES — Salespersons
# ═══════════════════════════════════════════════════════════════════════

@app.route('/salespersons')
@admin_required
def salesperson_list():
    salespersons = Salesperson.query.order_by(Salesperson.name).all()
    # Compute customer counts per salesperson
    sp_stats = {}
    for sp in salespersons:
        total_cust = Customer.query.filter_by(salesperson=sp.name).filter(Customer.deleted_at.is_(None)).count()
        paid_cust = db.session.query(func.count(func.distinct(PI.customer_id))).filter(
            PI.salesperson == sp.name,
            PI.paid == True,
            PI.deleted_at.is_(None)
        ).scalar() or 0
        sp_stats[sp.name] = {'total_customers': total_cust, 'paid_customers': paid_cust}
    return render_template('salesperson_list.html', salespersons=salespersons, sp_stats=sp_stats)


@app.route('/salespersons/add', methods=['GET', 'POST'])
@admin_required
def salesperson_add():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        if not name:
            flash('业务员姓名不能为空。', 'danger')
            return render_template('salesperson_form.html', sp=None, editing=False)
        if Salesperson.query.filter_by(name=name).first():
            flash('业务员姓名已存在。', 'danger')
            return render_template('salesperson_form.html', sp=None, editing=False)
        sp = Salesperson(
            name=name,
            phone=request.form.get('phone', '').strip(),
            email=request.form.get('email', '').strip(),
            dingtalk_user_id=request.form.get('dingtalk_user_id', '').strip(),
            notes=request.form.get('notes', '').strip(),
        )
        db.session.add(sp)
        db.session.commit()
        flash('业务员添加成功。', 'success')
        return redirect(url_for('salesperson_list'))
    return render_template('salesperson_form.html', sp=None, editing=False)


@app.route('/salespersons/<int:id>/edit', methods=['GET', 'POST'])
@admin_required
def salesperson_edit(id):
    sp = Salesperson.query.get_or_404(id)
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        if not name:
            flash('业务员姓名不能为空。', 'danger')
            return render_template('salesperson_form.html', sp=sp, editing=True)
        existing = Salesperson.query.filter_by(name=name).first()
        if existing and existing.id != sp.id:
            flash('业务员姓名已存在。', 'danger')
            return render_template('salesperson_form.html', sp=sp, editing=True)
        sp.name = name
        sp.phone = request.form.get('phone', '').strip()
        sp.email = request.form.get('email', '').strip()
        sp.dingtalk_user_id = request.form.get('dingtalk_user_id', '').strip()
        sp.notes = request.form.get('notes', '').strip()
        db.session.commit()
        flash('业务员更新成功。', 'success')
        return redirect(url_for('salesperson_list'))
    return render_template('salesperson_form.html', sp=sp, editing=True)


@app.route('/salespersons/<int:id>/delete', methods=['POST'])
@admin_required
def salesperson_delete(id):
    sp = Salesperson.query.get_or_404(id)
    db.session.delete(sp)
    db.session.commit()
    flash('业务员删除成功。', 'success')
    return redirect(url_for('salesperson_list'))


# ═══════════════════════════════════════════════════════════════════════
#  ROUTES — Users (仅管理员可操作)
# ═══════════════════════════════════════════════════════════════════════

@app.route('/users')
@admin_required
def user_list():
    if not is_admin():
        flash('无权执行此操作。', 'danger')
        return redirect(url_for('index'))
    users = User.query.order_by(User.created_at.desc()).all()
    return render_template('user_list.html', users=users)


@app.route('/users/add', methods=['GET', 'POST'])
@admin_required
def user_add():
    if not is_admin():
        flash('无权执行此操作。', 'danger')
        return redirect(url_for('index'))
    if request.method == 'POST':
        account = request.form.get('account', '').strip()
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        role = request.form.get('role', 'salesperson').strip()
        salesperson_name = request.form.get('salesperson_name', '').strip()
        if not _valid_account(account) or not username or not password:
            flash('账号、用户名和密码不能为空，账号最多 64 个字符。', 'danger')
            return render_template('user_form.html', u=None, editing=False)
        if len(password) < 10:
            flash('临时密码至少需要 10 个字符。', 'danger')
            return render_template('user_form.html', u=None, editing=False)
        if _find_user_by_account(account):
            flash('账号已存在。', 'danger')
            return render_template('user_form.html', u=None, editing=False)
        if User.query.filter_by(username=username).first():
            flash('用户名已存在。', 'danger')
            return render_template('user_form.html', u=None, editing=False)
        db.session.add(User(
            account=account,
            username=username,
            password_hash=generate_password_hash(password),
            role=role,
            salesperson_name=salesperson_name if role == 'salesperson' else '',
            must_change_password=True,
        ))
        db.session.commit()
        flash('用户已创建。', 'success')
        return redirect(url_for('user_list'))
    return render_template('user_form.html', u=None, editing=False)


@app.route('/users/<int:id>/edit', methods=['GET', 'POST'])
@admin_required
def user_edit(id):
    if not is_admin():
        flash('无权执行此操作。', 'danger')
        return redirect(url_for('index'))
    user = User.query.get_or_404(id)
    pw_hint = '留空则保持当前密码'
    if request.method == 'POST':
        account = request.form.get('account', '').strip()
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        role = request.form.get('role', 'salesperson').strip()
        salesperson_name = request.form.get('salesperson_name', '').strip()
        if not _valid_account(account) or not username:
            flash('账号和用户名不能为空，账号最多 64 个字符。', 'danger')
            return render_template('user_form.html', u=user, editing=True, pw_hint=pw_hint)
        existing_account = _find_user_by_account(account)
        if existing_account and existing_account.id != user.id:
            flash('账号已存在。', 'danger')
            return render_template('user_form.html', u=user, editing=True, pw_hint=pw_hint)
        existing = User.query.filter_by(username=username).first()
        if existing and existing.id != user.id:
            flash('用户名已存在。', 'danger')
            return render_template('user_form.html', u=user, editing=True, pw_hint=pw_hint)
        if password and len(password) < 10:
            flash('临时密码至少需要 10 个字符。', 'danger')
            return render_template('user_form.html', u=user, editing=True, pw_hint=pw_hint)
        user.account = account
        user.username = username
        if password:
            user.password_hash = generate_password_hash(password)
            user.must_change_password = True
        user.role = role
        user.salesperson_name = salesperson_name if role == 'salesperson' else ''
        user.auth_version += 1
        db.session.commit()
        flash('用户已更新。', 'success')
        return redirect(url_for('user_list'))
    return render_template('user_form.html', u=user, editing=True, pw_hint=pw_hint)


@app.route('/users/<int:id>/delete', methods=['POST'])
@admin_required
def user_delete(id):
    if not is_admin():
        flash('无权执行此操作。', 'danger')
        return redirect(url_for('index'))
    user = User.query.get_or_404(id)
    if (user.account or '').lower() == 'admin':
        flash('不能删除管理员账号。', 'danger')
        return redirect(url_for('user_list'))
    db.session.delete(user)
    db.session.commit()
    flash('用户已删除。', 'success')
    return redirect(url_for('user_list'))


@app.route('/users/<int:id>/toggle-active', methods=['POST'])
@admin_required
def user_toggle_active(id):
    if not is_admin():
        flash('无权执行此操作。', 'danger')
        return redirect(url_for('index'))
    user = User.query.get_or_404(id)
    if (user.account or '').lower() == 'admin':
        flash('不能停用管理员账号。', 'danger')
        return redirect(url_for('user_list'))
    user.active = not user.active
    user.auth_version += 1
    db.session.commit()
    status = '启用' if user.active else '停用'
    flash(f'用户“{user.username}”已{status}。', 'success')
    return redirect(url_for('user_list'))


@app.route('/users/<int:id>/reset-password', methods=['POST'])
@admin_required
def user_reset_password(id):
    if not is_admin():
        flash('无权执行此操作。', 'danger')
        return redirect(url_for('index'))
    user = User.query.get_or_404(id)
    new_pw = request.form.get('new_password', '').strip()
    if not new_pw or len(new_pw) < 10:
        flash('密码至少需要 10 个字符。', 'danger')
        return redirect(url_for('user_list'))
    user.password_hash = generate_password_hash(new_pw)
    user.must_change_password = True
    user.auth_version += 1
    db.session.commit()
    flash(f'用户“{user.username}”的密码已重置。', 'success')
    return redirect(url_for('user_list'))


# ═══════════════════════════════════════════════════════════════════════
#  ROUTES — Field management / Accounts (仅管理员可操作)
# ═══════════════════════════════════════════════════════════════════════


def _field_options(field_key):
    if field_key not in MANAGED_FIELD_LABELS:
        return []
    return FieldOption.query.filter_by(field_key=field_key).order_by(
        FieldOption.sort_order, FieldOption.id
    ).all()


def _managed_field_value(field_key, raw_value, existing_value=''):
    """Accept only a configured choice, while preserving a legacy PI value."""
    value = (raw_value or '').strip()
    existing = (existing_value or '').strip()
    if not value:
        return ''
    if existing and value == existing:
        return value
    if field_key not in MANAGED_FIELD_LABELS:
        raise ValueError('不支持该字段。')
    if not FieldOption.query.filter_by(field_key=field_key, value=value).first():
        raise ValueError(f'请选择字段管理中已有的{MANAGED_FIELD_LABELS[field_key]}。')
    return value


def _selectable_or_manual_field(field_key, raw_value):
    """Store a configured choice or a one-off value entered for this PI."""
    if field_key not in {'price_terms', 'delivery_time'}:
        raise ValueError('不支持该字段。')
    value = (raw_value or '').strip()
    if len(value) > 200:
        raise ValueError(f'{MANAGED_FIELD_LABELS[field_key]}不能超过 200 个字符。')
    return value


def _managed_field_english(field_key, raw_value, existing_value='', existing_english=''):
    """Resolve and snapshot the English label for a managed PI field."""
    value = _managed_field_value(field_key, raw_value, existing_value)
    if not value:
        return ''
    existing = (existing_value or '').strip()
    existing_en = (existing_english or '').strip()
    if existing and value == existing and existing_en:
        return existing_en
    option = FieldOption.query.filter_by(field_key=field_key, value=value).first()
    return ((option.english_value if option else '') or value).strip()


def _require_customer_adjustment_type(amount, value):
    """A non-zero customer charge/discount must have an outward label."""
    if abs(float(amount or 0)) > 0.000001 and not (value or '').strip():
        raise ValueError('填写客户费用/折扣金额后，必须选择对应类型。')


@app.route('/accounts')
@app.route('/field-management')
@admin_required
def account_list():
    if not is_admin(): return redirect(url_for('index'))
    accounts = Account.query.order_by(Account.name).all()
    return render_template(
        'field_management.html',
        accounts=accounts,
        shipping_note_options=_field_options('shipping_note'),
        expense_category_options=_field_options('expense_category'),
        price_terms_options=_field_options('price_terms'),
        delivery_time_options=_field_options('delivery_time'),
    )


@app.route('/field-options/add', methods=['POST'])
@admin_required
def field_option_add():
    field_key = request.form.get('field_key', '').strip()
    value = request.form.get('value', '').strip()
    english_value = request.form.get('english_value', '').strip()
    if field_key not in MANAGED_FIELD_LABELS:
        abort(400)
    if not value:
        flash('选项内容不能为空。', 'danger')
        return redirect(url_for('account_list', _anchor=field_key))
    if len(value) > 200:
        flash('选项内容不能超过 200 个字符。', 'danger')
        return redirect(url_for('account_list', _anchor=field_key))
    if field_key in MANAGED_FIELDS_WITH_ENGLISH and not english_value:
        flash('对外 PI 使用的英文名称不能为空。', 'danger')
        return redirect(url_for('account_list', _anchor=field_key))
    if len(english_value) > 200:
        flash('英文名称不能超过 200 个字符。', 'danger')
        return redirect(url_for('account_list', _anchor=field_key))
    if FieldOption.query.filter_by(field_key=field_key, value=value).first():
        flash('该选项已经存在。', 'warning')
        return redirect(url_for('account_list', _anchor=field_key))
    max_order = db.session.query(func.max(FieldOption.sort_order)).filter_by(field_key=field_key).scalar() or 0
    option = FieldOption(
        field_key=field_key, value=value, english_value=english_value,
        sort_order=max_order + 10,
    )
    db.session.add(option)
    db.session.flush()
    _audit('create', 'field_option', option.id,
           f'新增{MANAGED_FIELD_LABELS[field_key]}选项：{value}',
           after=_snapshot(option, ['field_key', 'value', 'english_value', 'sort_order']))
    db.session.commit()
    flash('字段选项已添加。', 'success')
    return redirect(url_for('account_list', _anchor=field_key))


@app.route('/field-options/<int:id>/edit', methods=['POST'])
@admin_required
def field_option_edit(id):
    option = FieldOption.query.get_or_404(id)
    value = request.form.get('value', '').strip()
    english_value = request.form.get('english_value', '').strip()
    if not value:
        flash('选项内容不能为空。', 'danger')
        return redirect(url_for('account_list', _anchor=option.field_key))
    if len(value) > 200:
        flash('选项内容不能超过 200 个字符。', 'danger')
        return redirect(url_for('account_list', _anchor=option.field_key))
    if option.field_key in MANAGED_FIELDS_WITH_ENGLISH and not english_value:
        flash('对外 PI 使用的英文名称不能为空。', 'danger')
        return redirect(url_for('account_list', _anchor=option.field_key))
    if len(english_value) > 200:
        flash('英文名称不能超过 200 个字符。', 'danger')
        return redirect(url_for('account_list', _anchor=option.field_key))
    duplicate = FieldOption.query.filter(
        FieldOption.field_key == option.field_key,
        FieldOption.value == value,
        FieldOption.id != option.id,
    ).first()
    if duplicate:
        flash('该选项已经存在。', 'warning')
        return redirect(url_for('account_list', _anchor=option.field_key))
    before = _snapshot(option, ['field_key', 'value', 'english_value', 'sort_order'])
    option.value = value
    option.english_value = english_value
    _audit('update', 'field_option', option.id,
           f'修改{MANAGED_FIELD_LABELS[option.field_key]}选项：{value}',
           before=before, after=_snapshot(option, ['field_key', 'value', 'english_value', 'sort_order']))
    db.session.commit()
    flash('字段选项已更新；历史 PI 内容不会改变。', 'success')
    return redirect(url_for('account_list', _anchor=option.field_key))


@app.route('/field-options/<int:id>/delete', methods=['POST'])
@admin_required
def field_option_delete(id):
    option = FieldOption.query.get_or_404(id)
    field_key = option.field_key
    before = _snapshot(option, ['field_key', 'value', 'english_value', 'sort_order'])
    _audit('delete', 'field_option', option.id,
           f'删除{MANAGED_FIELD_LABELS[field_key]}选项：{option.value}', before=before)
    db.session.delete(option)
    db.session.commit()
    flash('字段选项已删除；历史 PI 内容不受影响。', 'success')
    return redirect(url_for('account_list', _anchor=field_key))

@app.route('/accounts/add', methods=['GET', 'POST'])
@admin_required
def account_add():
    if not is_admin(): return redirect(url_for('index'))
    if request.method == 'POST':
        if not _require_current_password():
            return render_template('account_form.html', a=None, editing=False), 403
        currency = request.form.get('currency', 'USD').strip().upper()
        if currency not in {'USD', 'RMB'}:
            flash('收款账户币种只能选择美元或人民币。', 'danger')
            return render_template('account_form.html', a=None, editing=False), 400
        account = Account(
            name=request.form.get('name','').strip(),
            company_name=request.form.get('company_name','').strip(),
            country_region=request.form.get('country_region','').strip(),
            beneficiary_address=request.form.get('beneficiary_address','').strip(),
            bank_name=request.form.get('bank_name','').strip(),
            bank_address=request.form.get('bank_address','').strip(),
            account_no=request.form.get('account_no','').strip(),
            swift_code=request.form.get('swift_code','').strip(),
            bank_code=request.form.get('bank_code','').strip(),
            branch_code=request.form.get('branch_code','').strip(),
            brand=request.form.get('brand','klista').strip(),
            currency=currency,
            notes=request.form.get('notes','').strip(),
        )
        db.session.add(account)
        db.session.flush()
        _audit('create', 'account', account.id, f'新增收款账户：{account.name}',
               after=_snapshot(account, ['name', 'company_name', 'country_region',
                                           'beneficiary_address', 'bank_name', 'bank_address',
                                           'account_no', 'swift_code', 'bank_code', 'branch_code',
                                           'brand', 'currency']))
        db.session.commit()
        flash('收款账户已添加。', 'success')
        return redirect(url_for('account_list'))
    return render_template('account_form.html', a=None, editing=False)

@app.route('/accounts/<int:id>/edit', methods=['GET', 'POST'])
@admin_required
def account_edit(id):
    if not is_admin(): return redirect(url_for('index'))
    a = Account.query.get_or_404(id)
    if request.method == 'POST':
        if not _require_current_password():
            return render_template('account_form.html', a=a, editing=True), 403
        currency = request.form.get('currency', 'USD').strip().upper()
        if currency not in {'USD', 'RMB'}:
            flash('收款账户币种只能选择美元或人民币。', 'danger')
            return render_template('account_form.html', a=a, editing=True), 400
        account_fields = ['name', 'company_name', 'country_region', 'beneficiary_address',
                          'bank_name', 'bank_address', 'account_no', 'swift_code',
                          'bank_code', 'branch_code', 'brand', 'currency', 'notes']
        before = _snapshot(a, account_fields)
        a.name = request.form.get('name','').strip()
        a.company_name = request.form.get('company_name','').strip()
        a.country_region = request.form.get('country_region','').strip()
        a.beneficiary_address = request.form.get('beneficiary_address','').strip()
        a.bank_name = request.form.get('bank_name','').strip()
        a.bank_address = request.form.get('bank_address','').strip()
        a.account_no = request.form.get('account_no','').strip()
        a.swift_code = request.form.get('swift_code','').strip()
        a.bank_code = request.form.get('bank_code','').strip()
        a.branch_code = request.form.get('branch_code','').strip()
        a.brand = request.form.get('brand','klista').strip()
        a.currency = currency
        a.notes = request.form.get('notes','').strip()
        _audit('update', 'account', a.id, f'修改收款账户：{a.name}', before=before,
               after=_snapshot(a, account_fields))
        db.session.commit()
        flash('收款账户已更新。', 'success')
        return redirect(url_for('account_list'))
    return render_template('account_form.html', a=a, editing=True)

@app.route('/accounts/<int:id>/delete', methods=['POST'])
@admin_required
def account_delete(id):
    if not is_admin(): return redirect(url_for('index'))
    if not _require_current_password():
        return redirect(url_for('account_list'))
    account = Account.query.get_or_404(id)
    if request.form.get('confirm_value', '').strip() != account.name:
        flash('输入内容与账户名称不一致，未执行删除。', 'danger')
        return redirect(url_for('account_list'))
    before = _snapshot(account, ['name', 'company_name', 'country_region',
                                 'beneficiary_address', 'bank_name', 'bank_address',
                                 'account_no', 'swift_code', 'bank_code', 'branch_code',
                                 'brand', 'currency'])
    _audit('delete', 'account', account.id, f'删除收款账户：{account.name}', before=before)
    db.session.delete(account)
    db.session.commit()
    flash('收款账户已删除。', 'success')
    return redirect(url_for('account_list'))


# ═══════════════════════════════════════════════════════════════════════
#  ROUTES — Audit log and recycle bin (仅管理员可操作)
# ═══════════════════════════════════════════════════════════════════════

@app.route('/audit-logs')
@admin_required
def audit_logs():
    entity_type = request.args.get('entity_type', '').strip()
    action = request.args.get('action', '').strip()
    query = AuditLog.query
    if entity_type:
        query = query.filter(AuditLog.entity_type == entity_type)
    if action:
        query = query.filter(AuditLog.action == action)
    page = max(request.args.get('page', 1, type=int), 1)
    per_page = 100
    total = query.count()
    logs = query.order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).offset((page - 1) * per_page).limit(per_page).all()
    return render_template('audit_logs.html', logs=logs, total=total, page=page,
                           total_pages=max(1, (total + per_page - 1) // per_page),
                           entity_type=entity_type, action=action)


@app.route('/recycle-bin')
@admin_required
def recycle_bin():
    customers = Customer.query.filter(Customer.deleted_at.isnot(None)).order_by(Customer.deleted_at.desc()).all()
    pis = PI.query.options(joinedload(PI.customer)).filter(PI.deleted_at.isnot(None)).order_by(PI.deleted_at.desc()).all()
    payments = Payment.query.options(joinedload(Payment.pi)).filter(Payment.deleted_at.isnot(None)).order_by(Payment.deleted_at.desc()).all()
    return render_template('recycle_bin.html', customers=customers, pis=pis, payments=payments)


@app.route('/recycle-bin/customer/<int:id>/restore', methods=['POST'])
@admin_required
def restore_customer(id):
    customer = Customer.query.get_or_404(id)
    if customer.deleted_at is None:
        flash('该客户已经是正常状态。', 'info')
        return redirect(url_for('recycle_bin'))
    before = _snapshot(customer, ['name', 'salesperson', 'deleted_at'])
    deleted_marker = customer.deleted_at
    customer.deleted_at = None
    customer.version = (customer.version or 1) + 1
    # Only restore PIs deleted by the same customer-delete operation. A PI that
    # had already been deleted independently must remain in the recycle bin.
    restored_pis = PI.query.filter_by(customer_id=customer.id).filter(PI.deleted_at == deleted_marker).all()
    for pi in restored_pis:
        pi.deleted_at = None
        pi.version = (pi.version or 1) + 1
    _recalculate_customer_deal(customer)
    _audit('restore', 'customer', customer.id, f'恢复客户 {customer.name} 及 {len(restored_pis)} 份 PI', before=before,
           after=_snapshot(customer, ['name', 'salesperson', 'deleted_at']))
    db.session.commit()
    flash('客户及关联 PI 已恢复。', 'success')
    return redirect(url_for('recycle_bin'))


@app.route('/recycle-bin/pi/<int:id>/restore', methods=['POST'])
@admin_required
def restore_pi(id):
    pi = PI.query.get_or_404(id)
    if pi.deleted_at is None:
        flash('该 PI 已经是正常状态。', 'info')
        return redirect(url_for('recycle_bin'))
    customer = Customer.query.get(pi.customer_id)
    if not customer or customer.deleted_at is not None:
        flash('请先恢复客户，再恢复该 PI。', 'danger')
        return redirect(url_for('recycle_bin'))
    before = _snapshot(pi, ['pi_number', 'customer_id', 'salesperson', 'deleted_at'])
    pi.deleted_at = None
    pi.version = (pi.version or 1) + 1
    _recalculate_customer_deal(customer)
    _audit('restore', 'pi', pi.id, f'恢复 PI：{pi.pi_number}', before=before,
           after=_snapshot(pi, ['pi_number', 'customer_id', 'salesperson', 'deleted_at']))
    db.session.commit()
    flash('PI 已恢复。', 'success')
    return redirect(url_for('recycle_bin'))


@app.route('/recycle-bin/payment/<int:id>/restore', methods=['POST'])
@admin_required
def restore_payment(id):
    payment = Payment.query.get_or_404(id)
    if payment.deleted_at is None:
        flash('该回款已经是正常状态。', 'info')
        return redirect(url_for('recycle_bin'))
    pi = PI.query.get(payment.pi_id)
    if not pi or pi.deleted_at is not None:
        flash('请先恢复 PI，再恢复该回款。', 'danger')
        return redirect(url_for('recycle_bin'))
    duplicate = Payment.query.filter(Payment.id != payment.id, Payment.deleted_at.is_(None),
                                     Payment.order_no_normalized == payment.order_no_normalized).first()
    if duplicate:
        flash('无法恢复：已有正常回款使用相同流水号。', 'danger')
        return redirect(url_for('recycle_bin'))
    before = _snapshot(payment, ['pi_id', 'amount', 'fee', 'order_no', 'deleted_at'])
    payment.deleted_at = None
    _recalculate_pi_payments(pi)
    customer = Customer.query.get(pi.customer_id)
    if customer:
        _recalculate_customer_deal(customer)
    _audit('restore', 'payment', payment.id, f'恢复回款：{payment.order_no}', before=before,
           after=_snapshot(payment, ['pi_id', 'amount', 'fee', 'order_no', 'deleted_at']))
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        flash('无法恢复：该回款与现有记录冲突。', 'danger')
        return redirect(url_for('recycle_bin'))
    flash('回款已恢复，相关金额已重新计算；采购、装箱、报关和发货记录均未修改。', 'success')
    return redirect(url_for('recycle_bin'))


# ═══════════════════════════════════════════════════════════════════════
#  ROUTES — Suppliers
# ═══════════════════════════════════════════════════════════════════════

@app.route('/suppliers')
@admin_required
def supplier_list():
    if not is_admin(): return redirect(url_for('index'))
    suppliers = Supplier.query.order_by(Supplier.name).all()
    return render_template('supplier_list.html', suppliers=suppliers)

@app.route('/suppliers/<int:id>')
@admin_required
def supplier_detail(id):
    """Supplier detail page with procurement history and outstanding balance."""
    if not is_admin(): return redirect(url_for('index'))
    s = Supplier.query.get_or_404(id)
    # All procurement items for this supplier, with PI info
    procs = Procurement.query.options(
        db.joinedload(Procurement.pi),
        db.joinedload(Procurement.pi_item).joinedload(PIItem.product)
    ).filter_by(supplier_id=id).order_by(Procurement.created_at.desc()).all()

    # Calculate totals
    total_proc = sum(p.total for p in procs)
    # Group by PI
    pi_groups = {}
    for p in procs:
        pi_id = p.pi_id
        if pi_id not in pi_groups:
            pi_groups[pi_id] = {'pi': p.pi, 'proc_items': [], 'subtotal': 0}
        pi_groups[pi_id]['proc_items'].append(p)
        pi_groups[pi_id]['subtotal'] += p.total

    return render_template('supplier_detail.html', supplier=s, procs=procs,
                           total_proc=total_proc, pi_groups=pi_groups,
                           count=len(procs))


@app.route('/suppliers/<int:id>/statement')
@admin_required
def supplier_statement(id):
    """Generate and download supplier statement PDF."""
    if not is_admin(): return redirect(url_for('index'))
    s = Supplier.query.get_or_404(id)
    procs = Procurement.query.options(
        db.joinedload(Procurement.pi),
        db.joinedload(Procurement.pi_item).joinedload(PIItem.product)
    ).filter_by(supplier_id=id).order_by(Procurement.created_at.asc()).all()
    total_proc = sum(p.total for p in procs)

    pdf_dir = os.path.join(APP_ROOT, 'pdf')
    os.makedirs(pdf_dir, exist_ok=True)
    safe_name = secure_filename(s.name)
    filename = f'statement_{safe_name}_{datetime.utcnow().strftime("%Y%m%d_%H%M%S")}.pdf'
    filepath = os.path.join(pdf_dir, filename)

    generate_supplier_statement(s, procs, total_proc, filepath)

    return send_file(
        filepath, as_attachment=True,
        download_name=f'对账单_{s.name}_{datetime.utcnow().strftime("%Y%m%d")}.pdf',
        mimetype='application/pdf'
    )


@app.route('/suppliers/add', methods=['GET', 'POST'])
@admin_required
def supplier_add():
    if not is_admin(): return redirect(url_for('index'))
    if request.method == 'POST':
        s = Supplier(
            name=request.form.get('name','').strip(),
            contact_person=request.form.get('contact_person','').strip(),
            phone=request.form.get('phone','').strip(),
            email=request.form.get('email','').strip(),
            address=request.form.get('address','').strip(),
            notes=request.form.get('notes','').strip(),
        )
        if not s.name:
            flash('供应商名称不能为空。', 'danger')
            return render_template('supplier_form.html', s=s, editing=False)
        db.session.add(s)
        db.session.commit()
        flash('供应商已添加。', 'success')
        return redirect(url_for('supplier_list'))
    return render_template('supplier_form.html', s=None, editing=False)

@app.route('/suppliers/<int:id>/edit', methods=['GET', 'POST'])
@admin_required
def supplier_edit(id):
    if not is_admin(): return redirect(url_for('index'))
    s = Supplier.query.get_or_404(id)
    if request.method == 'POST':
        s.name = request.form.get('name','').strip()
        s.contact_person = request.form.get('contact_person','').strip()
        s.phone = request.form.get('phone','').strip()
        s.email = request.form.get('email','').strip()
        s.address = request.form.get('address','').strip()
        s.notes = request.form.get('notes','').strip()
        if not s.name:
            flash('供应商名称不能为空。', 'danger')
            return render_template('supplier_form.html', s=s, editing=True)
        db.session.commit()
        flash('供应商已更新。', 'success')
        return redirect(url_for('supplier_list'))
    return render_template('supplier_form.html', s=s, editing=True)

@app.route('/suppliers/<int:id>/delete', methods=['POST'])
@admin_required
def supplier_delete(id):
    if not is_admin(): return redirect(url_for('index'))
    db.session.delete(Supplier.query.get_or_404(id))
    db.session.commit()
    flash('供应商已删除。', 'success')
    return redirect(url_for('supplier_list'))

@app.route('/api/suppliers', methods=['GET', 'POST'])
@admin_required
def api_supplier_list():
    if not is_admin():
        return jsonify({'success': False, 'error': '仅管理员可操作'}), 403
    if request.method == 'POST':
        data = request.get_json(silent=True) or {}
        name = str(data.get('name', '') or '').strip()
        if not name:
            return jsonify({'success': False, 'error': '供应商名称不能为空。'}), 400
        if len(name) > 200:
            return jsonify({'success': False, 'error': '供应商名称不能超过 200 个字符。'}), 400
        existing = Supplier.query.filter(func.lower(Supplier.name) == name.lower()).first()
        if existing:
            return jsonify({
                'success': False,
                'error': '该供应商名称已经存在。',
                'supplier': existing.to_dict(),
            }), 409
        supplier = Supplier(
            name=name,
            contact_person=str(data.get('contact_person', '') or '').strip()[:100],
            phone=str(data.get('phone', '') or '').strip()[:50],
            email=str(data.get('email', '') or '').strip()[:200],
            address=str(data.get('address', '') or '').strip(),
            notes=str(data.get('notes', '') or '').strip(),
        )
        db.session.add(supplier)
        db.session.flush()
        _audit(
            'create', 'supplier', supplier.id,
            f'在采购页面新增供应商 {supplier.name}',
            after=_snapshot(supplier, [
                'name', 'contact_person', 'phone', 'email', 'address', 'notes',
            ]),
        )
        db.session.commit()
        return jsonify({'success': True, 'supplier': supplier.to_dict()}), 201
    suppliers = Supplier.query.order_by(Supplier.name).all()
    return jsonify([s.to_dict() for s in suppliers])


# ═══════════════════════════════════════════════════════════════════════
#  ROUTES — PI (Proforma Invoice)
# ═══════════════════════════════════════════════════════════════════════

@app.route('/pi/create', methods=['GET', 'POST'])
@login_required
def pi_create():
    customers = filter_by_user(Customer.query, Customer, 'salesperson').order_by(Customer.name).all()
    admin_flag = is_admin()

    if request.method == 'POST':
        customer_id = request.form.get('customer_id', type=int)
        salesperson = request.form.get('salesperson', '').strip()
        payment_terms = request.form.get('payment_terms', '').strip()
        try:
            price_terms = _selectable_or_manual_field(
                'price_terms', request.form.get('price_terms', '')
            )
            delivery_time = _selectable_or_manual_field(
                'delivery_time', request.form.get('delivery_time', '')
            )
        except ValueError as exc:
            flash(str(exc), 'danger')
            return redirect(url_for('pi_create'))
        bank_info = request.form.get('bank_info', '').strip()
        notes = request.form.get('notes', '').strip()
        issue_date_str = request.form.get('issue_date', '').strip()
        currency = request.form.get('currency', 'USD').strip()
        try:
            business_exchange_rate = _nonnegative_float(
                request.form.get('exchange_rate', str(_get_exchange_rate())),
                '本单业务汇率',
            )
        except ValueError as exc:
            flash(str(exc), 'danger')
            return redirect(url_for('pi_create'))
        if business_exchange_rate <= 0:
            flash('本单业务汇率必须大于 0。', 'danger')
            return redirect(url_for('pi_create'))
        company = request.form.get('company', 'klista').strip()
        account_id = request.form.get('account_id', type=int)
        selected_account = db.session.get(Account, account_id) if account_id else None
        if not is_admin() and selected_account:
            currency = selected_account.currency or 'USD'
            company = selected_account.brand or 'klista'
        if currency not in {'USD', 'RMB'} or company not in {'klista', 'qisuo'}:
            abort(400)

        if not customer_id:
            flash('请选择客户。', 'danger')
            return render_template('create_pi.html', customers=customers,
                                   pi=None,
                                   today=date.today().strftime('%Y-%m-%d'),
                                   selected_customer_id=None,
                                   is_admin=admin_flag)

        customer = Customer.query.get_or_404(customer_id)
        require_customer_access(customer)
        if not is_admin():
            salesperson = current_salesperson_name()

        if not salesperson:
            flash('请选择业务员。', 'danger')
            return render_template('create_pi.html', customers=customers,
                                   pi=None,
                                   today=date.today().strftime('%Y-%m-%d'),
                                   selected_customer_id=customer_id,
                                   is_admin=admin_flag)

        shipping_address = request.form.get('shipping_address', '').strip()
        try:
            shipping_cost = _signed_float(request.form.get('shipping_cost', '0'), '客户费用/折扣')
            shipping_note = _managed_field_value('shipping_note', request.form.get('shipping_note', ''))
            shipping_note_en = _managed_field_english(
                'shipping_note', request.form.get('shipping_note', '')
            )
            _require_customer_adjustment_type(shipping_cost, shipping_note)
        except ValueError as exc:
            flash(str(exc), 'danger')
            return redirect(url_for('pi_create'))

        # Parse issue date
        try:
            issue_date = datetime.strptime(issue_date_str, '%Y-%m-%d').date() if issue_date_str else date.today()
        except ValueError:
            issue_date = date.today()

        # Load only the rows submitted by the browser.  The former full-table
        # product query became expensive once the catalogue grew into the
        # thousands, even though the picker itself is paginated.
        selected_items, total_amount = _submitted_pi_items(request.form)

        if not selected_items:
            flash('请至少选择一个产品。', 'danger')
            return render_template('create_pi.html', customers=customers,
                                   pi=None,
                                   today=issue_date.strftime('%Y-%m-%d'),
                                   selected_customer_id=customer_id,
                                   is_admin=admin_flag)

        # Create PI record
        pi_number = _generate_pi_number()
        if not is_admin() and not selected_account:
            flash('请选择已审核的收款账户。', 'danger')
            return redirect(url_for('pi_create'))

        # total_amount = product subtotal only (shipping stored separately)
        total_amount = round(total_amount, 2)

        pi = PI(
            pi_number=pi_number,
            customer_id=customer_id,
            issue_date=issue_date,
            payment_terms=payment_terms or '100% TT before shipment',
            price_terms=price_terms,
            delivery_time=delivery_time,
            salesperson=salesperson,
            currency=currency,
            exchange_rate=business_exchange_rate,
            company=company,
            total_amount=total_amount,
            shipping_cost=shipping_cost,
            shipping_note=shipping_note,
            shipping_note_en=shipping_note_en,
            shipping_address=shipping_address,
            notes=notes,
        )
        _apply_bank_snapshot(pi, selected_account, bank_info)
        db.session.add(pi)
        db.session.flush()  # Get pi.id

        # Create PI items
        for item in selected_items:
            pi_item = PIItem(
                pi_id=pi.id,
                product_id=item['product'].id,
                quantity=item['quantity'],
                unit_price=item['unit_price'],
                amount=item['amount'],
            )
            db.session.add(pi_item)

        db.session.flush()

        # Generate the saved PDF and Excel with the same default template and
        # rendering path used by the export workbench.
        try:
            pdf_filename, excel_filename = _generate_default_pi_documents(pi)
            pi.pdf_path = pdf_filename
            pi.excel_path = excel_filename
        except Exception as e:
            db.session.rollback()
            flash(f'生成 PDF 失败：{str(e)}', 'danger')
            return render_template('create_pi.html', customers=customers,
                                   pi=None,
                                   today=issue_date.strftime('%Y-%m-%d'),
                                   selected_customer_id=customer_id,
                                   is_admin=admin_flag)

        _audit('create', 'pi', pi.id, f'新增 PI：{pi.pi_number}',
               after=_snapshot(pi, ['pi_number', 'customer_id', 'issue_date', 'salesperson', 'currency', 'exchange_rate', 'company', 'total_amount', 'shipping_cost', 'shipping_note', 'shipping_note_en', 'payment_terms', 'price_terms', 'delivery_time', 'bank_info', *BANK_SNAPSHOT_FIELDS, 'notes', 'version']))
        db.session.commit()
        flash(f'PI {pi_number} 已创建并生成 PDF。', 'success')
        return redirect(url_for('pi_detail', id=pi.id))

    # GET request
    selected_customer_id = request.args.get('customer_id', type=int)
    preselected_salesperson = ''
    if selected_customer_id:
        cust = Customer.query.get(selected_customer_id)
        if cust:
            require_customer_access(cust)
            preselected_salesperson = cust.salesperson
    return render_template('create_pi.html', customers=customers,
                           pi=None,
                           today=date.today().strftime('%Y-%m-%d'),
                           selected_customer_id=selected_customer_id,
                           preselected_salesperson=preselected_salesperson,
                           is_admin=is_admin())


@app.route('/pi/list')
@login_required
def pi_list():
    salesperson_filter = request.args.get('salesperson', '').strip()
    date_from = request.args.get('date_from', '').strip()
    date_to = request.args.get('date_to', '').strip()
    payment_status = request.args.get('payment_status', '').strip()
    order_status = request.args.get('order_status', '').strip()
    customs_status = request.args.get('customs_status', '').strip()
    payment_labels = {
        'unpaid': '未回款',
        'partial': '部分回款',
        'paid': '已付清',
    }
    order_labels = {
        'pending': '待采购',
        'partial': '部分采购',
        'purchased': '采购完成',
        'shipped': '发货完成',
    }
    customs_labels = {
        'unregistered': '未登记',
        'required': '需要报关',
        'not_required': '无需报关',
    }
    if payment_status not in payment_labels:
        payment_status = ''
    if order_status not in order_labels:
        order_status = ''
    if customs_status not in customs_labels:
        customs_status = ''

    query = filter_by_user(
        PI.query.options(
            joinedload(PI.customer),
            selectinload(PI.expenses),
            selectinload(PI.packing_list),
            selectinload(PI.items),
            selectinload(PI.procurements),
        ),
        PI,
        'salesperson',
    )

    if salesperson_filter:
        query = query.filter(PI.salesperson == salesperson_filter)
    if date_from:
        try:
            d_from = datetime.strptime(date_from, '%Y-%m-%d').date()
            query = query.filter(PI.issue_date >= d_from)
        except ValueError:
            pass
    if date_to:
        try:
            d_to = datetime.strptime(date_to, '%Y-%m-%d').date()
            query = query.filter(PI.issue_date <= d_to)
        except ValueError:
            pass

    if payment_status == 'paid':
        query = query.filter(PI.paid.is_(True))
    elif payment_status == 'partial':
        query = query.filter(
            PI.paid.is_not(True),
            func.coalesce(PI.received_amount, 0) > 0,
        )
    elif payment_status == 'unpaid':
        query = query.filter(
            PI.paid.is_not(True),
            func.coalesce(PI.received_amount, 0) <= 0,
        )

    if customs_status == 'required':
        query = query.filter(PI.customs_required.is_(True))
    elif customs_status == 'not_required':
        query = query.filter(PI.customs_required.is_(False))
    elif customs_status == 'unregistered':
        query = query.filter(PI.customs_required.is_(None))

    pis = query.order_by(PI.created_at.desc()).all()
    if order_status:
        expected_order_status = order_labels[order_status]
        pis = [
            pi for pi in pis
            if pi.effective_procurement_status == expected_order_status
        ]
    payment_account_ids = {}
    for pi in pis:
        matching_account = _matching_account_for_pi(pi)
        payment_account_ids[pi.id] = matching_account.id if matching_account else None

    # Total for this filtered set
    filtered_totals = {
        'USD': round(sum(pi.grand_total for pi in pis if pi.currency != 'RMB'), 2),
        'RMB': round(sum(pi.grand_total for pi in pis if pi.currency == 'RMB'), 2),
    }

    resp = make_response(render_template('pi_list.html', pis=pis,
                           salesperson_filter=salesperson_filter,
                           date_from=date_from, date_to=date_to,
                           payment_status=payment_status,
                           order_status=order_status,
                           customs_status=customs_status,
                           payment_status_label=payment_labels.get(payment_status, ''),
                           order_status_label=order_labels.get(order_status, ''),
                           customs_status_label=customs_labels.get(customs_status, ''),
                           filtered_totals=filtered_totals,
                           payment_account_ids=payment_account_ids,
                           payment_token=uuid.uuid4().hex))
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'
    return resp


def _packing_pi_query():
    """Load all PI data needed by the packing-list editor and exports."""
    return PI.query.options(
        joinedload(PI.customer),
        selectinload(PI.items).joinedload(PIItem.product),
        selectinload(PI.packing_list)
        .selectinload(PackingList.boxes)
        .selectinload(PackingBox.items),
    ).filter(PI.deleted_at.is_(None))


def _packing_company(pi):
    if (pi.company or '').lower() == 'qisuo':
        return (
            'Changzhou Qisuo welding and cutting Equipment Co., LTD',
            'No. 158, Jingchuang Road, Yaoguan Town, Changzhou District, '
            'Jiangsu Province',
        )
    return COMPANY_CONFIG['name'], COMPANY_CONFIG.get('address', '')


def _packing_list_payload(pi, packing_list=None, prefill=False):
    pi_items = []
    for item in pi.items:
        product = item.product
        pi_items.append({
            'id': item.id,
            'name': product.name if product else '',
            'product_code': product.product_code if product else '',
            'specification': product.specification if product else '',
            'image': product.image if product else '',
            'quantity': int(item.quantity or 0),
        })

    boxes = []
    if packing_list:
        for box in packing_list.boxes:
            boxes.append({
                'box_no': box.box_no,
                'net_weight': box.net_weight or 0,
                'gross_weight': box.gross_weight or 0,
                'length_cm': box.length_cm or 0,
                'width_cm': box.width_cm or 0,
                'height_cm': box.height_cm or 0,
                'volume_cbm': box.volume_cbm or 0,
                'shipping_mark': box.shipping_mark or '',
                'note': box.note or '',
                'items': [{
                    'pi_item_id': packed_item.pi_item_id,
                    'quantity': int(packed_item.quantity or 0),
                    'note': packed_item.note or '',
                } for packed_item in box.items],
            })
    elif prefill and pi_items:
        boxes.append({
            'box_no': '1',
            'net_weight': 0,
            'gross_weight': 0,
            'length_cm': 0,
            'width_cm': 0,
            'height_cm': 0,
            'volume_cbm': 0,
            'shipping_mark': '',
            'note': '',
            'items': [],
        })

    return {
        'pi_id': pi.id,
        'pi_number': pi.pi_number,
        'customer': pi.customer.name if pi.customer else '',
        'salesperson': pi.salesperson or '',
        'status': packing_list.status if packing_list else 'unsaved',
        'packing_date': (
            packing_list.packing_date.isoformat()
            if packing_list and packing_list.packing_date else date.today().isoformat()
        ),
        'version': packing_list.version if packing_list else 0,
        'saved': packing_list is not None,
        'pi_items': pi_items,
        'boxes': boxes,
    }


def _packing_text(value, label, limit):
    text_value = str(value or '').strip()
    if len(text_value) > limit:
        raise ValueError(f'{label}不能超过 {limit} 个字符。')
    if re.search(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', text_value):
        raise ValueError(f'{label}包含无效字符。')
    return text_value


def _packing_number(value, label):
    try:
        number = float(value or 0)
    except (TypeError, ValueError) as exc:
        raise ValueError(f'{label}必须是数字。') from exc
    if not math.isfinite(number) or number < 0 or number > 1000000000:
        raise ValueError(f'{label}必须是有效的非负数字。')
    return round(number, 6)


def _packing_quantity(value):
    if isinstance(value, bool) or not re.fullmatch(r'[1-9]\d*', str(value or '')):
        raise ValueError('装箱数量必须是正整数。')
    quantity = int(value)
    if quantity > 1000000:
        raise ValueError('单行装箱数量过大。')
    return quantity


def _validate_packing_boxes(pi, raw_boxes, completing=False):
    if not isinstance(raw_boxes, list) or not raw_boxes:
        raise ValueError('请至少保留一个箱子。')
    if len(raw_boxes) > 200:
        raise ValueError('一份装箱单最多包含 200 个箱子。')

    pi_items = {item.id: item for item in pi.items}
    required = {item.id: int(item.quantity or 0) for item in pi.items}
    packed = {item_id: 0 for item_id in required}
    seen_box_numbers = set()
    result = []
    row_count = 0

    for box_index, raw_box in enumerate(raw_boxes):
        if not isinstance(raw_box, dict):
            raise ValueError('箱子数据格式不正确。')
        box_no = _packing_text(raw_box.get('box_no'), '箱号', 50)
        if not box_no:
            raise ValueError('箱号不能为空。')
        box_key = box_no.casefold()
        if box_key in seen_box_numbers:
            raise ValueError(f'箱号“{box_no}”重复。')
        seen_box_numbers.add(box_key)

        net_weight = _packing_number(raw_box.get('net_weight'), '净重')
        gross_weight = _packing_number(raw_box.get('gross_weight'), '毛重')
        if gross_weight and net_weight and gross_weight < net_weight:
            raise ValueError(f'箱号“{box_no}”的毛重不能小于净重。')
        length_cm = _packing_number(raw_box.get('length_cm'), '长度')
        width_cm = _packing_number(raw_box.get('width_cm'), '宽度')
        height_cm = _packing_number(raw_box.get('height_cm'), '高度')
        raw_items = raw_box.get('items')
        if not isinstance(raw_items, list):
            raise ValueError(f'箱号“{box_no}”的产品数据格式不正确。')
        if completing and not raw_items:
            raise ValueError(f'箱号“{box_no}”至少需要一个产品。')

        box_seen_items = set()
        items = []
        for item_index, raw_item in enumerate(raw_items):
            row_count += 1
            if row_count > 2000:
                raise ValueError('一份装箱单最多包含 2000 行产品。')
            try:
                pi_item_id = int(raw_item.get('pi_item_id'))
            except (AttributeError, TypeError, ValueError) as exc:
                raise ValueError('装箱产品信息无效。') from exc
            if pi_item_id not in pi_items:
                raise ValueError('装箱产品不属于当前 PI。')
            if pi_item_id in box_seen_items:
                raise ValueError(f'箱号“{box_no}”中同一产品不能重复。')
            box_seen_items.add(pi_item_id)
            quantity = _packing_quantity(raw_item.get('quantity'))
            packed[pi_item_id] += quantity
            if packed[pi_item_id] > required[pi_item_id]:
                product = pi_items[pi_item_id].product
                name = product.name if product else f'产品 #{pi_item_id}'
                raise ValueError(f'“{name}”的累计装箱数量超过 PI 数量。')
            product = pi_items[pi_item_id].product
            items.append({
                'pi_item': pi_items[pi_item_id],
                'quantity': quantity,
                'note': _packing_text(raw_item.get('note'), '产品备注', 500),
                'sort_order': item_index,
                'product_name': product.name if product else '',
                'product_code': product.product_code if product else '',
                'specification': product.specification if product else '',
            })

        result.append({
            'box_no': box_no,
            'net_weight': net_weight,
            'gross_weight': gross_weight,
            'length_cm': length_cm,
            'width_cm': width_cm,
            'height_cm': height_cm,
            'volume_cbm': round(length_cm * width_cm * height_cm / 1000000, 6),
            'shipping_mark': _packing_text(raw_box.get('shipping_mark'), '唛头', 300),
            'note': _packing_text(raw_box.get('note'), '箱备注', 500),
            'sort_order': box_index,
            'items': items,
        })

    if completing:
        missing = []
        for item_id, quantity in required.items():
            if packed[item_id] != quantity:
                product = pi_items[item_id].product
                name = product.name if product else f'产品 #{item_id}'
                missing.append(f'{name}（已装 {packed[item_id]} / 应装 {quantity}）')
        if missing:
            raise ValueError('完成前请核对全部 PI 数量：' + '；'.join(missing[:5]))
    return result


@app.route('/packing-lists')
@login_required
def packing_list_index():
    salesperson_filter, date_from, date_to, preset = _report_filter_values()
    status_filter = request.args.get('status', '').strip()
    if status_filter not in ('', 'unsaved', 'draft', 'completed'):
        status_filter = ''
    query = filter_by_user(
        PI.query.options(
            joinedload(PI.customer),
            selectinload(PI.items),
            selectinload(PI.packing_list)
            .selectinload(PackingList.boxes)
            .selectinload(PackingBox.items),
        ),
        PI,
        'salesperson',
    )
    query = _apply_report_filters(query, salesperson_filter, date_from, date_to)
    # A first payment opens packing work. Keep an already-created historical
    # packing list visible so it can still be reviewed/exported after reversal.
    query = query.outerjoin(PackingList).filter(
        (func.coalesce(PI.received_amount, 0) > 0) | (PackingList.id.isnot(None))
    )
    if status_filter == 'unsaved':
        query = query.filter(PackingList.id.is_(None))
    elif status_filter in ('draft', 'completed'):
        query = query.filter(PackingList.status == status_filter)
    pis = query.order_by(PI.issue_date.desc(), PI.id.desc()).all()
    salespeople = []
    if is_admin():
        salespeople = [row[0] for row in db.session.query(PI.salesperson).filter(
            PI.deleted_at.is_(None), PI.salesperson.isnot(None), PI.salesperson != ''
        ).distinct().order_by(PI.salesperson).all()]
    return render_template(
        'packing_list_index.html', pis=pis, salespeople=salespeople,
        salesperson_filter=salesperson_filter, date_from=date_from,
        date_to=date_to, preset=preset, status_filter=status_filter,
    )


@app.route('/packing-list/<int:pi_id>')
@login_required
def packing_list_detail(pi_id):
    pi = _packing_pi_query().filter(PI.id == pi_id).first_or_404()
    require_pi_access(pi)
    packing_list = pi.packing_list
    has_payment = (pi.received_amount or 0) > 0
    if packing_list is None and not has_payment:
        flash('PI 尚未回款，不能创建装箱单。', 'warning')
        return redirect(url_for('packing_list_index'))
    data = _packing_list_payload(
        pi, packing_list,
        prefill=is_admin() and has_payment and packing_list is None,
    )
    edit_mode = bool(
        is_admin() and has_payment and (
            packing_list is None
            or not packing_list.is_completed
            or request.args.get('edit') == '1'
        )
    )
    return render_template(
        'packing_list_edit.html', pi=pi, packing_list=packing_list,
        packing_data=data, can_edit=edit_mode,
    )


@app.route('/api/packing-list/<int:pi_id>', methods=['POST'])
@admin_required
def packing_list_save(pi_id):
    pi = _packing_pi_query().filter(PI.id == pi_id).first_or_404()
    if (pi.received_amount or 0) <= 0:
        return jsonify({
            'success': False,
            'error': 'PI 尚未回款，不能创建或修改装箱单。',
        }), 409
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({'success': False, 'error': '提交数据格式不正确。'}), 400
    action = str(payload.get('action') or 'draft').strip()
    if action not in ('draft', 'complete'):
        return jsonify({'success': False, 'error': '装箱单操作无效。'}), 400
    try:
        submitted_version = int(payload.get('version') or 0)
    except (TypeError, ValueError):
        return jsonify({'success': False, 'error': '页面版本无效，请刷新后重试。'}), 400
    packing_list = pi.packing_list
    current_version = packing_list.version if packing_list else 0
    if submitted_version != current_version:
        return jsonify({
            'success': False,
            'error': '装箱单已被其他管理员更新，请刷新页面后再修改。',
        }), 409
    try:
        packing_date_value = str(payload.get('packing_date') or '').strip()
        packing_date = (
            datetime.strptime(packing_date_value, '%Y-%m-%d').date()
            if packing_date_value else date.today()
        )
        boxes = _validate_packing_boxes(
            pi, payload.get('boxes'), completing=action == 'complete'
        )
    except ValueError as exc:
        return jsonify({'success': False, 'error': str(exc)}), 400

    user = get_current_user()
    before = _packing_list_payload(pi, packing_list) if packing_list else {}
    try:
        if packing_list is None:
            packing_list = PackingList(
                pi=pi, created_by=user.username, updated_by=user.username,
                status='draft', packing_date=packing_date,
            )
            db.session.add(packing_list)
            db.session.flush()
        else:
            packing_list.boxes.clear()
            db.session.flush()
        packing_list.status = 'completed' if action == 'complete' else 'draft'
        packing_list.packing_date = packing_date
        packing_list.updated_by = user.username
        packing_list.updated_at = datetime.utcnow()

        for box_data in boxes:
            box = PackingBox(
                box_no=box_data['box_no'], net_weight=box_data['net_weight'],
                gross_weight=box_data['gross_weight'], length_cm=box_data['length_cm'],
                width_cm=box_data['width_cm'], height_cm=box_data['height_cm'],
                volume_cbm=box_data['volume_cbm'], shipping_mark=box_data['shipping_mark'],
                note=box_data['note'], sort_order=box_data['sort_order'],
            )
            packing_list.boxes.append(box)
            for item_data in box_data['items']:
                box.items.append(PackingItem(
                    pi_item=item_data['pi_item'], quantity=item_data['quantity'],
                    product_name=item_data['product_name'],
                    product_code=item_data['product_code'],
                    specification=item_data['specification'],
                    note=item_data['note'], sort_order=item_data['sort_order'],
                ))
        db.session.flush()
        after = _packing_list_payload(pi, packing_list)
        _audit(
            'complete' if action == 'complete' else 'save', 'packing_list',
            packing_list.id,
            f'{"完成" if action == "complete" else "保存"}装箱单：{pi.pi_number}',
            before=before, after=after,
        )
        db.session.commit()
    except StaleDataError:
        db.session.rollback()
        return jsonify({'success': False, 'error': '装箱单已被其他管理员更新，请刷新后重试。'}), 409
    except IntegrityError:
        db.session.rollback()
        return jsonify({'success': False, 'error': '箱号重复或装箱数据冲突，请检查后重试。'}), 409
    except Exception:
        db.session.rollback()
        current_app.logger.exception('Saving packing list failed')
        return jsonify({'success': False, 'error': '保存装箱单失败，请稍后重试。'}), 500
    return jsonify({
        'success': True,
        'message': '装箱单已完成。' if action == 'complete' else '装箱单草稿已保存。',
        'data': _packing_list_payload(pi, packing_list),
    })


def _packing_export(pi_id, output_format):
    pi = _packing_pi_query().filter(PI.id == pi_id).first_or_404()
    require_pi_access(pi)
    packing_list = pi.packing_list
    if not packing_list:
        abort(404)
    company_name, company_address = _packing_company(pi)
    workbook_bytes = generate_packing_list_workbook(
        pi, packing_list, company_name, company_address
    )
    template = DocumentTemplate.query.filter_by(code='packing-a4', active=True).first()
    if template:
        workbook_bytes = apply_packing_template_style(
            workbook_bytes, _template_file_path(template), compact=False
        )
    suffix = '-DRAFT' if not packing_list.is_completed else ''
    base_name = secure_filename(f'Packing-List-{pi.pi_number}{suffix}') or 'packing-list'
    if output_format == 'xlsx':
        response = send_file(
            BytesIO(workbook_bytes),
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True, download_name=f'{base_name}.xlsx',
        )
    else:
        with tempfile.TemporaryDirectory(prefix='packing-list-') as work_dir:
            excel_path = os.path.join(work_dir, f'{base_name}.xlsx')
            pdf_path = os.path.join(work_dir, f'{base_name}.pdf')
            with open(excel_path, 'wb') as output_file:
                output_file.write(workbook_bytes)
            try:
                convert_excel_to_pdf(excel_path, pdf_path)
            except TemplateError as exc:
                flash(f'生成装箱单 PDF 失败：{exc}', 'danger')
                return redirect(url_for('packing_list_detail', pi_id=pi.id))
            with open(pdf_path, 'rb') as pdf_file:
                pdf_bytes = pdf_file.read()
        response = send_file(
            BytesIO(pdf_bytes), mimetype='application/pdf', as_attachment=True,
            download_name=f'{base_name}.pdf',
        )
    response.headers['Cache-Control'] = 'no-store'
    return response


@app.route('/packing-list/<int:pi_id>/export.xlsx')
@login_required
def packing_list_export_excel(pi_id):
    return _packing_export(pi_id, 'xlsx')


@app.route('/packing-list/<int:pi_id>/export.pdf')
@login_required
def packing_list_export_pdf(pi_id):
    return _packing_export(pi_id, 'pdf')


def _packing_compact_export(pi_id, output_format):
    pi = _packing_pi_query().filter(PI.id == pi_id).first_or_404()
    require_pi_access(pi)
    packing_list = pi.packing_list
    if not packing_list:
        abort(404)
    suffix = '-DRAFT' if not packing_list.is_completed else ''
    base_name = secure_filename(
        f'Packing-List-{pi.pi_number}-Compact-100x150{suffix}'
    ) or 'packing-list-compact-100x150'
    content = generate_compact_packing_list_workbook(pi, packing_list)
    template = DocumentTemplate.query.filter_by(
        code='packing-compact-100x150', active=True
    ).first()
    if template:
        content = apply_packing_template_style(
            content, _template_file_path(template), compact=True
        )
    mimetype = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    if output_format == 'pdf':
        with tempfile.TemporaryDirectory(prefix='packing-compact-') as work_dir:
            excel_path = os.path.join(work_dir, f'{base_name}.xlsx')
            pdf_path = os.path.join(work_dir, f'{base_name}.pdf')
            with open(excel_path, 'wb') as output_file:
                output_file.write(content)
            try:
                convert_excel_to_pdf(excel_path, pdf_path)
            except TemplateError as exc:
                flash(f'生成装箱单 PDF 失败：{exc}', 'danger')
                return redirect(url_for('packing_list_detail', pi_id=pi.id))
            with open(pdf_path, 'rb') as pdf_file:
                content = pdf_file.read()
        mimetype = 'application/pdf'
    response = send_file(
        BytesIO(content), mimetype=mimetype, as_attachment=True,
        download_name=f'{base_name}.{output_format}',
    )
    response.headers['Cache-Control'] = 'no-store'
    return response


@app.route('/packing-list/<int:pi_id>/compact-100x150.xlsx')
@login_required
def packing_list_compact_export_excel(pi_id):
    return _packing_compact_export(pi_id, 'xlsx')


@app.route('/packing-list/<int:pi_id>/compact-100x150.pdf')
@login_required
def packing_list_compact_export_pdf(pi_id):
    return _packing_compact_export(pi_id, 'pdf')


@app.route('/pi/<int:id>')
@login_required
def pi_detail(id):
    pi = PI.query.options(
        joinedload(PI.customer),
        joinedload(PI.items).joinedload(PIItem.product),
    ).get_or_404(id)
    require_pi_access(pi)
    resp = make_response(render_template('pi_detail.html', pi=pi))
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'
    return resp


@app.route('/pi/<int:id>/preview')
@login_required
def pi_preview(id):
    pi = PI.query.options(
        joinedload(PI.customer),
        joinedload(PI.items).joinedload(PIItem.product),
    ).get_or_404(id)
    require_pi_access(pi)
    return render_template('pi_preview.html', pi=pi)


@app.route('/pi/<int:id>/download')
@login_required
def pi_download(id):
    pi = PI.query.options(
        joinedload(PI.customer),
        joinedload(PI.items).joinedload(PIItem.product),
    ).get_or_404(id)
    require_pi_access(pi)
    work_dir = tempfile.mkdtemp(prefix='pi-direct-download-')
    try:
        template = _export_template()
        export_pi = _pi_export_copy(pi)
        output_path, mimetype = _render_pi_export(
            export_pi, template, 'pdf', work_dir, preview=False
        )
    except (TemplateError, ValueError) as exc:
        shutil.rmtree(work_dir, ignore_errors=True)
        flash(f'生成 PDF 失败：{exc}', 'danger')
        return redirect(url_for('pi_detail', id=id))
    except Exception:
        shutil.rmtree(work_dir, ignore_errors=True)
        current_app.logger.exception('Direct PI PDF download failed')
        flash('生成 PDF 失败，请联系管理员查看日志。', 'danger')
        return redirect(url_for('pi_detail', id=id))

    download_name = (
        f'{secure_filename(pi.pi_number) or "PI"}_'
        f'{secure_filename(template.name) or "template"}.pdf'
    )
    response = send_file(
        output_path,
        mimetype=mimetype,
        as_attachment=True,
        download_name=download_name,
        conditional=False,
        max_age=0,
    )
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    response.call_on_close(lambda: shutil.rmtree(work_dir, ignore_errors=True))
    return response


@app.route('/pi/<int:id>/excel')
@login_required
def pi_excel_download(id):
    pi = PI.query.options(
        joinedload(PI.customer),
        joinedload(PI.items).joinedload(PIItem.product),
    ).get_or_404(id)
    require_pi_access(pi)
    # Auto-generate if missing
    if not pi.excel_path or not os.path.exists(os.path.join(app.config['PDF_DIR'], pi.excel_path)):
        try:
            fn = generate_pi_excel(pi, app.config['PDF_DIR'])
            pi.excel_path = fn
            db.session.commit()
        except Exception as e:
            flash(f'生成 Excel 失败：{e}', 'danger')
            return redirect(url_for('pi_detail', id=id))
    filepath = os.path.join(app.config['PDF_DIR'], pi.excel_path)
    return send_file(filepath, as_attachment=True, download_name=pi.excel_path)


@app.route('/pi/<int:id>/toggle-paid', methods=['POST'])
@login_required
def pi_toggle_paid(id):
    pi = PI.query.get_or_404(id)
    require_pi_access(pi)
    received_str = request.form.get('received_amount', '').strip()
    fee_str = request.form.get('fee', '0').strip()
    order_no = request.form.get('order_no', '').strip()
    order_no_normalized = _normalize_payment_reference(order_no)
    idempotency_key = request.form.get('idempotency_key', '').strip()
    receiving_account_id = request.form.get('receiving_account_id', type=int)
    receiving_account = db.session.get(Account, receiving_account_id) if receiving_account_id else None
    pi_currency = (pi.currency or 'USD').upper()
    try:
        amount = _nonnegative_float(received_str if received_str else pi.grand_total, '回款金额')
        fee = _nonnegative_float(fee_str if fee_str else 0, '手续费')
    except ValueError as exc:
        flash(str(exc), 'danger')
        return redirect(request.referrer or url_for('pi_list'))
    if amount <= 0:
        flash('回款金额必须大于 0。', 'danger')
        return redirect(request.referrer or url_for('pi_list'))
    if not order_no:
        flash('请填写回款流水号（阿里巴巴信保、支付宝或微信订单号）。', 'danger')
        return redirect(request.referrer or url_for('pi_list'))
    if not receiving_account:
        flash('请选择并确认实际到账账户。', 'danger')
        return redirect(request.referrer or url_for('pi_list'))
    if (receiving_account.currency or 'USD').upper() != pi_currency:
        flash(f'到账账户币种必须与 PI 币种 {pi_currency} 一致。', 'danger')
        return redirect(request.referrer or url_for('pi_list'))

    if not (16 <= len(idempotency_key) <= 64):
        flash('回款表单已过期，请刷新页面后重试。', 'danger')
        return redirect(request.referrer or url_for('pi_list'))

    # Database-level uniqueness below is the final guard; this early check
    # provides a friendlier message and applies across every PI.
    existing = Payment.query.filter(Payment.deleted_at.is_(None)).filter(
        db.or_(Payment.order_no_normalized == order_no_normalized,
               Payment.idempotency_key == idempotency_key)
    ).first()
    if existing:
        flash(f'该回款流水号已记录在 PI #{existing.pi_id}，系统未重复入账。', 'warning')
        return redirect(request.referrer or url_for('pi_list'))

    # Check total received won't exceed PI grand total (product + shipping)
    pi_grand_total = pi.grand_total
    current_received = sum(p.amount for p in _active_payments(pi.id))
    if current_received + amount > pi_grand_total:
        sym = '¥' if pi.currency == 'RMB' else '$'
        remaining = pi_grand_total - current_received
        flash(f'回款金额超过 PI 总额。剩余可收：{sym}{remaining:,.2f}（PI 总额：{sym}{pi_grand_total:,.2f}）', 'danger')
        return redirect(request.referrer or url_for('pi_list'))

    attachment_file = request.files.get('attachment')
    if not attachment_file or not attachment_file.filename:
        flash('请上传回款凭证图片。', 'danger')
        return redirect(request.referrer or url_for('pi_list'))
    try:
        attachment_file.stream.seek(0, os.SEEK_END)
        attachment_size = attachment_file.stream.tell()
        attachment_file.stream.seek(0)
    except (AttributeError, OSError):
        attachment_size = 0
    if attachment_size > 12 * 1024 * 1024:
        flash('回款凭证图片不能超过 12 MB。', 'danger')
        return redirect(request.referrer or url_for('pi_list'))
    attachment_name = _save_upload(attachment_file)
    if not attachment_name:
        flash('回款凭证必须是有效的 JPG、PNG、WebP 或 GIF 图片。', 'danger')
        return redirect(request.referrer or url_for('pi_list'))

    # Add payment record
    payment = Payment(
        pi_id=pi.id,
        amount=amount,
        fee=fee,
        order_no=order_no,
        order_no_normalized=order_no_normalized,
        idempotency_key=idempotency_key,
        receiving_account_id=receiving_account.id,
        receiving_account_name=receiving_account.name,
        receiving_account_currency=pi_currency,
        attachment=attachment_name,
    )
    db.session.add(payment)
    try:
        db.session.flush()
    except IntegrityError:
        db.session.rollback()
        _remove_upload(attachment_name)
        flash('该回款流水号或本次提交已处理，系统未重复入账。', 'warning')
        return redirect(request.referrer or url_for('pi_list'))

    try:
        # Amount + fee counts toward both paid status and the capped customer deal total.
        total_paid = _recalculate_pi_payments(pi)

        # Partial payments count immediately; RMB payments use the fixed
        # performance rate and each PI is capped at its invoiced total.
        customer = Customer.query.get(pi.customer_id)
        if customer:
            _recalculate_customer_deal(customer)

        _audit('create', 'payment', payment.id, f'在 {pi.pi_number} 登记回款：{order_no}',
               after=_snapshot(payment, ['pi_id', 'amount', 'fee', 'order_no', 'receiving_account_id',
                                         'receiving_account_name', 'receiving_account_currency',
                                         'attachment', 'created_at']))

        db.session.commit()
    except Exception:
        db.session.rollback()
        _remove_upload(attachment_name)
        raise

    # ── DingTalk 喜报 ──
    sym = '¥' if (pi.currency == 'RMB') else '$'
    cust_name = pi.customer.name if pi.customer else '未知客户'
    sp_name = pi.salesperson or '未分配'
    status = '🎉 全额付清' if pi.paid else ('📥 部分付款' if pi.received_amount > 0 else '📝 首笔付款')
    ding_title = f'💰 回款喜报 — {cust_name}'
    ding_text = (
        f'## 💰 回款喜报\n\n'
        f'**客户：** {cust_name}\n\n'
        f'**PI单号：** {pi.pi_number}\n\n'
        f'**业务员：** {sp_name}\n\n'
        f'**本次收款：** {sym}{amount:,.2f}\n\n'
        f'**手续费：** {sym}{fee:,.2f}\n\n'
        f'**到账账户：** {receiving_account.name}（{pi_currency}）\n\n'
        f'**订单编号：** {order_no}\n\n'
        f'**累计已收：** {sym}{pi.received_amount:,.2f} / {sym}{pi.grand_total:,.2f}\n\n'
        f'**状态：** {status}\n\n'
        f'> {COMPANY_CONFIG["name"]}  \n'
        f'> {datetime.now().strftime("%Y-%m-%d %H:%M")}'
    )
    ding_settings = _load_settings()
    report_webhook = _dingtalk_report_webhook(sp_name, ding_settings)
    if report_webhook:
        _send_dingtalk(ding_title, ding_text, webhook=report_webhook)

    # ── DingTalk 待办 ──
    sp = Salesperson.query.filter_by(name=sp_name).first()
    dt_user_id = sp.dingtalk_user_id if sp else ''
    if dt_user_id and _setting_enabled(ding_settings, 'dingtalk_task_enabled'):
        task_subject = f'{sp_name} - {cust_name} - {sym}{pi.received_amount:,.2f}/{sym}{pi.grand_total:,.2f} {status}'
        task_desc = (
            f'**客户：** {cust_name}\n'
            f'**PI单号：** {pi.pi_number}\n'
            f'**业务员：** {sp_name}\n'
            f'**本次收款：** {sym}{amount:,.2f}（手续费 {sym}{fee:,.2f}）\n'
            f'**到账账户：** {receiving_account.name}（{pi_currency}）\n'
            f'**订单编号：** {order_no}\n'
            f'**累计已收：** {sym}{pi.received_amount:,.2f} / {sym}{pi.grand_total:,.2f}\n'
            f'**状态：** {status}\n'
        )
        if pi.notes:
            task_desc += f'\n**备注：** {pi.notes}\n'

        # Build executor list: salesperson first, then default executors
        import json as _json
        default_execs = _json.loads(ding_settings.get('dingtalk_default_executors', '[]'))
        executor_ids = [dt_user_id]
        for eid in default_execs:
            if eid != dt_user_id:
                executor_ids.append(eid)

        pdf_path = os.path.join(app.config['PDF_DIR'], pi.pdf_path) if pi.pdf_path else ''
        task_id = _dingtalk_create_task(executor_ids, task_subject, task_desc)

    remaining = max(0, pi.grand_total - total_paid)
    flash(f'回款 {sym}{amount:,.2f}（手续费 {sym}{fee:,.2f}）已登记至“{receiving_account.name}”，剩余 {sym}{remaining:,.2f}。', 'success')
    return redirect(request.referrer or url_for('pi_list'))

@app.route('/pi/<int:id>/payment/<int:pid>/delete', methods=['POST'])
@login_required
def payment_delete(id, pid):
    payment = Payment.query.get_or_404(pid)
    pi = PI.query.get_or_404(id)
    require_pi_access(pi)
    if payment.pi_id != pi.id:
        abort(404)
    if payment.deleted_at is not None:
        abort(404)
    if request.form.get('confirm_value', '').strip() != payment.order_no:
        flash('输入内容与回款流水号不一致，未执行删除。', 'danger')
        return redirect(request.referrer or url_for('pi_list'))
    before = _snapshot(payment, ['pi_id', 'amount', 'fee', 'order_no', 'receiving_account_id',
                                 'receiving_account_name', 'receiving_account_currency', 'attachment',
                                 'deleted_at'])
    payment.deleted_at = datetime.utcnow()
    _recalculate_pi_payments(pi)
    # Update customer
    customer = Customer.query.get(pi.customer_id)
    if customer:
        _recalculate_customer_deal(customer)
    _audit('soft_delete', 'payment', payment.id, f'将回款 {payment.order_no} 移入回收站', before=before,
           after=_snapshot(payment, ['pi_id', 'amount', 'fee', 'order_no', 'receiving_account_id',
                                     'receiving_account_name', 'receiving_account_currency', 'attachment',
                                     'deleted_at']))
    db.session.commit()
    flash('回款已移入回收站；采购、装箱、报关和发货记录均未修改。', 'info')
    return redirect(request.referrer or url_for('pi_list'))


@app.route('/api/pi/<int:id>/payments')
@login_required
def api_pi_payments(id):
    pi = PI.query.get_or_404(id)
    require_pi_access(pi)
    grand_total = pi.grand_total
    payments = _active_payments(pi.id)
    default_account_id = None
    for payment in reversed(payments):
        if not payment.receiving_account_id:
            continue
        account = db.session.get(Account, payment.receiving_account_id)
        if account and (account.currency or 'USD').upper() == (pi.currency or 'USD').upper():
            default_account_id = account.id
            break
    if default_account_id is None:
        matching_account = _matching_account_for_pi(pi)
        default_account_id = matching_account.id if matching_account else None
    return jsonify({
        'currency': pi.currency or 'USD',
        'total_amount': pi.total_amount,
        'product_subtotal': pi.product_subtotal,
        'grand_total': grand_total,
        'received': pi.received_amount or 0,
        'paid': pi.paid,
        'default_account_id': default_account_id,
        'payments': [{
            'id': p.id,
            'amount': p.amount,
            'fee': p.fee or 0,
            'order_no': p.order_no or '',
            'receiving_account_id': p.receiving_account_id,
            'receiving_account_name': p.receiving_account_name or '',
            'receiving_account_currency': p.receiving_account_currency or '',
            'has_attachment': bool(p.attachment),
            'created_at': p.created_at.strftime('%Y-%m-%d %H:%M') if p.created_at else '',
        } for p in payments]
    })


@app.route('/payments/<int:id>/attachment')
@login_required
def payment_attachment(id):
    """Serve a payment receipt only to users who may access its PI."""
    payment = Payment.query.get_or_404(id)
    if payment.deleted_at is not None:
        abort(404)
    pi = PI.query.get_or_404(payment.pi_id)
    require_pi_access(pi)
    safe_name = secure_filename(payment.attachment or '')
    if not safe_name or safe_name != payment.attachment:
        abort(404)
    filepath = os.path.join(current_app.config['UPLOAD_DIR'], safe_name)
    if not os.path.isfile(filepath):
        abort(404)
    extension = os.path.splitext(safe_name)[1].lower()
    return send_file(
        filepath,
        conditional=True,
        download_name=f'{secure_filename(pi.pi_number) or "PI"}-回款凭证{extension}',
    )


@app.route('/api/pi/<int:id>/customs-declaration', methods=['GET', 'POST'])
@login_required
def api_pi_customs_declaration(id):
    """Read or update whether a PI requires a customs declaration."""
    pi = PI.query.get_or_404(id)
    require_pi_access(pi)

    if request.method == 'GET':
        return jsonify({
            'success': True,
            'pi_number': pi.pi_number,
            'customs_required': pi.customs_required,
            'note': pi.customs_note or '',
            'recorded_at': (
                pi.customs_recorded_at.strftime('%Y-%m-%d %H:%M')
                if pi.customs_recorded_at else ''
            ),
            'recorded_by': pi.customs_recorded_by or '',
        })

    payload = request.get_json(silent=True) or request.form
    raw_required = payload.get('customs_required')
    if raw_required is True or str(raw_required).strip().lower() in {'true', '1'}:
        customs_required = True
    elif raw_required is False or str(raw_required).strip().lower() in {'false', '0'}:
        customs_required = False
    else:
        return jsonify({'success': False, 'error': '请选择需要报关或无需报关。'}), 400

    note = str(payload.get('note') or '').strip()
    if len(note) > 500:
        return jsonify({'success': False, 'error': '备注不能超过 500 个字符。'}), 400

    fields = [
        'customs_required', 'customs_note',
        'customs_recorded_at', 'customs_recorded_by',
    ]
    before = _snapshot(pi, fields)
    pi.customs_required = customs_required
    pi.customs_note = note
    pi.customs_recorded_at = datetime.utcnow()
    pi.customs_recorded_by = get_current_user().username
    label = '需要报关' if customs_required else '无需报关'
    _audit(
        'update', 'pi', pi.id,
        f'更新 PI {pi.pi_number} 报关记录：{label}',
        before=before,
        after=_snapshot(pi, fields),
    )
    try:
        db.session.commit()
    except StaleDataError:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': '这份 PI 刚被其他人更新，请刷新页面后重试。',
        }), 409

    return jsonify({
        'success': True,
        'pi_number': pi.pi_number,
        'customs_required': pi.customs_required,
        'note': pi.customs_note or '',
        'recorded_at': pi.customs_recorded_at.strftime('%Y-%m-%d %H:%M'),
        'recorded_by': pi.customs_recorded_by,
        'label': label,
    })


@app.route('/pi/<int:id>/delete', methods=['POST'])
@login_required
def pi_delete(id):
    pi = PI.query.get_or_404(id)
    require_pi_access(pi)
    if request.form.get('confirm_value', '').strip() != pi.pi_number:
        flash('输入内容与 PI 编号不一致，未执行删除。', 'danger')
        return redirect(request.referrer or url_for('pi_list'))
    before = _snapshot(pi, ['pi_number', 'customer_id', 'salesperson', 'total_amount', 'received_amount', 'deleted_at'])
    pi.deleted_at = datetime.utcnow()
    pi.version = (pi.version or 1) + 1
    _audit('soft_delete', 'pi', pi.id, f'将 PI {pi.pi_number} 移入回收站', before=before,
           after=_snapshot(pi, ['pi_number', 'customer_id', 'salesperson', 'total_amount', 'received_amount', 'deleted_at']))
    db.session.commit()
    flash('PI 已移入回收站。', 'success')
    return redirect(url_for('pi_list'))


@app.route('/pi/<int:id>/copy', methods=['POST'])
@login_required
def pi_copy(id):
    """Copy a PI: same info, new date and PI number."""
    original = PI.query.options(
        joinedload(PI.items).joinedload(PIItem.product)
    ).get_or_404(id)
    require_pi_access(original)

    # Generate new PI number with today's date
    pi_number = _generate_pi_number()

    # Create new PI with same data
    new_pi = PI(
        pi_number=pi_number,
        customer_id=original.customer_id,
        issue_date=date.today(),
        payment_terms=original.payment_terms,
        price_terms=original.price_terms,
        delivery_time=original.delivery_time,
        bank_info=original.bank_info,
        salesperson=original.salesperson,
        currency=original.currency or 'USD',
        exchange_rate=_pi_exchange_rate(original),
        company=original.company or 'klista',
        total_amount=original.total_amount,
        shipping_cost=original.shipping_cost or 0.0,
        shipping_note=original.shipping_note or '',
        shipping_note_en=original.shipping_note_en or '',
        shipping_address=original.shipping_address or '',
        notes=original.notes,
    )
    for field in BANK_SNAPSHOT_FIELDS:
        setattr(new_pi, field, getattr(original, field, '') or '')
    db.session.add(new_pi)
    db.session.flush()  # Get new_pi.id

    # Copy all PI items
    for item in original.items:
        new_item = PIItem(
            pi_id=new_pi.id,
            product_id=item.product_id,
            quantity=item.quantity,
            unit_price=item.unit_price,
            amount=item.amount,
        )
        db.session.add(new_item)

    db.session.flush()

    # Generate the saved files through the export workbench renderer.
    try:
        pdf_filename, excel_filename = _generate_default_pi_documents(new_pi)
        new_pi.pdf_path = pdf_filename
        new_pi.excel_path = excel_filename
    except Exception as e:
        db.session.rollback()
        flash(f'生成 PDF 失败：{str(e)}', 'danger')
        return redirect(url_for('pi_list'))

    _audit('create', 'pi', new_pi.id, f'复制 PI：{original.pi_number} → {new_pi.pi_number}',
           after=_snapshot(new_pi, ['pi_number', 'customer_id', 'salesperson', 'currency', 'total_amount', 'shipping_cost']))
    db.session.commit()
    flash(f'已从 {original.pi_number} 复制生成 {pi_number}，现在可以编辑。', 'success')
    return redirect(url_for('pi_edit', id=new_pi.id))


def _preload_products(pi):
    preload = []
    pi_rate = _pi_exchange_rate(pi)
    for item in pi.items:
        prod = item.product
        if prod:
            price_usd = item.unit_price if pi.currency != 'RMB' else item.unit_price / pi_rate
            preload.append({'id': prod.id, 'name': prod.name, 'code': prod.product_code,
                            'spec': prod.specification or '', 'price': item.unit_price,
                            'price_usd': price_usd,
                            'img': prod.image or '', 'qty': item.quantity})
    return preload


def _pi_downstream_impact(pi):
    """Summarize records that make structural PI edits business-sensitive."""
    payment_count = Payment.query.filter_by(pi_id=pi.id).filter(
        Payment.deleted_at.is_(None)
    ).count()
    procurements = Procurement.query.filter_by(pi_id=pi.id).all()
    supplier_count = len({row.supplier_id for row in procurements if row.supplier_id})
    packing_list = PackingList.query.filter_by(pi_id=pi.id).first()
    box_count = 0
    packing_item_count = 0
    if packing_list:
        box_count = PackingBox.query.filter_by(packing_list_id=packing_list.id).count()
        packing_item_count = PackingItem.query.join(PackingBox).filter(
            PackingBox.packing_list_id == packing_list.id
        ).count()
    customs_recorded = pi.customs_required is not None
    has_downstream = bool(
        payment_count or procurements or packing_list
        or customs_recorded or pi.shipping_completed
    )
    return {
        'has_downstream': has_downstream,
        'payment_count': payment_count,
        'procurement_count': len(procurements),
        'supplier_count': supplier_count,
        'packing_exists': bool(packing_list),
        'packing_status': packing_list.status if packing_list else '',
        'box_count': box_count,
        'packing_item_count': packing_item_count,
        'customs_recorded': customs_recorded,
        'customs_label': (
            '需要报关' if pi.customs_required is True
            else ('无需报关' if pi.customs_required is False else '')
        ),
        'shipping_completed': bool(pi.shipping_completed),
    }


def _pi_item_usage(pi):
    """Return purchased and packed quantities keyed by the stable PI item id."""
    usage = {
        item.id: {'procured': 0, 'packed': 0}
        for item in pi.items
    }
    procurement_rows = db.session.query(
        Procurement.pi_item_id, func.sum(Procurement.quantity)
    ).filter(Procurement.pi_id == pi.id).group_by(Procurement.pi_item_id).all()
    for item_id, quantity in procurement_rows:
        usage.setdefault(item_id, {'procured': 0, 'packed': 0})['procured'] = int(quantity or 0)

    packing_rows = db.session.query(
        PackingItem.pi_item_id, func.sum(PackingItem.quantity)
    ).join(PackingBox, PackingItem.packing_box_id == PackingBox.id).join(
        PackingList, PackingBox.packing_list_id == PackingList.id
    ).filter(PackingList.pi_id == pi.id).group_by(PackingItem.pi_item_id).all()
    for item_id, quantity in packing_rows:
        usage.setdefault(item_id, {'procured': 0, 'packed': 0})['packed'] = int(quantity or 0)
    return usage


def _pi_structural_changes(pi, *, customer_id, salesperson, currency,
                           exchange_rate, company, issue_date, shipping_cost,
                           selected_items):
    """Describe submitted changes that can affect downstream business records."""
    changes = []
    scalar_values = (
        ('客户', pi.customer_id, customer_id),
        ('业务员', pi.salesperson or '', salesperson or ''),
        ('币种', (pi.currency or 'USD').upper(), currency.upper()),
        ('本单业务汇率', float(pi.exchange_rate or 0), float(exchange_rate)),
        ('公司模板', pi.company or 'klista', company or 'klista'),
        ('开单日期', pi.issue_date, issue_date),
        ('客户费用/折扣', float(pi.shipping_cost or 0), float(shipping_cost)),
    )
    for label, old_value, new_value in scalar_values:
        if isinstance(old_value, float) or isinstance(new_value, float):
            different = abs(float(old_value) - float(new_value)) > 0.00005
        else:
            different = old_value != new_value
        if different:
            changes.append(label)

    existing_by_product = {item.product_id: item for item in pi.items}
    submitted_by_product = {row['product'].id: row for row in selected_items}
    added = [row['product'].name for product_id, row in submitted_by_product.items()
             if product_id not in existing_by_product]
    removed = [item.product.name if item.product else str(item.product_id)
               for product_id, item in existing_by_product.items()
               if product_id not in submitted_by_product]
    modified = []
    for product_id, item in existing_by_product.items():
        submitted = submitted_by_product.get(product_id)
        if not submitted:
            continue
        details = []
        if int(item.quantity or 0) != int(submitted['quantity']):
            details.append('数量')
        if abs(float(item.unit_price or 0) - float(submitted['unit_price'])) > 0.005:
            details.append('单价')
        if details:
            modified.append(
                f"{item.product.name if item.product else product_id}（{'、'.join(details)}）"
            )
    if added:
        changes.append(f"新增产品：{'、'.join(added[:5])}")
    if removed:
        changes.append(f"移除产品：{'、'.join(removed[:5])}")
    if modified:
        changes.append(f"修改产品：{'、'.join(modified[:5])}")

    submitted_total = round(sum(row['amount'] for row in selected_items), 2)
    if abs(float(pi.total_amount or 0) - submitted_total) > 0.005 and not any(
        label.startswith(('新增产品：', '移除产品：', '修改产品：')) for label in changes
    ):
        changes.append('产品小计')
    return changes


def _validate_pi_item_reconciliation(pi, selected_items):
    """Block item changes that would invalidate existing purchase/packing rows."""
    usage = _pi_item_usage(pi)
    submitted_by_product = {row['product'].id: row for row in selected_items}
    errors = []
    for item in pi.items:
        submitted = submitted_by_product.get(item.product_id)
        item_usage = usage.get(item.id, {'procured': 0, 'packed': 0})
        product_name = item.product.name if item.product else str(item.product_id)
        if not submitted:
            references = []
            if item_usage['procured']:
                references.append(f"已采购 {item_usage['procured']}")
            if item_usage['packed']:
                references.append(f"已装箱 {item_usage['packed']}")
            if references:
                errors.append(f"{product_name} 不能移除（{'，'.join(references)}）")
            continue
        submitted_quantity = int(submitted['quantity'])
        if item_usage['procured'] > submitted_quantity:
            errors.append(
                f"{product_name} 的 PI 数量不能低于已采购数量 {item_usage['procured']}"
            )
        if item_usage['packed'] > submitted_quantity:
            errors.append(
                f"{product_name} 的 PI 数量不能低于已装箱数量 {item_usage['packed']}"
            )
    return errors


def _reconcile_pi_items(pi, selected_items):
    """Update PI items in place so downstream foreign keys remain valid."""
    existing_by_product = {item.product_id: item for item in pi.items}
    submitted_product_ids = set()
    for submitted in selected_items:
        product_id = submitted['product'].id
        submitted_product_ids.add(product_id)
        item = existing_by_product.get(product_id)
        if item is None:
            item = PIItem(product_id=product_id)
            pi.items.append(item)
        item.quantity = submitted['quantity']
        item.unit_price = submitted['unit_price']
        item.amount = submitted['amount']
    for product_id, item in existing_by_product.items():
        if product_id not in submitted_product_ids:
            pi.items.remove(item)


@app.route('/pi/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def pi_edit(id):
    pi = PI.query.options(
        joinedload(PI.customer),
        joinedload(PI.items).joinedload(PIItem.product),
    ).get_or_404(id)
    require_pi_access(pi)
    customers = filter_by_user(Customer.query, Customer, 'salesperson').order_by(Customer.name).all()
    # Map existing items: product_id -> {quantity, selected}
    existing_items = {item.product_id: item.quantity for item in pi.items}
    preload = _preload_products(pi)
    downstream_impact = _pi_downstream_impact(pi)

    def render_edit_page():
        return render_template(
            'pi_edit.html', pi=pi, customers=customers,
            existing_items=existing_items, preload_products=preload,
            downstream_impact=downstream_impact,
        )

    if request.method == 'POST':
        if _submitted_version(pi) != (pi.version or 1):
            db.session.rollback()
            flash('该 PI 已被其他人修改，已重新加载最新版本，请核对后再次提交。', 'warning')
            return redirect(url_for('pi_edit', id=id))
        before = _snapshot(pi, ['pi_number', 'customer_id', 'issue_date', 'salesperson', 'currency', 'exchange_rate', 'company', 'total_amount', 'shipping_cost', 'shipping_note', 'shipping_note_en', 'payment_terms', 'price_terms', 'delivery_time', 'bank_info', *BANK_SNAPSHOT_FIELDS, 'notes', 'version'])
        before['items'] = [item.to_dict() for item in pi.items]
        old_customer_id = pi.customer_id
        customer_id = request.form.get('customer_id', type=int)
        salesperson = request.form.get('salesperson', '').strip()
        payment_terms = request.form.get('payment_terms', '').strip()
        try:
            price_terms = _selectable_or_manual_field(
                'price_terms', request.form.get('price_terms', '')
            )
            delivery_time = _selectable_or_manual_field(
                'delivery_time', request.form.get('delivery_time', '')
            )
        except ValueError as exc:
            flash(str(exc), 'danger')
            return redirect(url_for('pi_edit', id=id))
        bank_info = request.form.get('bank_info', '').strip()
        notes = request.form.get('notes', '').strip()
        issue_date_str = request.form.get('issue_date', '').strip()
        currency = request.form.get('currency', 'USD').strip()
        try:
            business_exchange_rate = _nonnegative_float(
                request.form.get('exchange_rate', str(_pi_exchange_rate(pi))),
                '本单业务汇率',
            )
        except ValueError as exc:
            flash(str(exc), 'danger')
            return redirect(url_for('pi_edit', id=id))
        if business_exchange_rate <= 0:
            flash('本单业务汇率必须大于 0。', 'danger')
            return redirect(url_for('pi_edit', id=id))
        company = request.form.get('company', 'klista').strip()
        account_id = request.form.get('account_id', type=int)
        selected_account = db.session.get(Account, account_id) if account_id else None
        if not is_admin():
            if selected_account:
                currency = selected_account.currency or pi.currency or 'USD'
                company = selected_account.brand or pi.company or 'klista'
            else:
                currency = pi.currency or 'USD'
                company = pi.company or 'klista'
        if currency not in {'USD', 'RMB'} or company not in {'klista', 'qisuo'}:
            abort(400)

        if not customer_id:
            flash('请选择客户。', 'danger')
            return render_edit_page()

        customer = Customer.query.get_or_404(customer_id)
        require_customer_access(customer)
        if not is_admin():
            salesperson = current_salesperson_name()

        if not salesperson:
            flash('请选择业务员。', 'danger')
            return render_edit_page()

        shipping_address = request.form.get('shipping_address', '').strip()
        try:
            shipping_cost = _signed_float(request.form.get('shipping_cost', '0'), '客户费用/折扣')
            shipping_note = _managed_field_value(
                'shipping_note', request.form.get('shipping_note', ''), pi.shipping_note
            )
            shipping_note_en = _managed_field_english(
                'shipping_note', request.form.get('shipping_note', ''),
                pi.shipping_note, pi.shipping_note_en,
            )
            _require_customer_adjustment_type(shipping_cost, shipping_note)
        except ValueError as exc:
            flash(str(exc), 'danger')
            return redirect(url_for('pi_edit', id=id))

        try:
            issue_date = datetime.strptime(issue_date_str, '%Y-%m-%d').date() if issue_date_str else pi.issue_date
        except ValueError:
            issue_date = pi.issue_date

        selected_items, total_amount = _submitted_pi_items(
            request.form,
            allow_inactive_ids=set(existing_items),
        )

        if not selected_items:
            flash('请至少选择一个产品。', 'danger')
            return render_edit_page()

        structural_changes = _pi_structural_changes(
            pi,
            customer_id=customer_id,
            salesperson=salesperson,
            currency=currency,
            exchange_rate=business_exchange_rate,
            company=company,
            issue_date=issue_date,
            shipping_cost=shipping_cost,
            selected_items=selected_items,
        )
        if downstream_impact['has_downstream'] and structural_changes:
            if not is_admin():
                flash(
                    '该 PI 已有下游业务记录，业务员只能修改备注、地址、条款等非结构信息。',
                    'danger',
                )
                return redirect(url_for('pi_edit', id=id))
            unlock_confirmed = request.form.get('downstream_unlock') == '1'
            change_reason = request.form.get('downstream_change_reason', '').strip()
            if not unlock_confirmed or len(change_reason) < 5:
                flash('请确认下游影响，并填写至少 5 个字符的修改原因。', 'danger')
                return redirect(url_for('pi_edit', id=id))
        else:
            change_reason = ''

        item_errors = _validate_pi_item_reconciliation(pi, selected_items)
        if item_errors:
            flash('；'.join(item_errors[:5]), 'danger')
            return redirect(url_for('pi_edit', id=id))
        if (
            downstream_impact['payment_count']
            and (pi.currency or 'USD').upper() != currency.upper()
        ):
            flash('该 PI 已有回款记录，不能修改币种；请先按业务流程处理原回款记录。', 'danger')
            return redirect(url_for('pi_edit', id=id))

        # Update PI record
        pi.customer_id = customer_id
        pi.salesperson = salesperson
        pi.currency = currency
        pi.exchange_rate = business_exchange_rate
        pi.company = company
        pi.issue_date = issue_date
        pi.payment_terms = payment_terms or '100% TT before shipment'
        pi.price_terms = price_terms
        pi.delivery_time = delivery_time
        _apply_bank_snapshot(
            pi, selected_account, bank_info, preserve_existing=not selected_account
        )
        total_amount = round(total_amount, 2)
        pi.total_amount = total_amount
        pi.shipping_cost = shipping_cost
        pi.shipping_note = shipping_note
        pi.shipping_note_en = shipping_note_en
        pi.shipping_address = shipping_address
        pi.notes = notes

        # Preserve stable PI item ids so procurement and packing references
        # continue to point at the same business rows.
        _reconcile_pi_items(pi, selected_items)

        db.session.flush()

        # Amount/customer changes must update the stored payment flag and both
        # customers' deal totals in the same transaction as the PI edit.
        active_payments = _active_payments(pi.id)
        paid_with_fee = sum(
            (payment.amount or 0) + (payment.fee or 0)
            for payment in active_payments
        )
        pi.received_amount = round(sum(
            payment.amount or 0 for payment in active_payments
        ), 2)
        pi.paid = paid_with_fee >= pi.grand_total
        customer_ids_to_recalculate = {old_customer_id, customer_id}
        for affected_customer_id in customer_ids_to_recalculate:
            affected_customer = db.session.get(Customer, affected_customer_id)
            if affected_customer:
                _recalculate_customer_deal(affected_customer)

        # Regenerate the saved files through the export workbench renderer.
        try:
            pdf_filename, excel_filename = _generate_default_pi_documents(pi)
            pi.pdf_path = pdf_filename
            pi.excel_path = excel_filename
        except Exception as e:
            db.session.rollback()
            flash(f'生成 PDF 失败：{str(e)}', 'danger')
            return render_edit_page()

        pi.version = (pi.version or 1) + 1
        after = _snapshot(pi, ['pi_number', 'customer_id', 'issue_date', 'salesperson', 'currency', 'exchange_rate', 'company', 'total_amount', 'shipping_cost', 'shipping_note', 'shipping_note_en', 'payment_terms', 'price_terms', 'delivery_time', 'bank_info', *BANK_SNAPSHOT_FIELDS, 'notes', 'version'])
        after['items'] = [item.to_dict() for item in pi.items]
        if structural_changes:
            after['structural_changes'] = structural_changes
        if change_reason:
            after['downstream_change_reason'] = change_reason
        summary = f'修改 PI：{pi.pi_number}'
        if change_reason:
            summary += f'（下游解锁原因：{change_reason[:120]}）'
        _audit('update', 'pi', pi.id, summary, before=before, after=after)
        db.session.commit()
        flash(f'PI {pi.pi_number} 已更新并重新生成 PDF。', 'success')
        return redirect(url_for('pi_detail', id=pi.id))

    # GET request
    return render_edit_page()


def _apply_form_to_pi(form, pi):
    """Apply form data to PI object in memory (no commit)."""
    if is_admin():
        pi.pi_number = form.get('pi_number', pi.pi_number).strip() or pi.pi_number
    pi.issue_date = datetime.strptime(form.get('issue_date', ''), '%Y-%m-%d').date() if form.get('issue_date') else pi.issue_date
    if is_admin():
        pi.salesperson = form.get('salesperson', '').strip() or pi.salesperson
        account_id = form.get('account_id', type=int)
        account = db.session.get(Account, account_id) if account_id else None
        _apply_bank_snapshot(
            pi, account, form.get('bank_info', ''), preserve_existing=not account
        )
    pi.currency = form.get('currency', pi.currency or 'USD').strip()
    if pi.currency not in {'USD', 'RMB'}:
        raise ValueError('不支持该币种。')
    pi.payment_terms = form.get('payment_terms', '').strip()
    pi.price_terms = _selectable_or_manual_field(
        'price_terms', form.get('price_terms', pi.price_terms or '')
    )
    pi.delivery_time = _selectable_or_manual_field(
        'delivery_time', form.get('delivery_time', pi.delivery_time or '')
    )
    pi.shipping_address = form.get('shipping_address', '').strip()
    previous_shipping_note = pi.shipping_note
    previous_shipping_note_en = pi.shipping_note_en
    pi.shipping_note = _managed_field_value(
        'shipping_note', form.get('shipping_note', ''), previous_shipping_note
    )
    pi.shipping_note_en = _managed_field_english(
        'shipping_note', form.get('shipping_note', ''),
        previous_shipping_note, previous_shipping_note_en,
    )
    pi.notes = form.get('notes', '').strip()
    pi.shipping_cost = _signed_float(form.get('shipping_cost', '0'), '客户费用/折扣')
    _require_customer_adjustment_type(pi.shipping_cost, pi.shipping_note)

    # Customer fields (in memory)
    if pi.customer:
        if is_admin():
            pi.customer.name = form.get('cust_name', '').strip() or pi.customer.name
            pi.customer.country = form.get('cust_country', '').strip()
        pi.customer.contact_person = form.get('cust_contact', '').strip()
        pi.customer.email = form.get('cust_email', '').strip()
        pi.customer.phone = form.get('cust_phone', '').strip()

    # Product items
    total = 0.0
    for item in pi.items:
        qty = _positive_int(form.get(f'qty_{item.id}', str(item.quantity)), 'Quantity')
        price = _nonnegative_float(form.get(f'price_{item.id}', str(item.unit_price)), 'Unit price')
        item.quantity = qty
        item.unit_price = price
        item.amount = round(price * qty, 2)
        total += item.amount
        if item.product and is_admin():
            prod_name = form.get(f'prod_name_{item.id}', '').strip()
            if prod_name:
                item.product.name = prod_name
            item.product.product_code = form.get(f'prod_code_{item.id}', '').strip()
            item.product.specification = form.get(f'prod_spec_{item.id}', '').strip()
    pi.total_amount = round(total, 2)

    # Company override — store on pi object for PDF generator to pick up
    if is_admin():
        company_name = form.get('company_name', '').strip()
        if company_name:
            pi._company_name_override = company_name
        company_addr = form.get('company_addr', '').strip()
        if company_addr:
            pi._company_addr_override = company_addr
        company_short = form.get('company_short', '').strip()
        if company_short:
            pi._company_short_override = company_short


def _template_file_path(template):
    filename = os.path.basename(template.filename or '')
    if not filename or filename != (template.filename or ''):
        raise TemplateError('模板文件路径无效。')
    path = os.path.join(app.config['DOCUMENT_TEMPLATE_DIR'], filename)
    if not os.path.isfile(path):
        raise TemplateError('模板文件不存在，请联系管理员重新上传。')
    return path


def _active_export_templates():
    return DocumentTemplate.query.filter_by(active=True, template_type='xlsx').order_by(
        DocumentTemplate.is_default.desc(), DocumentTemplate.id.asc()
    ).all()


def _export_template(template_id=None):
    query = DocumentTemplate.query.filter_by(active=True, template_type='xlsx')
    template = query.filter_by(id=template_id).first() if template_id else None
    if not template:
        template = query.filter_by(is_default=True).first()
    if not template:
        template = query.filter_by(code='system-default').first()
    if not template:
        raise TemplateError('当前没有可用的 PI 模板。')
    return template


def _pi_export_copy(pi):
    """Create a plain in-memory copy that SQLAlchemy can never persist."""
    customer = pi.customer
    customer_copy = SimpleNamespace(
        name=customer.name if customer else '',
        contact_person=customer.contact_person if customer else '',
        country=customer.country if customer else '',
        email=customer.email if customer else '',
        phone=customer.phone if customer else '',
        address=customer.address if customer else '',
        notes=customer.notes if customer else '',
    )
    item_copies = []
    for item in pi.items:
        product = item.product
        product_copy = SimpleNamespace(
            name=product.name if product else '',
            product_code=product.product_code if product else '',
            specification=product.specification if product else '',
            image=product.image if product else '',
        )
        item_copies.append(SimpleNamespace(
            id=item.id,
            quantity=item.quantity,
            unit_price=item.unit_price,
            amount=item.amount,
            product=product_copy,
        ))
    export_copy = SimpleNamespace(
        id=pi.id,
        pi_number=pi.pi_number,
        issue_date=pi.issue_date,
        salesperson=pi.salesperson,
        currency=pi.currency,
        company=pi.company,
        payment_terms=pi.payment_terms,
        price_terms=pi.price_terms,
        delivery_time=pi.delivery_time,
        bank_info=pi.bank_info,
        shipping_address=pi.shipping_address,
        shipping_note=pi.shipping_note,
        shipping_note_en=pi.shipping_note_en,
        notes=pi.notes,
        shipping_cost=pi.shipping_cost,
        total_amount=pi.total_amount,
        customer=customer_copy,
        items=item_copies,
        _upload_dir_override=app.config['UPLOAD_DIR'],
    )
    for field in BANK_SNAPSHOT_FIELDS:
        setattr(export_copy, field, getattr(pi, field, '') or '')
    return export_copy


def _apply_export_form(form, export_pi):
    """Apply one-off export edits to a non-ORM copy.

    PI number, owner and currency are intentionally locked for every role.
    Sales users also cannot alter customer identity, product identity, company,
    or bank details from the export screen.
    """
    if form.get('issue_date'):
        try:
            export_pi.issue_date = datetime.strptime(form.get('issue_date'), '%Y-%m-%d').date()
        except ValueError as exc:
            raise ValueError('日期格式不正确。') from exc
    export_pi.payment_terms = form.get('payment_terms', '').strip()
    export_pi.price_terms = _selectable_or_manual_field(
        'price_terms', form.get('price_terms', export_pi.price_terms or '')
    )
    export_pi.delivery_time = _selectable_or_manual_field(
        'delivery_time', form.get('delivery_time', export_pi.delivery_time or '')
    )
    export_pi.shipping_address = form.get('shipping_address', '').strip()
    export_pi.notes = form.get('notes', '').strip()
    previous_shipping_note = export_pi.shipping_note
    previous_shipping_note_en = export_pi.shipping_note_en
    export_pi.shipping_note = _managed_field_value(
        'shipping_note', form.get('shipping_note', ''), previous_shipping_note
    )
    export_pi.shipping_note_en = _managed_field_english(
        'shipping_note', form.get('shipping_note', ''),
        previous_shipping_note, previous_shipping_note_en,
    )
    export_pi.shipping_cost = _signed_float(
        form.get('shipping_cost', '0'), '客户费用/折扣'
    )
    _require_customer_adjustment_type(export_pi.shipping_cost, export_pi.shipping_note)

    if is_admin():
        account_id = form.get('account_id', type=int)
        account = db.session.get(Account, account_id) if account_id else None
        _apply_bank_snapshot(
            export_pi, account, form.get('bank_info', ''), preserve_existing=not account
        )
        export_pi.customer.name = form.get('cust_name', '').strip() or export_pi.customer.name
        export_pi.customer.country = form.get('cust_country', '').strip()
        company_name = form.get('company_name', '').strip()
        company_address = form.get('company_addr', '').strip()
        if company_name:
            export_pi._company_name_override = company_name
        if company_address:
            export_pi._company_addr_override = company_address

    export_pi.customer.contact_person = form.get('cust_contact', '').strip()
    export_pi.customer.email = form.get('cust_email', '').strip()
    export_pi.customer.phone = form.get('cust_phone', '').strip()
    export_pi.customer.address = form.get('cust_address', '').strip()

    total = 0.0
    for item in export_pi.items:
        item.quantity = _positive_int(
            form.get(f'qty_{item.id}', str(item.quantity)), '数量'
        )
        item.unit_price = _nonnegative_float(
            form.get(f'price_{item.id}', str(item.unit_price)), '单价'
        )
        if is_admin():
            item.product.name = (
                form.get(f'prod_name_{item.id}', '').strip() or item.product.name
            )
            item.product.product_code = form.get(f'prod_code_{item.id}', '').strip()
            item.product.specification = form.get(f'prod_spec_{item.id}', '').strip()
        item.amount = round(item.quantity * item.unit_price, 2)
        total += item.amount
    export_pi.total_amount = round(total, 2)


def _export_copy_snapshot(export_pi):
    return {
        'issue_date': export_pi.issue_date.isoformat() if export_pi.issue_date else '',
        'payment_terms': export_pi.payment_terms,
        'price_terms': export_pi.price_terms,
        'delivery_time': export_pi.delivery_time,
        'bank_info': export_pi.bank_info,
        'bank_snapshot': {
            field: getattr(export_pi, field, '') or ''
            for field in BANK_SNAPSHOT_FIELDS
        },
        'shipping_address': export_pi.shipping_address,
        'shipping_note': export_pi.shipping_note,
        'shipping_note_en': export_pi.shipping_note_en,
        'notes': export_pi.notes,
        'shipping_cost': export_pi.shipping_cost,
        'customer': {
            'name': export_pi.customer.name,
            'contact_person': export_pi.customer.contact_person,
            'country': export_pi.customer.country,
            'email': export_pi.customer.email,
            'phone': export_pi.customer.phone,
            'address': export_pi.customer.address,
            'notes': export_pi.customer.notes,
        },
        'items': [
            {
                'id': item.id,
                'name': item.product.name,
                'code': item.product.product_code,
                'specification': item.product.specification,
                'quantity': item.quantity,
                'unit_price': item.unit_price,
                'amount': item.amount,
            }
            for item in export_pi.items
        ],
    }


def _render_pi_export(export_pi, template, output_format, work_dir, preview=False):
    sp = Salesperson.query.filter_by(name=export_pi.salesperson).first()
    salesperson_info = {'phone': sp.phone, 'email': sp.email} if sp else {}
    safe_number = secure_filename(export_pi.pi_number) or f'PI-{export_pi.id}'

    if template.template_type == 'system':
        if output_format == 'xlsx' and not preview:
            filename = generate_pi_excel(export_pi, work_dir)
            return os.path.join(work_dir, filename), 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        filename = generate_pi_pdf(export_pi, work_dir, salesperson_info)
        return os.path.join(work_dir, filename), 'application/pdf'

    template_path = _template_file_path(template)
    excel_path = os.path.join(work_dir, f'{safe_number}.xlsx')
    render_excel_template(
        template_path, export_pi, excel_path,
        salesperson_info=salesperson_info,
        upload_dir=app.config['UPLOAD_DIR'],
    )
    if template.code == 'system-default':
        apply_system_default_page_setup(excel_path)
    if output_format == 'xlsx' and not preview:
        return excel_path, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    pdf_path = os.path.join(work_dir, f'{safe_number}.pdf')
    convert_excel_to_pdf(excel_path, pdf_path)
    return pdf_path, 'application/pdf'


def _generate_default_pi_documents(pi):
    """Persist the exact files produced by the default export-workbench template."""
    db.session.flush()
    # Editing replaces the relationship in the current session.  Expire it so
    # the export copy sees the new rows, in their database insertion order.
    db.session.expire(pi, ['items'])
    pi_full = PI.query.options(
        joinedload(PI.customer),
        joinedload(PI.items).joinedload(PIItem.product),
    ).filter_by(id=pi.id).populate_existing().one()
    export_pi = _pi_export_copy(pi_full)
    template = _export_template()
    safe_number = secure_filename(pi.pi_number) or f'PI-{pi.id}'
    work_dir = tempfile.mkdtemp(prefix='pi-saved-export-')
    os.makedirs(app.config['PDF_DIR'], exist_ok=True)
    try:
        pdf_source, _ = _render_pi_export(
            export_pi, template, 'pdf', work_dir, preview=False
        )
        excel_source, _ = _render_pi_export(
            export_pi, template, 'xlsx', work_dir, preview=False
        )
        filenames = (f'{safe_number}.pdf', f'{safe_number}.xlsx')
        for source, filename in zip((pdf_source, excel_source), filenames):
            temporary_target = os.path.join(
                app.config['PDF_DIR'], f'.{uuid.uuid4().hex}-{filename}'
            )
            final_target = os.path.join(app.config['PDF_DIR'], filename)
            try:
                shutil.copy2(source, temporary_target)
                os.replace(temporary_target, final_target)
            finally:
                if os.path.exists(temporary_target):
                    os.remove(temporary_target)
        return filenames
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


@app.route('/document-templates')
@admin_required
def document_template_list():
    templates = DocumentTemplate.query.filter_by(template_type='xlsx').order_by(
        DocumentTemplate.is_default.desc(), DocumentTemplate.id.asc()
    ).all()
    packing_templates = DocumentTemplate.query.filter(
        DocumentTemplate.template_type.in_(['packing_a4', 'packing_compact'])
    ).order_by(DocumentTemplate.id.asc()).all()
    return render_template(
        'document_templates.html', templates=templates,
        packing_templates=packing_templates,
        placeholder_groups=PLACEHOLDER_GROUPS,
    )


@app.route('/document-templates/add', methods=['POST'])
@admin_required
def document_template_add():
    if not _require_current_password():
        return redirect(url_for('document_template_list'))
    name = request.form.get('name', '').strip()
    upload = request.files.get('template_file')
    if not name or len(name) > 200:
        flash('模板名称不能为空且不能超过 200 个字符。', 'danger')
        return redirect(url_for('document_template_list'))
    if not upload or not upload.filename or not upload.filename.lower().endswith('.xlsx'):
        flash('请选择 .xlsx 格式的模板文件。', 'danger')
        return redirect(url_for('document_template_list'))

    filename = f'{uuid.uuid4().hex}.xlsx'
    path = os.path.join(app.config['DOCUMENT_TEMPLATE_DIR'], filename)
    try:
        upload.save(path)
        validate_template(path)
    except (TemplateError, OSError) as exc:
        if os.path.exists(path):
            os.remove(path)
        flash(str(exc), 'danger')
        return redirect(url_for('document_template_list'))

    make_default = request.form.get('is_default') == '1'
    if make_default:
        DocumentTemplate.query.update({'is_default': False})
    template = DocumentTemplate(
        name=name,
        code='custom-' + uuid.uuid4().hex,
        template_type='xlsx',
        filename=filename,
        active=True,
        is_default=make_default,
        notes=request.form.get('notes', '').strip()[:1000],
        created_by=get_current_user().username,
    )
    db.session.add(template)
    db.session.flush()
    _audit('create', 'document_template', template.id, f'新增单据模板：{template.name}',
           after=template.to_dict())
    db.session.commit()
    flash('单据模板已添加，可在导出工作台中选择。', 'success')
    return redirect(url_for('document_template_list'))


@app.route('/document-templates/<int:id>/edit', methods=['POST'])
@admin_required
def document_template_edit(id):
    template = DocumentTemplate.query.get_or_404(id)
    if not _require_current_password():
        return redirect(url_for('document_template_list'))
    if template.template_type not in {'xlsx', 'packing_a4', 'packing_compact'}:
        flash('当前模板不是可编辑的 Excel 模板。', 'danger')
        return redirect(url_for('document_template_list'))

    name = request.form.get('name', '').strip()
    notes = request.form.get('notes', '').strip()[:1000]
    upload = request.files.get('template_file')
    if not name or len(name) > 200:
        flash('模板名称不能为空且不能超过 200 个字符。', 'danger')
        return redirect(url_for('document_template_list'))
    if upload and upload.filename and not upload.filename.lower().endswith('.xlsx'):
        flash('替换文件必须是 .xlsx 格式。', 'danger')
        return redirect(url_for('document_template_list'))

    new_filename = ''
    new_path = ''
    if upload and upload.filename:
        new_filename = f'{uuid.uuid4().hex}.xlsx'
        new_path = os.path.join(app.config['DOCUMENT_TEMPLATE_DIR'], new_filename)
        try:
            upload.save(new_path)
            if template.template_type == 'xlsx':
                validate_template(new_path)
            else:
                _validate_packing_template(
                    new_path, template.template_type == 'packing_compact'
                )
        except (TemplateError, OSError) as exc:
            if new_path and os.path.exists(new_path):
                os.remove(new_path)
            flash(str(exc), 'danger')
            return redirect(url_for('document_template_list'))

    before = template.to_dict()
    template.name = name
    template.notes = notes
    if new_filename:
        template.filename = new_filename
    if template.code == 'system-default':
        template.active = True
    _audit(
        'update', 'document_template', template.id,
        f'编辑单据模板：{template.name}', before=before, after=template.to_dict(),
    )
    db.session.commit()
    flash(
        '模板源文件和说明已更新，后续导出立即使用新版本。'
        if new_filename else '模板信息已更新。',
        'success',
    )
    return redirect(url_for('document_template_list'))


@app.route('/document-templates/<int:id>/toggle', methods=['POST'])
@admin_required
def document_template_toggle(id):
    template = DocumentTemplate.query.get_or_404(id)
    if not _require_current_password():
        return redirect(url_for('document_template_list'))
    if template.code == 'system-default' and template.active:
        flash('系统默认模板必须保持启用，作为导出备用。', 'warning')
        return redirect(url_for('document_template_list'))
    if template.is_default and template.active:
        flash('默认模板不能直接停用，请先把其他模板设为默认。', 'warning')
        return redirect(url_for('document_template_list'))
    before = template.to_dict()
    template.active = not template.active
    _audit('update', 'document_template', template.id, f'切换模板状态：{template.name}',
           before=before, after=template.to_dict())
    db.session.commit()
    flash('模板状态已更新。', 'success')
    return redirect(url_for('document_template_list'))


@app.route('/document-templates/<int:id>/default', methods=['POST'])
@admin_required
def document_template_default(id):
    template = DocumentTemplate.query.get_or_404(id)
    if not _require_current_password():
        return redirect(url_for('document_template_list'))
    if not template.active:
        flash('请先启用该模板，再设为默认。', 'warning')
        return redirect(url_for('document_template_list'))
    old_default = DocumentTemplate.query.filter_by(is_default=True).first()
    DocumentTemplate.query.update({'is_default': False})
    template.is_default = True
    _audit('update', 'document_template', template.id, f'设置默认模板：{template.name}',
           before={'previous_default': old_default.name if old_default else ''},
           after={'default_template': template.name})
    db.session.commit()
    flash('默认导出模板已更新。', 'success')
    return redirect(url_for('document_template_list'))


@app.route('/document-templates/<int:id>/delete', methods=['POST'])
@admin_required
def document_template_delete(id):
    template = DocumentTemplate.query.get_or_404(id)
    if not _require_current_password():
        return redirect(url_for('document_template_list'))
    if template.code == 'system-default':
        flash('系统默认模板不能删除。', 'warning')
        return redirect(url_for('document_template_list'))
    if request.form.get('confirm_value', '').strip() != template.name:
        flash('输入内容与模板名称不一致，未执行删除。', 'danger')
        return redirect(url_for('document_template_list'))
    before = template.to_dict()
    filename = os.path.basename(template.filename or '')
    path = os.path.join(app.config['DOCUMENT_TEMPLATE_DIR'], filename) if filename else ''
    if template.is_default:
        fallback = DocumentTemplate.query.filter_by(code='system-default').first()
        if fallback:
            fallback.active = True
            fallback.is_default = True
    _audit('delete', 'document_template', template.id, f'删除单据模板：{template.name}', before=before)
    db.session.delete(template)
    db.session.commit()
    if path:
        try:
            os.remove(path)
        except OSError:
            current_app.logger.warning('Could not remove document template file: %s', path)
    flash('模板已删除，历史 PI 和历史导出审计不受影响。', 'success')
    return redirect(url_for('document_template_list'))


@app.route('/document-templates/<int:id>/source')
@admin_required
def document_template_source(id):
    template = DocumentTemplate.query.get_or_404(id)
    if template.template_type not in {'xlsx', 'packing_a4', 'packing_compact'}:
        abort(404)
    path = _template_file_path(template)
    return send_file(path, as_attachment=True, download_name=f'{secure_filename(template.name) or "pi-template"}.xlsx')


@app.route('/document-templates/example')
@admin_required
def document_template_example():
    work_dir = tempfile.mkdtemp(prefix='pi-template-example-')
    path = os.path.join(work_dir, 'PI-template-example.xlsx')
    create_placeholder_template(path)

    response = send_file(path, as_attachment=True, download_name='PI-template-example.xlsx')
    response.call_on_close(lambda: shutil.rmtree(work_dir, ignore_errors=True))
    return response


@app.route('/pi/<int:id>/export', methods=['GET', 'POST'])
@login_required
def pi_export(id):
    """Export workbench. Form edits are applied only to a plain Python copy."""
    pi = PI.query.options(
        joinedload(PI.customer),
        joinedload(PI.items).joinedload(PIItem.product),
    ).get_or_404(id)
    require_pi_access(pi)

    templates = _active_export_templates()
    if request.method == 'GET':
        selected_template = _export_template(request.args.get('template_id', type=int))
        return render_template(
            'live_edit_pi.html', pi=pi, templates=templates,
            selected_template=selected_template,
        )

    output_format = request.form.get('output_format', 'pdf').lower()
    mode = request.form.get('mode', 'download').lower()
    if output_format not in {'pdf', 'xlsx'} or mode not in {'preview', 'download'}:
        return jsonify({'error': '导出参数无效。'}), 400
    work_dir = tempfile.mkdtemp(prefix='pi-export-')
    try:
        template = _export_template(request.form.get('template_id', type=int))
        export_pi = _pi_export_copy(pi)
        original_snapshot = _export_copy_snapshot(export_pi)
        _apply_export_form(request.form, export_pi)
        export_snapshot = _export_copy_snapshot(export_pi)
        output_path, mimetype = _render_pi_export(
            export_pi, template, output_format, work_dir, preview=(mode == 'preview')
        )
        actual_format = 'pdf' if mode == 'preview' else output_format
        changed_fields = [
            key for key in export_snapshot if export_snapshot[key] != original_snapshot.get(key)
        ]
        _audit(
            'export', 'pi', pi.id,
            f'导出 PI：{pi.pi_number}（{template.name} / {actual_format.upper()}）',
            after={
                'template_id': template.id,
                'template_name': template.name,
                'format': actual_format,
                'mode': mode,
                'temporary_changed_fields': changed_fields,
                'original_pi_unchanged': True,
            },
        )
        db.session.commit()
    except (TemplateError, ValueError) as exc:
        db.session.rollback()
        shutil.rmtree(work_dir, ignore_errors=True)
        return jsonify({'error': str(exc)}), 400
    except Exception:
        db.session.rollback()
        shutil.rmtree(work_dir, ignore_errors=True)
        current_app.logger.exception('PI export failed')
        return jsonify({'error': '导出失败，请联系管理员查看日志。'}), 500

    download_name = f'{secure_filename(pi.pi_number) or "PI"}_{secure_filename(template.name) or "template"}.{actual_format}'
    response = send_file(
        output_path,
        mimetype=mimetype,
        as_attachment=(mode == 'download'),
        download_name=download_name,
    )
    response.call_on_close(lambda: shutil.rmtree(work_dir, ignore_errors=True))
    return response


@app.route('/pi/<int:id>/live-edit')
@login_required
def pi_live_edit(id):
    """Keep old bookmarks working; saving through this path is no longer allowed."""
    pi = PI.query.get_or_404(id)
    require_pi_access(pi)
    return redirect(url_for('pi_export', id=id))


# ═══════════════════════════════════════════════════════════════════════
#  ROUTES — Procurement (采购)
# ═══════════════════════════════════════════════════════════════════════

def _procurement_gaps(pi):
    """Return PI items that have not been covered by confirmed purchase data."""
    purchased = dict(
        db.session.query(Procurement.pi_item_id, func.sum(Procurement.quantity))
        .filter(
            Procurement.pi_id == pi.id,
            Procurement.supplier_id.isnot(None),
            Procurement.unit_price >= 0,
        )
        .group_by(Procurement.pi_item_id)
        .all()
    )
    gaps = []
    for item in pi.items:
        required = int(item.quantity or 0)
        actual = int(purchased.get(item.id, 0) or 0)
        if required <= 0 or actual < required:
            product_name = item.product.name if item.product else f'产品项 #{item.id}'
            gaps.append({
                'pi_item_id': item.id,
                'product': product_name,
                'required': required,
                'purchased': actual,
            })
    return gaps

@app.route('/procurement')
@admin_required
def procurement_select():
    """Select a PI to start procurement."""
    if not is_admin(): return redirect(url_for('index'))
    salesperson_filter, date_from, date_to, preset = _report_filter_values()
    pi_query = PI.query.options(
        joinedload(PI.customer),
        selectinload(PI.items).joinedload(PIItem.product),
    ).filter(
        PI.received_amount > 0,
        PI.deleted_at.is_(None),
    )
    pi_query = _apply_report_filters(
        pi_query, salesperson_filter, date_from, date_to
    )
    pis = pi_query.order_by(PI.id.desc()).all()
    pi_complete = {pi.id for pi in pis if pi.procurement_is_complete}
    resp = make_response(render_template(
        'procurement_select.html',
        pis=pis,
        pi_complete=pi_complete,
        salesperson_filter=salesperson_filter,
        date_from=date_from,
        date_to=date_to,
        preset=preset,
    ))
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return resp


@app.route('/procurement/<int:pi_id>')
@admin_required
def procurement_page(pi_id):
    """Procurement page for a specific PI."""
    if not is_admin(): return redirect(url_for('index'))
    readonly = request.args.get('readonly', '0') == '1'
    pi = PI.query.options(
        db.joinedload(PI.customer),
        db.joinedload(PI.items).joinedload(PIItem.product)
    ).get_or_404(pi_id)
    if pi.deleted_at is not None:
        abort(404)
    suppliers = [s.to_dict() for s in Supplier.query.order_by(Supplier.name).all()]
    existing = {}
    for p in Procurement.query.filter_by(pi_id=pi_id).all():
        existing[str(p.pi_item_id)] = p.to_dict()
    resp = make_response(render_template(
        'procurement.html',
        pi=pi,
        suppliers=suppliers,
        existing=existing,
        readonly=readonly,
        pi_exchange_rate=_pi_exchange_rate(pi),
    ))
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return resp


def _supplier_export_groups(pi, data):
    """Validate browser procurement rows and group them by trusted suppliers."""
    items = data.get('items', [])
    if not isinstance(items, list) or not items:
        raise ValueError('请至少填写一项有效采购明细。')
    purchase_date = str(data.get('procurement_date', '') or date.today().isoformat()).strip()
    try:
        date.fromisoformat(purchase_date)
    except ValueError as exc:
        raise ValueError('采购日期格式不正确。') from exc

    pi_items = {item.id: item for item in pi.items}
    normalized = []
    supplier_ids = set()
    seen_item_ids = set()
    for item in items:
        try:
            item_id = int(item.get('pi_item_id'))
            supplier_id = int(item.get('supplier_id'))
            unit_price = float(item.get('unit_price'))
            quantity = int(item.get('quantity'))
        except (AttributeError, TypeError, ValueError) as exc:
            raise ValueError('采购明细包含无效数值。') from exc
        if item_id not in pi_items or item_id in seen_item_ids:
            raise ValueError('采购明细与当前 PI 不匹配，请刷新后重试。')
        if not math.isfinite(unit_price) or unit_price < 0 or quantity <= 0:
            raise ValueError('采购数量必须大于 0，采购单价不能为负数。')
        seen_item_ids.add(item_id)
        supplier_ids.add(supplier_id)
        normalized.append({
            'pi_item': pi_items[item_id],
            'supplier_id': supplier_id,
            'unit_price': unit_price,
            'quantity': quantity,
            'note': str(item.get('note', '') or '')[:1000],
        })

    suppliers = {
        supplier.id: supplier
        for supplier in Supplier.query.filter(Supplier.id.in_(supplier_ids)).all()
    }
    if len(suppliers) != len(supplier_ids):
        raise ValueError('所选供应商不存在，请刷新后重试。')
    groups = {}
    for item in normalized:
        supplier_id = item['supplier_id']
        if supplier_id not in groups:
            groups[supplier_id] = {
                'supplier': suppliers[supplier_id],
                'items': [],
            }
        groups[supplier_id]['items'].append(item)
    return purchase_date, groups


def _supplier_order_filename(pi, supplier, extension='xlsx'):
    label = ''.join(
        character for character in (supplier.name or '')
        if character not in '/\\\0\r\n'
    ).strip()[:80] or f'供应商{supplier.id}'
    pi_number = secure_filename(pi.pi_number) or f'PI-{pi.id}'
    return f'采购单_{label}_{pi_number}.{extension}'


@app.route('/procurement/<int:pi_id>/supplier-orders/export', methods=['POST'])
@admin_required
def procurement_supplier_orders_export(pi_id):
    """Export current form rows as one XLSX or a ZIP split by supplier."""
    if not is_admin():
        abort(403)
    pi = PI.query.options(
        db.joinedload(PI.items).joinedload(PIItem.product)
    ).filter_by(id=pi_id).first_or_404()
    if pi.deleted_at is not None:
        abort(404)
    if (pi.received_amount or 0) <= 0:
        return jsonify({'success': False, 'error': '该 PI 尚未回款，不能导出采购单。'}), 400
    data = request.get_json(silent=True) or {}
    try:
        purchase_date, groups = _supplier_export_groups(pi, data)
    except ValueError as exc:
        return jsonify({'success': False, 'error': str(exc)}), 400

    requested_supplier_id = data.get('supplier_id')
    if requested_supplier_id not in (None, ''):
        try:
            requested_supplier_id = int(requested_supplier_id)
        except (TypeError, ValueError):
            return jsonify({'success': False, 'error': '供应商参数无效。'}), 400
        if requested_supplier_id not in groups:
            return jsonify({'success': False, 'error': '当前采购明细中没有该供应商的产品。'}), 400
        selected_groups = {requested_supplier_id: groups[requested_supplier_id]}
    else:
        selected_groups = groups

    buyer_company = (
        'Changzhou QISUO Welding and Cutting Equipment Co., Ltd.'
        if pi.company == 'qisuo' else COMPANY_CONFIG['name']
    )

    def create_workbook(group):
        return generate_supplier_purchase_order(
            pi=pi,
            supplier=group['supplier'],
            entries=group['items'],
            purchase_date=purchase_date,
            buyer_company=buyer_company,
            buyer_address=COMPANY_CONFIG.get('address', ''),
            upload_dir=current_app.config['UPLOAD_DIR'],
        )

    if len(selected_groups) == 1 and requested_supplier_id not in (None, ''):
        group = next(iter(selected_groups.values()))
        response = send_file(
            BytesIO(create_workbook(group)),
            as_attachment=True,
            download_name=_supplier_order_filename(pi, group['supplier']),
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
    else:
        archive = BytesIO()
        with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as bundle:
            for group in selected_groups.values():
                bundle.writestr(
                    _supplier_order_filename(pi, group['supplier']),
                    create_workbook(group),
                )
        archive.seek(0)
        response = send_file(
            archive,
            as_attachment=True,
            download_name=f'供应商采购单_{secure_filename(pi.pi_number) or pi.id}.zip',
            mimetype='application/zip',
        )
    response.headers['Cache-Control'] = 'no-store'
    return response


@app.route('/api/procurement/save', methods=['POST'])
@admin_required
def api_procurement_save():
    """Save procurement items for a PI."""
    if not is_admin(): return jsonify({'success': False, 'error': '仅管理员可操作'}), 403
    data = request.get_json(silent=True) or {}
    try:
        pi_id = int(data.get('pi_id'))
        supplier_freight_cost = float(
            data.get('supplier_freight_cost', data.get('actual_shipping', 0)) or 0
        )
    except (TypeError, ValueError):
        return jsonify({'success': False, 'error': '采购数据格式不正确。'}), 400
    draft = bool(data.get('draft'))
    items = data.get('items', [])
    if not isinstance(items, list):
        return jsonify({'success': False, 'error': '采购明细格式不正确。'}), 400
    if not math.isfinite(supplier_freight_cost) or supplier_freight_cost < 0:
        return jsonify({'success': False, 'error': '供应商采购运费不能为负数。'}), 400
    proc_date = str(data.get('procurement_date', '') or date.today().isoformat()).strip()
    try:
        date.fromisoformat(proc_date)
    except ValueError:
        return jsonify({'success': False, 'error': '采购日期格式不正确。'}), 400

    pi = PI.query.options(db.joinedload(PI.items).joinedload(PIItem.product)).filter_by(id=pi_id).first_or_404()
    if pi.deleted_at is not None:
        abort(404)
    if (pi.received_amount or 0) <= 0:
        return jsonify({'success': False, 'error': '该 PI 尚未回款，不能开始采购。'}), 400
    if pi.shipping_completed:
        return jsonify({
            'success': False,
            'error': '该 PI 已登记发货。请先在发货记录中单独撤销发货，再修改采购单。',
        }), 409
    if pi.procurement_confirmed:
        return jsonify({'success': False, 'error': '采购单已确认。如需修改，请先取消“采购完成”。'}), 409
    try:
        business_exchange_rate = float(data.get('exchange_rate', _pi_exchange_rate(pi)))
    except (TypeError, ValueError):
        return jsonify({'success': False, 'error': '本单业务汇率格式不正确。'}), 400
    if not math.isfinite(business_exchange_rate) or business_exchange_rate <= 0:
        return jsonify({'success': False, 'error': '本单业务汇率必须大于 0。'}), 400

    allowed_item_ids = {item.id for item in pi.items}
    normalized_items = []
    seen_item_ids = set()
    for it in items:
        if not isinstance(it, dict) or 'unit_price' not in it or it.get('unit_price') in (None, ''):
            return jsonify({'success': False, 'error': '采购明细缺少采购单价（允许填 0）。'}), 400
        try:
            item_id = int(it.get('pi_item_id'))
            supplier_id = int(it.get('supplier_id'))
            unit_price = float(it.get('unit_price'))
            quantity = int(it.get('quantity', 0) or 0)
        except (AttributeError, TypeError, ValueError):
            return jsonify({'success': False, 'error': '采购明细包含无效数值。'}), 400
        if item_id not in allowed_item_ids or item_id in seen_item_ids:
            return jsonify({'success': False, 'error': '采购明细与当前 PI 不匹配，请刷新后重试。'}), 400
        if not db.session.get(Supplier, supplier_id):
            return jsonify({'success': False, 'error': '所选供应商不存在，请刷新后重试。'}), 400
        if quantity <= 0 or not math.isfinite(unit_price) or unit_price < 0:
            return jsonify({'success': False, 'error': '采购数量必须大于 0，采购单价不能为负数。'}), 400
        seen_item_ids.add(item_id)
        normalized_items.append((item_id, supplier_id, unit_price, quantity, str(it.get('note', ''))[:1000]))

    if not normalized_items and not draft:
        return jsonify({'success': False, 'error': '请至少填写一项有效采购明细。'}), 400

    Procurement.query.filter_by(pi_id=pi_id).delete(synchronize_session=False)
    for item_id, supplier_id, unit_price, quantity, note in normalized_items:
        proc = Procurement(
            pi_id=pi_id,
            pi_item_id=item_id,
            supplier_id=supplier_id,
            unit_price=unit_price,
            quantity=quantity,
            total=unit_price * quantity,
            procurement_date=proc_date,
            note=note,
        )
        db.session.add(proc)

    pi.exchange_rate = business_exchange_rate
    pi.supplier_freight_cost = supplier_freight_cost
    pi.procurement_status = '部分采购' if normalized_items else '待采购'
    _audit('update', 'procurement', pi.id, '暂存采购单明细' if draft else '保存采购单明细',
           after={
               'item_count': len(normalized_items),
               'supplier_freight_cost': supplier_freight_cost,
               'exchange_rate': business_exchange_rate,
               'draft': draft,
           })
    db.session.flush()
    gaps = _procurement_gaps(pi)
    db.session.commit()
    return jsonify({
        'success': True,
        'draft': draft,
        'complete': not gaps,
        'missing_items': gaps,
    })


@app.route('/api/procurement/<int:pi_id>/confirm', methods=['POST'])
@admin_required
def api_procurement_confirm(pi_id):
    """Confirm a complete purchase order or unlock it for correction."""
    if not is_admin(): return jsonify({'success': False}), 403
    pi = PI.query.options(db.joinedload(PI.items).joinedload(PIItem.product)).filter_by(id=pi_id).first_or_404()
    if pi.deleted_at is not None:
        abort(404)
    if (pi.received_amount or 0) <= 0:
        return jsonify({'success': False, 'error': '该 PI 尚未回款，不能确认采购。'}), 400
    action = request.args.get('action', 'confirm')
    if action == 'unconfirm':
        if pi.shipping_completed:
            return jsonify({'success': False, 'error': '请先撤销“发货完成”，再修改采购单。'}), 409
        pi.procurement_confirmed = False
        pi.procurement_status = '部分采购' if pi.procurements else '待采购'
        _audit('update', 'procurement', pi.id, '取消采购完成确认')
    elif action == 'confirm':
        gaps = _procurement_gaps(pi)
        if gaps:
            names = '、'.join(gap['product'] for gap in gaps[:5])
            return jsonify({
                'success': False,
                'error': f'采购单尚未完整，以下产品未采购足量：{names}',
                'missing_items': gaps,
            }), 400
        pi.procurement_confirmed = True
        pi.procurement_status = '采购完成'
        _audit('update', 'procurement', pi.id, '确认采购完成')
    else:
        return jsonify({'success': False, 'error': '采购确认操作无效。'}), 400
    db.session.commit()
    return jsonify({'success': True, 'confirmed': pi.procurement_confirmed,
                    'procurement_status': pi.effective_procurement_status})


def _shipping_record_payload(pi):
    """Return a stable UI payload without exposing unrelated PI data."""
    unavailable_reason = ''
    if (pi.received_amount or 0) <= 0:
        unavailable_reason = '该 PI 尚未回款，不能登记发货。'
    elif not pi.procurement_is_complete:
        unavailable_reason = '采购尚未完成，暂时不能登记发货。'
    return {
        'success': True,
        'pi_number': pi.pi_number,
        'procurement_status': pi.effective_procurement_status,
        'shipping_completed': bool(pi.shipping_completed),
        'can_ship': bool(not pi.shipping_completed and not unavailable_reason),
        'unavailable_reason': unavailable_reason,
        'shipping_date': pi.shipping_date.isoformat() if pi.shipping_date else '',
        'tracking_no': pi.shipping_tracking_no or '',
        'note': pi.shipping_record_note or '',
        'recorded_at': (
            pi.shipping_recorded_at.strftime('%Y-%m-%d %H:%M')
            if pi.shipping_recorded_at else ''
        ),
        'recorded_by': pi.shipping_recorded_by or '',
    }


@app.route('/api/pi/<int:pi_id>/shipping-record', methods=['GET', 'POST'])
@login_required
def api_pi_shipping_record(pi_id):
    """Read or create the shipment record for an accessible PI."""
    pi = PI.query.options(
        joinedload(PI.items).joinedload(PIItem.product)
    ).filter_by(id=pi_id).first_or_404()
    require_pi_access(pi)

    if request.method == 'GET':
        return jsonify(_shipping_record_payload(pi))

    if pi.shipping_completed:
        return jsonify({'success': False, 'error': '该 PI 已登记发货，请直接查看发货记录。'}), 409
    if (pi.received_amount or 0) <= 0:
        return jsonify({'success': False, 'error': '该 PI 尚未回款，不能登记发货。'}), 400
    if not pi.procurement_is_complete or _procurement_gaps(pi):
        return jsonify({'success': False, 'error': '采购尚未完成，暂时不能登记发货。'}), 400

    payload = request.get_json(silent=True) or request.form
    shipping_date_value = str(payload.get('shipping_date') or '').strip()
    try:
        parsed_shipping_date = date.fromisoformat(shipping_date_value)
    except ValueError:
        return jsonify({'success': False, 'error': '请选择正确的发货日期。'}), 400

    tracking_no = str(payload.get('tracking_no') or '').strip()
    note = str(payload.get('note') or '').strip()
    if len(tracking_no) > 200:
        return jsonify({'success': False, 'error': '物流单号不能超过 200 个字符。'}), 400
    if len(note) > 1000:
        return jsonify({'success': False, 'error': '备注不能超过 1000 个字符。'}), 400

    fields = [
        'shipping_completed', 'shipping_date', 'shipping_tracking_no',
        'shipping_record_note', 'shipping_recorded_at',
        'shipping_recorded_by', 'procurement_status',
    ]
    before = _snapshot(pi, fields)
    pi.shipping_completed = True
    pi.shipping_date = parsed_shipping_date
    pi.shipping_tracking_no = tracking_no
    pi.shipping_record_note = note
    pi.shipping_recorded_at = datetime.utcnow()
    pi.shipping_recorded_by = get_current_user().username
    pi.procurement_status = '发货完成'
    _audit(
        'update', 'pi', pi.id,
        f'登记 PI {pi.pi_number} 发货完成',
        before=before,
        after=_snapshot(pi, fields),
    )
    try:
        db.session.commit()
    except StaleDataError:
        db.session.rollback()
        return jsonify({'success': False, 'error': '该 PI 已被其他用户更新，请刷新后重试。'}), 409
    return jsonify(_shipping_record_payload(pi))


@app.route('/api/pi/<int:pi_id>/shipping-complete', methods=['POST'])
@admin_required
def api_pi_shipping_complete(pi_id):
    """Legacy admin compatibility endpoint; the UI uses shipping records."""
    pi = PI.query.options(db.joinedload(PI.items).joinedload(PIItem.product)).filter_by(id=pi_id).first_or_404()
    if pi.deleted_at is not None:
        abort(404)
    if (pi.received_amount or 0) <= 0:
        return jsonify({'success': False, 'error': '该 PI 尚未回款，不能确认发货完成。'}), 400
    data = request.get_json(silent=True) or {}
    completed = data.get('completed', True)
    if not isinstance(completed, bool):
        return jsonify({'success': False, 'error': '发货确认参数无效。'}), 400
    if not completed and pi.shipping_completed and data.get('confirm_downstream_reset') is not True:
        return jsonify({
            'success': False,
            'error': '撤销发货需要单独确认。该操作会清空发货日期、物流单号、备注、登记人和登记时间；回款、采购、装箱及报关记录不会改变。',
            'confirmation_required': True,
            'affected_fields': [
                '发货完成状态', '发货日期', '物流单号', '发货备注', '登记人', '登记时间',
            ],
            'preserved_records': ['回款', '采购', '装箱', '报关'],
        }), 409
    if completed:
        if not pi.procurement_confirmed:
            return jsonify({'success': False, 'error': '采购单尚未完整确认，不能标记发货完成。'}), 400
        gaps = _procurement_gaps(pi)
        if gaps:
            return jsonify({'success': False, 'error': '采购单不完整，不能标记发货完成。'}), 400
    fields = [
        'shipping_completed', 'shipping_date', 'shipping_tracking_no',
        'shipping_record_note', 'shipping_recorded_at', 'shipping_recorded_by',
        'procurement_status',
    ]
    before = _snapshot(pi, fields)
    previous = pi.effective_procurement_status
    pi.shipping_completed = completed
    if completed:
        pi.shipping_date = pi.shipping_date or date.today()
        pi.shipping_tracking_no = str(data.get('tracking_no') or pi.shipping_tracking_no or '')[:200]
        pi.shipping_record_note = str(data.get('note') or pi.shipping_record_note or '')[:1000]
        pi.shipping_recorded_at = pi.shipping_recorded_at or datetime.utcnow()
        pi.shipping_recorded_by = pi.shipping_recorded_by or get_current_user().username
    else:
        pi.shipping_date = None
        pi.shipping_tracking_no = ''
        pi.shipping_record_note = ''
        pi.shipping_recorded_at = None
        pi.shipping_recorded_by = ''
    pi.procurement_status = '发货完成' if completed else ('采购完成' if pi.procurement_confirmed else '待采购')
    _audit(
        'update', 'pi', pi.id,
        f'订单进度：{previous} → {pi.procurement_status}',
        before=before, after=_snapshot(pi, fields),
    )
    db.session.commit()
    return jsonify({'success': True, 'procurement_status': pi.effective_procurement_status,
                    'version': pi.version})


@app.route('/api/procurement/<int:pi_id>')
@admin_required
def api_procurement_get(pi_id):
    """Get all procurement items for a PI with product names and images."""
    procs = Procurement.query.filter_by(pi_id=pi_id).all()
    result = []
    for p in procs:
        d = p.to_dict()
        if p.pi_item and p.pi_item.product:
            d['pi_item_name'] = p.pi_item.product.name
            d['pi_item_cn'] = p.pi_item.product.chinese_name or ''
            d['pi_item_image'] = p.pi_item.product.image or ''
        if p.pi_item:
            d['pi_unit_price'] = p.pi_item.unit_price
            d['pi_quantity'] = p.pi_item.quantity
        result.append(d)
    return jsonify(result)


@app.route('/backup')
@admin_required
def backup_page():
    """Backup management page."""
    backup_dir = app.config['BACKUP_DIR']
    os.makedirs(backup_dir, exist_ok=True)

    # List existing backups
    backups = []
    if os.path.exists(backup_dir):
        for f in sorted(os.listdir(backup_dir), reverse=True):
            if f.endswith('.zip') and f.startswith('backup_'):
                fp = os.path.join(backup_dir, f)
                size_mb = os.path.getsize(fp) / (1024 * 1024)
                mtime = datetime.fromtimestamp(os.path.getmtime(fp))
                backups.append({
                    'filename': f,
                    'size_mb': f'{size_mb:.1f} MB',
                    'date': mtime.strftime('%Y-%m-%d %H:%M'),
                })

    return render_template('backup.html', backups=backups)


@app.route('/backup/create', methods=['POST'])
@admin_required
def backup_create():
    """Create a full backup zip (database + uploads)."""
    backup_dir = app.config['BACKUP_DIR']
    os.makedirs(backup_dir, exist_ok=True)

    timestamp = date.today().strftime('%Y%m%d')
    backup_name = f'backup_{timestamp}.zip'
    backup_path = os.path.join(backup_dir, backup_name)

    # If backup already exists today, add sequence number
    seq = 1
    while os.path.exists(backup_path):
        backup_name = f'backup_{timestamp}_{seq:02d}.zip'
        backup_path = os.path.join(backup_dir, backup_name)
        seq += 1

    try:
        temp_db_path = ''
        with zipfile.ZipFile(backup_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            # Add database
            db_dir = os.environ.get('DATABASE_DIR', os.path.join(APP_ROOT, 'instance'))
            db_path = os.path.join(db_dir, 'pi_manager.db')
            if os.path.exists(db_path):
                fd, temp_db_path = tempfile.mkstemp(suffix='.db')
                os.close(fd)
                with sqlite3.connect(db_path, timeout=30) as source, sqlite3.connect(temp_db_path) as target:
                    source.backup(target)
                zf.write(temp_db_path, 'instance/pi_manager.db')

            # Add uploads directory
            uploads_dir = app.config['UPLOAD_DIR']
            if os.path.exists(uploads_dir):
                for root, dirs, files in os.walk(uploads_dir):
                    for fn in files:
                        fp = os.path.join(root, fn)
                        arcname = os.path.join('uploads', os.path.relpath(fp, uploads_dir))
                        zf.write(fp, arcname)

            if os.path.exists(SETTINGS_FILE):
                zf.write(SETTINGS_FILE, 'settings.json')

            # Add company config info
            info = (
                f"Backup created: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"Project: PI Management System\n"
                f"Company: {COMPANY_CONFIG['name']}\n"
            )
            zf.writestr('backup_info.txt', info)

        size_mb = os.path.getsize(backup_path) / (1024 * 1024)
        flash(f'备份已创建：{backup_name}（{size_mb:.1f} MB）', 'success')
    except Exception as e:
        flash(f'备份失败：{str(e)}', 'danger')
    finally:
        if temp_db_path and os.path.exists(temp_db_path):
            os.remove(temp_db_path)

    return redirect(url_for('backup_page'))


@app.route('/backup/download/<filename>')
@admin_required
def backup_download(filename):
    """Download a backup zip file."""
    backup_dir = app.config['BACKUP_DIR']
    filepath = os.path.join(backup_dir, secure_filename(filename))
    if not os.path.exists(filepath):
        flash('未找到备份文件。', 'danger')
        return redirect(url_for('backup_page'))
    return send_file(filepath, as_attachment=True, download_name=filename)


@app.route('/backup/delete/<filename>', methods=['POST'])
@admin_required
def backup_delete(filename):
    """Delete a backup zip file."""
    backup_dir = app.config['BACKUP_DIR']
    filepath = os.path.join(backup_dir, secure_filename(filename))
    if os.path.exists(filepath):
        os.remove(filepath)
        flash(f'备份 {filename} 已删除。', 'success')
    return redirect(url_for('backup_page'))


# ═══════════════════════════════════════════════════════════════════════
#  Context processors — inject globals into templates
# ═══════════════════════════════════════════════════════════════════════

@app.context_processor
def inject_globals():
    user = get_current_user()
    settings = _load_settings()
    return {
        'company': COMPANY_CONFIG,
        'app_root': APP_ROOT,
        'all_salespersons': Salesperson.query.order_by(Salesperson.name).all(),
        'all_accounts': Account.query.order_by(Account.name).all(),
        'shipping_note_options': _field_options('shipping_note'),
        'expense_category_options': _field_options('expense_category'),
        'price_terms_options': _field_options('price_terms'),
        'delivery_time_options': _field_options('delivery_time'),
        'current_user': user,
        'is_admin': is_admin(),
        'exchange_rate': _get_exchange_rate(),
        'performance_exchange_rate': PERFORMANCE_EXCHANGE_RATE,
        'today_str': date.today().strftime('%Y-%m-%d'),
    }


# ═══════════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    print(f"App root: {APP_ROOT}")
    print(f"Database: {os.path.join(os.environ.get('DATABASE_DIR', os.path.join(APP_ROOT, 'instance')), 'pi_manager.db')}")
    print(f"PDF directory: {app.config['PDF_DIR']}")
    print("Starting development server on http://127.0.0.1:5000 ...")
    app.run(host='127.0.0.1', port=5000, debug=False)
