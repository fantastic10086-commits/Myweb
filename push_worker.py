"""Run separately from Flask: python push_worker.py (APNs credentials required).
Delivery is at least once. APNs acceptance is not proof a banner was displayed.
"""
import os
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from models import db, PI, User, OrderMessage, OrderReadState, PushDevice, PushDelivery
from order_chat import user_can_chat


class APNsTransport:
    def __init__(self):
        import httpx
        self.team=os.environ['APNS_TEAM_ID']
        self.key_id=os.environ['APNS_KEY_ID']
        self.topic=os.environ['APNS_TOPIC']
        self.key=Path(os.environ['APNS_KEY_PATH']).read_text()
        self.client=httpx.Client(http2=True, timeout=15)
        self.jwt=None; self.issued=0

    def send(self, device, delivery, payload):
        import jwt
        now=int(time.time())
        if not self.jwt or now-self.issued>2400:
            self.jwt=jwt.encode({'iss':self.team,'iat':now},self.key,algorithm='ES256',headers={'kid':self.key_id})
            self.issued=now
        host='api.sandbox.push.apple.com' if device.environment=='sandbox' else 'api.push.apple.com'
        response=self.client.post(f'https://{host}/3/device/{device.token}',headers={
            'authorization':'bearer '+self.jwt, 'apns-topic':self.topic,
            'apns-push-type':'alert','apns-priority':'10',
            'apns-expiration':str(now+86400),
            'apns-id':str(uuid.uuid5(uuid.NAMESPACE_URL,f'{self.topic}/delivery/{delivery.id}')),
            'apns-collapse-id':f'message-{delivery.message_id}',
        },json=payload)
        try: reason=response.json().get('reason','')
        except ValueError: reason=''
        return response.status_code,reason


def deliver_batch(transport, limit=50, now=None):
    clock_override=now
    now=now or datetime.utcnow()
    candidates=PushDelivery.query.filter(PushDelivery.status.in_(['pending','processing']),
        PushDelivery.next_attempt_at<=now).order_by(PushDelivery.id).with_entities(PushDelivery.id).limit(limit).all()
    attempted=0
    for (id,) in candidates:
        attempt_now=clock_override or datetime.utcnow()
        claimed=PushDelivery.query.filter_by(id=id).filter(
            PushDelivery.status.in_(['pending','processing']),PushDelivery.next_attempt_at<=attempt_now
        ).update({'status':'processing','next_attempt_at':attempt_now+timedelta(minutes=5),
                  'attempts':PushDelivery.attempts+1},synchronize_session=False)
        db.session.commit()
        if not claimed: continue
        row=db.session.get(PushDelivery,id)
        if row is None: continue
        device=db.session.get(PushDevice,row.device_id)
        user=db.session.get(User,row.user_id)
        message=db.session.get(OrderMessage,row.message_id)
        pi=db.session.get(PI,message.pi_id) if message else None
        read=db.session.get(OrderReadState,(row.user_id,pi.id)) if pi else None
        allowed=(device and device.active and device.user_id==row.user_id and user and
                 device.auth_version==user.auth_version==row.auth_version and user_can_chat(user,pi))
        if not allowed or message.created_at < attempt_now-timedelta(days=1) or (read and read.last_read_id>=message.id):
            row.status='cancelled'; db.session.commit(); continue
        payload={'aps':{'alert':{'title':'订单新消息','body':'订单中有新消息，点击查看。'},
                        'sound':'default','thread-id':f'order-{pi.id}'},'pi_id':pi.id}
        attempted+=1
        try:
            status,reason=transport.send(device,row,payload)
        except Exception:
            # Never log device tokens, keys, response bodies or message text.
            status,reason=503,'TransportError'
        if status==200:
            row.status='sent';row.last_error=''
        elif status==410 or reason in {'BadDeviceToken','DeviceTokenNotForTopic','Unregistered'}:
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
    transport=APNsTransport()
    # Use the existing database without rerunning website startup migrations/seeding.
    from flask import Flask
    from sqlalchemy import event
    app=Flask('order-push-worker')
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
