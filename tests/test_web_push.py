import base64
import json
import os
import tempfile
import uuid
from pathlib import Path
from unittest.mock import patch
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization
from test_mobile_photos import MobilePhotosTests, application
from models import db, User, PI, OrderMessage, OrderReadState, WebPushSubscription, WebPushDelivery
from web_push import valid_endpoint, push_config
from web_push_worker import deliver_batch, WebPushTransport


def b64(value):
    return base64.urlsafe_b64encode(value).decode().rstrip('=')


class Transport:
    def __init__(self, status=201): self.status=status;self.calls=[]
    def send(self, sub, row, payload): self.calls.append(payload);return self.status,''


class WebPushTests(MobilePhotosTests):
    def setUp(self):
        super().setUp()
        with application.app.app_context():
            WebPushDelivery.query.delete();WebPushSubscription.query.delete();db.session.commit()
        self.config=patch('web_push.push_config',return_value={'public_key':'test','subject':'mailto:test@example.test','path':'unused'})
        self.config.start();self.addCleanup(self.config.stop)
        public=ec.generate_private_key(ec.SECP256R1()).public_key().public_bytes(serialization.Encoding.X962,serialization.PublicFormat.UncompressedPoint)
        self.subscription={'endpoint':'https://web.push.apple.com/test-'+uuid.uuid4().hex,'keys':{'p256dh':b64(public),'auth':b64(os.urandom(16))}}

    def post(self,path,data):
        return self.client.post('/api/mobile/'+path,json=data,headers={'X-CSRFToken':self.csrf})

    def message(self,key=None):
        return self.post(f'orders/{self.paid}/messages',{'body':'Internal private discussion','request_id':key or str(uuid.uuid4())})

    def queued(self):
        self.login('admin-test-login','AdminPass123!')
        self.assertEqual(self.post('web-push/subscribe',self.subscription).status_code,200)
        self.admin_client,self.admin_csrf=self.client,self.csrf
        self.client=application.app.test_client();self.login()
        result=self.message();self.assertEqual(result.status_code,201)
        return result.json['message']['id']

    def test_validation_auth_csrf_and_no_ssrf(self):
        self.assertEqual(self.client.get('/api/mobile/web-push/config').status_code,401)
        self.login()
        self.assertEqual(self.client.post('/api/mobile/web-push/subscribe',json=self.subscription).status_code,400)
        for url in ['http://web.push.apple.com/x','https://127.0.0.1/x','https://web.push.apple.com.evil.test/x','https://web.push.apple.com:123/x','https://user@web.push.apple.com/x','https://web.push.apple.com/x#fragment']:
            self.assertFalse(valid_endpoint(url))
            self.assertEqual(self.post('web-push/subscribe',{**self.subscription,'endpoint':url}).status_code,400)
        self.assertEqual(self.post('web-push/subscribe',{**self.subscription,'keys':{'p256dh':'bad','auth':'bad'}}).status_code,400)

    def test_transactional_queue_privacy_and_deduplication(self):
        self.queued();key=str(uuid.uuid4());self.message(key);self.message(key)
        with application.app.app_context():
            self.assertEqual(WebPushDelivery.query.count(),2)
            transport=Transport();self.assertEqual(deliver_batch(transport),2)
            self.assertEqual(deliver_batch(transport),0)
            self.assertNotIn('Internal',json.dumps(transport.calls))
            self.assertTrue(all(r.status=='sent' for r in WebPushDelivery.query.all()))

    def test_mobile_logout_cancels_delivery(self):
        self.queued()
        self.admin_client.post('/api/mobile/logout',headers={'X-CSRFToken':self.admin_csrf})
        with application.app.app_context():
            transport=Transport();deliver_batch(transport);self.assertEqual(transport.calls,[])
            self.assertEqual(WebPushDelivery.query.one().status,'cancelled')

    def test_web_logout_cancels_delivery(self):
        self.queued();self.admin_client.get('/logout')
        with application.app.app_context():
            transport=Transport();deliver_batch(transport);self.assertEqual(transport.calls,[])

    def test_rebinding_subscription_cancels_old_recipient(self):
        self.queued();self.assertEqual(self.post('web-push/subscribe',self.subscription).status_code,200)
        with application.app.app_context():
            transport=Transport();deliver_batch(transport);self.assertEqual(transport.calls,[])

    def test_read_or_revoked_user_cancels(self):
        mid=self.queued()
        self.admin_client.post(f'/api/mobile/orders/{self.paid}/read',json={'last_read_id':mid},headers={'X-CSRFToken':self.admin_csrf})
        with application.app.app_context():
            transport=Transport();deliver_batch(transport);self.assertEqual(transport.calls,[])
        self.message()
        with application.app.app_context():
            sub=WebPushSubscription.query.one();user=db.session.get(User,sub.user_id);old=user.auth_version;user.auth_version+=1;db.session.commit()
            try:
                transport=Transport();deliver_batch(transport);self.assertEqual(transport.calls,[])
            finally:user.auth_version=old;db.session.commit()

    def test_retry_and_expired_endpoint(self):
        self.queued()
        with application.app.app_context():
            deliver_batch(Transport(503));row=WebPushDelivery.query.one();self.assertEqual(row.status,'pending');self.assertEqual(row.attempts,1)
            self.assertEqual(deliver_batch(Transport()),0)
            deliver_batch(Transport(410),now=row.next_attempt_at)
            self.assertEqual(row.status,'failed');self.assertFalse(WebPushSubscription.query.one().active)

    def test_unsubscribe_resubscribe_invalidates_old_delivery(self):
        self.queued();self.client,self.csrf=self.admin_client,self.admin_csrf
        self.post('web-push/unsubscribe',{});self.post('web-push/subscribe',self.subscription)
        with application.app.app_context():
            transport=Transport();deliver_batch(transport);self.assertEqual(transport.calls,[])

    def test_worker_encrypts_and_disables_redirects(self):
        self.config.stop()
        with tempfile.TemporaryDirectory() as folder:
            key=ec.generate_private_key(ec.SECP256R1());path=Path(folder)/'key.pem'
            path.write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
            with patch.dict(os.environ,WEB_PUSH_PRIVATE_KEY_PATH=str(path),WEB_PUSH_SUBJECT='mailto:test@example.test'):
                config=push_config();self.assertEqual(len(base64.urlsafe_b64decode(config['public_key']+'=')),65)
                transport=WebPushTransport()
                import requests
                captured=[]
                def send(request, **kwargs):
                    captured.append((request,kwargs));response=requests.Response();response.status_code=201;response._content=b'';return response
                with application.app.app_context():
                    sub=WebPushSubscription(endpoint=self.subscription['endpoint'],**self.subscription['keys'])
                    with patch.object(transport.http,'send',side_effect=send):
                        result=transport.send(sub,None,{'order_id':self.paid,'body':'private'})
                self.assertEqual(result[0],201);request,kwargs=captured[0]
                self.assertFalse(kwargs['allow_redirects']);self.assertIn('Authorization',request.headers)
                self.assertNotIn(b'private',request.body)
