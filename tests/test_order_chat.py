import unittest
import uuid
from datetime import datetime, timedelta
from test_mobile_photos import MobilePhotosTests, application
from models import db, User, OrderMessage, OrderReadState, PushDevice, PushDelivery, PI
from push_worker import deliver_batch


class FakeAPNs:
    def __init__(self, code=200, reason=''):
        self.code=code; self.reason=reason; self.calls=[]
    def send(self, device, delivery, payload):
        self.calls.append(payload)
        return self.code,self.reason


class ChatTests(MobilePhotosTests):
    def setUp(self):
        super().setUp()
        with application.app.app_context():
            PushDelivery.query.delete(); PushDevice.query.delete()
            OrderReadState.query.delete(); OrderMessage.query.delete(); db.session.commit()

    def post(self,path,data):
        return self.client.post('/api/mobile/'+path,json=data,headers={'X-CSRFToken':self.csrf})

    def send(self, order=None, key=None, body='订单已经拍照，请确认。'):
        return self.post(f'orders/{order or self.paid}/messages',{'body':body,'request_id':key or str(uuid.uuid4())})

    def register(self, token='ab'*32):
        return self.post('devices',{'token':token,'environment':'sandbox'})

    def prepare_push(self):
        self.login('admin-test-login','AdminPass123!'); self.assertEqual(self.register().status_code,200)
        self.login(); return self.send().json['message']['id']

    def test_chat_permissions_and_deduplication(self):
        self.login(); key=str(uuid.uuid4())
        a=self.send(key=key); b=self.send(key=key)
        self.assertEqual(a.status_code,201);self.assertEqual(b.status_code,200)
        self.assertEqual(a.json['message']['id'],b.json['message']['id'])
        self.assertEqual(self.send(key=key,body='不同内容').status_code,409)
        for id in (self.other,self.mixed):
            self.assertEqual(self.send(order=id).status_code,403)
            self.assertEqual(self.client.get(f'/api/mobile/orders/{id}/messages').status_code,403)
        self.assertEqual(self.send(body=' ').status_code,400)
        self.assertEqual(self.send(body='a'*4001).status_code,400)
        self.assertEqual(self.post(f'orders/{self.paid}/messages',[1]).status_code,400)

    def test_read_state_is_per_user_order_and_monotonic(self):
        self.login(); first=self.send().json['message']['id']; last=self.send().json['message']['id']
        self.assertEqual(self.client.get('/api/mobile/unread').json['total'],0)
        self.login('admin-test-login','AdminPass123!')
        unread=self.client.get('/api/mobile/unread').json
        self.assertEqual(unread['total'],2)
        self.assertEqual(self.post(f'orders/{self.paid}/read',{'last_read_id':last}).status_code,200)
        self.post(f'orders/{self.paid}/read',{'last_read_id':first})
        self.assertEqual(self.client.get('/api/mobile/unread').json['total'],0)
        self.assertEqual(self.post(f'orders/{self.other}/read',{'last_read_id':last}).status_code,400)
        self.login('bob-login');self.assertEqual(self.client.get('/api/mobile/unread').json['total'],0)

    def test_pagination_does_not_drop_messages(self):
        self.login()
        for i in range(55): self.assertEqual(self.send(body=str(i)).status_code,201)
        result=self.client.get(f'/api/mobile/orders/{self.paid}/messages').json
        self.assertEqual(len(result['messages']),50);self.assertTrue(result['has_more'])
        older=self.client.get(f'/api/mobile/orders/{self.paid}/messages?before='+str(result['messages'][0]['id'])).json
        self.assertEqual(len(older['messages']),5); self.assertFalse(older['has_more'])
        latest=result['messages'][-1]['id']
        self.send(body='last')
        delta=self.client.get(f'/api/mobile/orders/{self.paid}/messages?after={latest}').json
        self.assertEqual([m['body'] for m in delta['messages']],['last'])

    def test_new_tables_allow_user_deletion_and_preserve_chat(self):
        from werkzeug.security import generate_password_hash
        with application.app.app_context():
            user=User(account='temporary-photo-user',username='Temporary',
                password_hash=generate_password_hash('StrongPass123!'),role='salesperson',
                salesperson_name='Alice',must_change_password=False)
            db.session.add(user);db.session.commit();id=user.id
        self.login('temporary-photo-user');self.register();self.upload()
        message_id=self.send().json['message']['id']
        # The pre-existing AuditLog FK blocks hard deletion independently of this feature.
        # Detach it in this fixture only to exercise the NEW tables' deletion behavior.
        from models import AuditLog
        with application.app.app_context():
            AuditLog.query.filter_by(user_id=id).update({'user_id':None});db.session.commit()
        self.login('admin-test-login','AdminPass123!')
        response=self.client.post(f'/users/{id}/delete',headers={'X-CSRFToken':self.csrf})
        self.assertEqual(response.status_code,302)
        with application.app.app_context():
            self.assertIsNone(db.session.get(User,id))
            self.assertEqual(PushDevice.query.filter_by(user_id=id).count(),0)
            message=db.session.get(OrderMessage,message_id)
            self.assertEqual(message.author_name,'Temporary');self.assertIsNone(message.author_id)
        self.assertEqual(self.client.get('/api/mobile/unread').json['total'],1)

    def test_push_outbox_and_content_privacy(self):
        self.prepare_push(); transport=FakeAPNs()
        with application.app.app_context():
            self.assertEqual(PushDelivery.query.count(),1)
            self.assertEqual(deliver_batch(transport),1)
            self.assertEqual(PushDelivery.query.one().status,'sent')
            self.assertEqual(deliver_batch(transport),0)
        self.assertEqual(transport.calls[0]['pi_id'],self.paid)
        self.assertNotIn('订单已经拍照',str(transport.calls))

    def test_push_retries_and_invalid_tokens(self):
        self.prepare_push(); transport=FakeAPNs(503,'ServiceUnavailable')
        with application.app.app_context():
            now=datetime.utcnow(); deliver_batch(transport,now=now)
            row=PushDelivery.query.one();self.assertEqual(row.status,'pending');self.assertEqual(row.attempts,1)
            self.assertEqual(deliver_batch(transport,now=now),0)
            deliver_batch(FakeAPNs(410,'Unregistered'),now=now+timedelta(hours=1))
            self.assertEqual(PushDelivery.query.one().status,'failed')
            self.assertFalse(PushDevice.query.one().active)

    def test_logout_cancels_pending_push(self):
        self.prepare_push()
        self.login('admin-test-login','AdminPass123!');self.register()
        self.assertEqual(self.post('logout',{}).status_code,200)
        with application.app.app_context():
            transport=FakeAPNs(); deliver_batch(transport)
            self.assertEqual(transport.calls,[]);self.assertEqual(PushDelivery.query.one().status,'cancelled')

    def test_device_rebinding_cannot_receive_previous_users_push(self):
        self.prepare_push()
        self.login('bob-login');self.register()
        with application.app.app_context():
            transport=FakeAPNs();deliver_batch(transport)
            self.assertEqual(transport.calls,[])

    def test_read_or_revoked_access_cancels_push(self):
        id=self.prepare_push()
        self.login('admin-test-login','AdminPass123!');self.post(f'orders/{self.paid}/read',{'last_read_id':id})
        with application.app.app_context():
            transport=FakeAPNs();deliver_batch(transport);self.assertEqual(transport.calls,[])
        self.login();self.send()
        with application.app.app_context():
            user=User.query.filter_by(account='admin-test-login').one();user.auth_version+=1;db.session.commit()
            transport=FakeAPNs();deliver_batch(transport);self.assertEqual(transport.calls,[])

if __name__=='__main__':
    unittest.main(defaultTest='ChatTests')
