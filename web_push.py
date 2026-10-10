"""Standards Web Push subscriptions; no paid Apple account or third-party SDK service."""
import base64
import os
import re
import uuid
from urllib.parse import urlsplit
from flask import jsonify, request, session, abort
from sqlalchemy.dialects.sqlite import insert
from models import db, User, WebPushSubscription, WebPushDelivery


def valid_endpoint(endpoint):
    if not isinstance(endpoint, str) or len(endpoint) > 2048:
        return False
    try:
        url = urlsplit(endpoint)
        host = url.hostname or ''
        allowed = (host == 'web.push.apple.com' or host.endswith('.push.apple.com') or
                   host == 'fcm.googleapis.com' or host == 'updates.push.services.mozilla.com')
        return (allowed and url.scheme == 'https' and url.port in (None, 443) and
                not url.username and not url.password and not url.fragment and bool(url.path) and
                not any(ord(c) < 33 for c in endpoint))
    except ValueError:
        return False


def decode_key(value, size):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]+={0,2}', value):
        raise ValueError('invalid key')
    data = base64.urlsafe_b64decode(value + '=' * (-len(value) % 4))
    if len(data) != size:
        raise ValueError('invalid key length')
    return data


def push_config():
    path = os.environ.get('WEB_PUSH_PRIVATE_KEY_PATH', '')
    subject = os.environ.get('WEB_PUSH_SUBJECT', '')
    if not path or not subject:
        return None
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from pathlib import Path
    key = serialization.load_pem_private_key(Path(path).read_bytes(), password=None)
    if not isinstance(key, ec.EllipticCurvePrivateKey) or not isinstance(key.curve, ec.SECP256R1):
        raise ValueError('VAPID key must be P-256')
    if not (subject.startswith('mailto:') or subject.startswith('https://')):
        raise ValueError('VAPID contact must be mailto: or https:')
    public = key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    return {'public_key': base64.urlsafe_b64encode(public).decode().rstrip('='), 'subject': subject, 'path': path}


def disable_session_web_push():
    binding = session.pop('web_push_binding', None)
    if binding:
        WebPushSubscription.query.filter_by(binding=binding, user_id=session.get('user_id')).update({'active': False})
        db.session.commit()


def queue_web_push(message, pi, author):
    from order_chat import user_can_chat
    for sub in WebPushSubscription.query.filter_by(active=True).filter(WebPushSubscription.user_id != author.id).all():
        user = db.session.get(User, sub.user_id)
        if user_can_chat(user, pi) and sub.auth_version == user.auth_version:
            db.session.add(WebPushDelivery(message_id=message.id, subscription_id=sub.id,
                user_id=user.id, auth_version=user.auth_version, binding=sub.binding))


def register_web_push(bp, current_user):
    @bp.get('/web-push/config')
    def config():
        try:
            value = push_config()
        except (OSError, ValueError, ImportError):
            return jsonify(enabled=False, message='服务器通知配置待完成。')
        return jsonify(enabled=bool(value), public_key=value['public_key'] if value else None,
                       message='' if value else '服务器尚未启用后台通知，页面内提醒仍可使用。')

    @bp.post('/web-push/subscribe')
    def subscribe():
        try:
            if not push_config():
                abort(503, description='服务器尚未启用后台通知。')
        except (OSError, ValueError, ImportError):
            abort(503, description='服务器通知配置待完成。')
        data = request.get_json(silent=True)
        if not isinstance(data, dict) or not valid_endpoint(data.get('endpoint')):
            abort(400, description='通知订阅地址无效或暂不支持此浏览器。')
        keys = data.get('keys')
        try:
            if not isinstance(keys, dict):
                raise ValueError()
            public = decode_key(keys.get('p256dh'), 65)
            decode_key(keys.get('auth'), 16)
            from cryptography.hazmat.primitives.asymmetric import ec
            ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), public)
        except (ValueError, TypeError):
            abort(400, description='通知加密信息无效。')
        user = current_user()
        old = WebPushSubscription.query.filter_by(endpoint=data['endpoint']).first()
        binding = (old.binding if old and old.active and old.user_id == user.id and
                   old.auth_version == user.auth_version and old.p256dh == keys['p256dh'] and old.auth == keys['auth']
                   else str(uuid.uuid4()))
        values = dict(user_id=user.id, auth_version=user.auth_version, binding=binding,
                      p256dh=keys['p256dh'], auth=keys['auth'], active=True)
        stmt = insert(WebPushSubscription).values(endpoint=data['endpoint'], **values)
        stmt = stmt.on_conflict_do_update(index_elements=['endpoint'], set_=values)
        db.session.execute(stmt)
        db.session.commit()
        session['web_push_binding'] = binding
        return jsonify(ok=True)

    @bp.post('/web-push/unsubscribe')
    def unsubscribe():
        disable_session_web_push()
        return jsonify(ok=True)
