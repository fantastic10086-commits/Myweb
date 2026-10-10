"""Independent Web Push worker. No Apple membership or paid push vendor required."""
import os
import time
import json
from pathlib import Path
from datetime import datetime, timedelta
from models import db, PI, User, OrderMessage, OrderReadState, WebPushSubscription, WebPushDelivery
from order_chat import user_can_chat
from web_push import push_config, valid_endpoint


class WebPushTransport:
    def __init__(self):
        import requests
        self.config = push_config()
        if not self.config:
            raise RuntimeError('Configure WEB_PUSH_PRIVATE_KEY_PATH and WEB_PUSH_SUBJECT first.')
        class NoRedirectSession(requests.Session):
            def request(self, method, url, **kwargs):
                if not valid_endpoint(url):
                    raise ValueError('Disallowed push endpoint')
                kwargs['allow_redirects'] = False
                return super().request(method, url, **kwargs)
        self.http = NoRedirectSession()
        self.http.trust_env = False

    def send(self, device, delivery, payload):
        from pywebpush import webpush, WebPushException
        if not valid_endpoint(device.endpoint):
            return 400, 'InvalidEndpoint'
        try:
            response = webpush(subscription_info={'endpoint':device.endpoint,
                'keys':{'p256dh':device.p256dh,'auth':device.auth}},
                data=json.dumps(payload,ensure_ascii=False),
                vapid_private_key=self.config['path'], vapid_claims={'sub':self.config['subject']},
                ttl=300, timeout=15, requests_session=self.http,
                headers={'Urgency':'normal','Topic':'order-'+str(payload['order_id'])})
            return response.status_code, ''
        except WebPushException as exc:
            response = exc.response
            return (response.status_code if response is not None else 503), 'PushServiceError'


def deliver_batch(transport, limit=50, now=None):
    clock_override=now
    now=now or datetime.utcnow()
    candidates=WebPushDelivery.query.filter(WebPushDelivery.status.in_(['pending','processing']),
        WebPushDelivery.next_attempt_at<=now).order_by(WebPushDelivery.id).with_entities(WebPushDelivery.id).limit(limit).all()
    attempted=0
    for (id,) in candidates:
        attempt_now=clock_override or datetime.utcnow()
        claimed=WebPushDelivery.query.filter_by(id=id).filter(
            WebPushDelivery.status.in_(['pending','processing']),WebPushDelivery.next_attempt_at<=attempt_now
        ).update({'status':'processing','next_attempt_at':attempt_now+timedelta(minutes=5),
                  'attempts':WebPushDelivery.attempts+1},synchronize_session=False)
        db.session.commit()
        if not claimed: continue
        row=db.session.get(WebPushDelivery,id)
        if row is None: continue
        device=db.session.get(WebPushSubscription,row.subscription_id)
        user=db.session.get(User,row.user_id)
        message=db.session.get(OrderMessage,row.message_id)
        pi=db.session.get(PI,message.pi_id) if message else None
        read=db.session.get(OrderReadState,(row.user_id,pi.id)) if pi else None
        allowed=(device and device.active and device.user_id==row.user_id and user and
                 device.auth_version==user.auth_version==row.auth_version and device.binding==row.binding and user_can_chat(user,pi))
        if not allowed or message.created_at < attempt_now-timedelta(days=1) or (read and read.last_read_id>=message.id):
            row.status='cancelled'; db.session.commit(); continue
        payload={'title':'订单新消息','body':'订单中有新消息，点击查看。','order_id':pi.id}
        attempted+=1
        try:
            status,reason=transport.send(device,row,payload)
        except Exception:
            # Never log device tokens, keys, response bodies or message text.
            status,reason=503,'TransportError'
        if 200<=status<300:
            row.status='sent';row.last_error=''
        elif status in (404,410):
            device.active=False;row.status='failed';row.last_error=reason or str(status)
        else:
            retry=status==429 or status>=500
            row.status='pending' if retry and row.attempts<8 else 'failed'
            row.next_attempt_at=attempt_now+timedelta(seconds=min(3600,15*(2**row.attempts)))
            row.last_error=(reason or str(status))[:200]
        db.session.commit()
    return attempted


if __name__=='__main__':
    # Fail fast before importing the live application if credentials are absent.
    transport=WebPushTransport()
    # Use the existing database without rerunning website startup migrations/seeding.
    from flask import Flask
    from sqlalchemy import event
    app=Flask('web-push-worker')
    database=Path(os.environ['DATABASE_DIR'])/'pi_manager.db'
    if not database.is_file():
        raise RuntimeError('Existing PI database is required; start the upgraded web app first.')
    app.config['SQLALCHEMY_DATABASE_URI']='sqlite:///'+str(database.resolve())
    app.config['SQLALCHEMY_ENGINE_OPTIONS']={'connect_args':{'timeout':30}}
    db.init_app(app)
    with app.app_context():
        @event.listens_for(db.engine,'connect')
        def configure_connection(connection, record):
            connection.execute('PRAGMA foreign_keys=ON')
            connection.execute('PRAGMA busy_timeout=30000')
    while True:
        with app.app_context():
            deliver_batch(transport)
        time.sleep(5)
