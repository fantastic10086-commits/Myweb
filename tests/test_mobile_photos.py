"""Isolated API integration tests; never use production data."""
import os
import unittest
import uuid
from io import BytesIO
from unittest.mock import patch
from datetime import datetime
import security_smoke as fixture
from models import db, PI, CustomerFile, OrderPhotoUpload, Customer, User
application = fixture.application


class MobilePhotosTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture.SecuritySmokeTests.setUpClass()

    def setUp(self):
        self.client = application.app.test_client()
        with application.app.app_context():
            alice = Customer.query.filter_by(name='Alice Customer').one()
            bob = Customer.query.filter_by(name='Bob Customer').one()
            suffix = uuid.uuid4().hex[:8]
            self.ids = []
            for name, owner, customer, received in [('paid','Alice',alice,10),('unpaid','Alice',alice,0),('other','Bob',bob,20),('mixed','Alice',bob,10)]:
                pi = PI(pi_number=f'MOBILE-{name}-{suffix}', salesperson=owner, customer_id=customer.id, received_amount=received)
                db.session.add(pi); db.session.flush(); setattr(self, name, pi.id); self.ids.append(pi.id)
            db.session.commit()
        self.key = str(uuid.uuid4())

    def login(self, account='alice-login', password='StrongPass123!'):
        csrf = self.client.get('/api/mobile/session').json['csrf_token']
        result = self.client.post('/api/mobile/login', data={'account':account,'password':password}, headers={'X-CSRFToken':csrf})
        if result.status_code == 200:
            self.csrf = result.json['csrf_token']
        return result

    def upload(self, order=None, **kwargs):
        data = {'request_id': self.key, 'photo': fixture.SecuritySmokeTests.image_upload(), 'note': '测试照片'}
        data.update(kwargs)
        return self.client.post(f'/api/mobile/orders/{order or self.paid}/photos', data=data, headers={'X-CSRFToken':self.csrf})

    def test_login_and_access_filter(self):
        self.assertEqual(self.client.get('/api/mobile/orders').status_code, 401)
        self.assertEqual(self.login().status_code, 200)
        rows = self.client.get('/api/mobile/orders', query_string={'q':'MOBILE-'}).json['orders']
        ids = {row['id'] for row in rows}
        self.assertIn(self.paid, ids)
        for id in (self.unpaid, self.other, self.mixed): self.assertNotIn(id, ids)
        self.assertEqual(self.client.get('/api/mobile/orders?q=NONEXISTENT').json['orders'], [])

    def test_photo_round_trip_and_web_folder(self):
        self.login(); result = self.upload(); self.assertEqual(result.status_code, 201)
        id = result.json['photo']['id']
        self.assertEqual(self.client.get(f'/api/mobile/photos/{id}/file').status_code, 200)
        self.assertEqual(self.client.get(f'/customer-files/{id}').status_code, 200)
        self.assertIn(id, [p['id'] for p in self.client.get(f'/api/mobile/orders/{self.paid}/photos').json['photos']])
        with application.app.app_context():
            record = db.session.get(CustomerFile, id)
            self.assertEqual(record.pi_id, self.paid)
            self.assertEqual(record.customer_id, db.session.get(PI, self.paid).customer_id)
            customer_id = record.customer_id
        html = self.client.get(f'/customers/{customer_id}').get_data(as_text=True)
        self.assertIn('测试照片', html)
        self.assertNotIn(f'action="/customer-files/{id}/delete"', html)

    def test_thumbnail_private_and_no_cache(self):
        self.login(); id = self.upload().json['photo']['id']
        with self.client.get(f'/api/mobile/photos/{id}/file?thumbnail=1') as response:
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.mimetype.startswith('image/'))
            self.assertIn('no-store', response.headers['Cache-Control'])
        self.login('bob-login')
        self.assertEqual(self.client.get(f'/api/mobile/photos/{id}/file?thumbnail=1').status_code,403)

    def test_temporary_password_and_maintenance(self):
        self.login()
        with application.app.app_context():
            user = User.query.filter_by(account='alice-login').one()
            user.must_change_password = True; db.session.commit()
        try:
            result = self.client.get('/api/mobile/orders')
            self.assertEqual(result.status_code,403); self.assertTrue(result.is_json)
        finally:
            with application.app.app_context():
                User.query.filter_by(account='alice-login').one().must_change_password = False; db.session.commit()
        with patch.object(application, '_maintenance_state', return_value={'enabled':True, 'message':'Test', 'reason':'Test'}):
            response = self.client.get('/api/mobile/orders')
            self.assertEqual(response.status_code,503); self.assertTrue(response.is_json)

    def test_retry_is_idempotent(self):
        self.login(); first = self.upload(); second = self.upload()
        self.assertEqual(first.status_code,201); self.assertEqual(second.status_code,200)
        self.assertEqual(first.json['photo']['id'],second.json['photo']['id'])
        self.assertEqual(self.upload(note='changed').status_code,409)

    def test_upload_permissions_and_unpaid(self):
        self.login()
        self.assertEqual(self.upload(self.unpaid).status_code,409)
        self.assertEqual(self.upload(self.other).status_code,403)
        self.assertEqual(self.upload(self.mixed).status_code,403)

    def test_delete_only_admin_in_both_interfaces(self):
        self.login(); id=self.upload().json['photo']['id']
        for path in (f'/api/mobile/photos/{id}/delete', f'/customer-files/{id}/delete'):
            self.assertEqual(self.client.post(path,headers={'X-CSRFToken':self.csrf}).status_code,403)
        self.login('admin-test-login','AdminPass123!')
        self.assertEqual(self.client.post(f'/api/mobile/photos/{id}/delete',headers={'X-CSRFToken':self.csrf}).status_code,200)
        self.assertEqual(self.client.get(f'/api/mobile/photos/{id}/file').status_code,404)
        self.assertEqual(self.client.get(f'/customer-files/{id}').status_code,404)

    def test_cross_user_and_deleted_order(self):
        self.login(); id=self.upload().json['photo']['id']
        self.login('bob-login')
        self.assertEqual(self.client.get(f'/api/mobile/photos/{id}/file').status_code,403)
        self.assertEqual(self.client.get(f'/api/mobile/orders/{self.paid}/photos').status_code,403)
        self.login()
        with application.app.app_context():
            db.session.get(PI,self.paid).deleted_at=datetime.utcnow(); db.session.commit()
        self.assertEqual(self.client.get(f'/api/mobile/photos/{id}/file').status_code,404)

    def test_bad_file_csrf_and_note(self):
        self.login()
        self.assertEqual(self.upload(photo=(BytesIO(b'fake'),'fake.jpg')).status_code,400)
        self.assertEqual(self.upload(photo=(BytesIO(b'hello'),'text.txt')).status_code,400)
        self.assertEqual(self.upload(note='x'*301).status_code,400)
        self.assertEqual(self.upload(request_id='bad').status_code,400)
        self.assertEqual(self.client.post(f'/api/mobile/orders/{self.paid}/photos').status_code,400)

    def test_expired_and_disabled_session(self):
        self.login()
        with self.client.session_transaction() as session: session['auth_version'] = -1
        self.assertEqual(self.client.get('/api/mobile/orders').status_code,401)
        self.assertIsNone(self.client.get('/api/mobile/session').json['user'])

    def test_wrong_password_and_logout(self):
        self.assertEqual(self.login(password='wrong').status_code,401)
        self.login()
        self.assertEqual(self.client.post('/api/mobile/logout', headers={'X-CSRFToken':self.csrf}).status_code,200)
        self.assertEqual(self.client.get('/api/mobile/orders').status_code,401)

    def test_failed_commit_cleans_file(self):
        self.login()
        with application.app.app_context():
            folder=application.app.config['UPLOAD_DIR']; before=set(os.listdir(folder))
        with patch.object(application.db.session,'commit',side_effect=RuntimeError('test failure')):
            self.assertEqual(self.upload().status_code,500)
        self.assertEqual(set(os.listdir(folder)),before)

    def test_paid_removed_blocks_upload_but_keeps_history(self):
        self.login(); id=self.upload().json['photo']['id']
        with application.app.app_context():
            db.session.get(PI,self.paid).received_amount=0; db.session.commit()
        self.key=str(uuid.uuid4())
        self.assertEqual(self.upload().status_code,409)
        self.assertEqual(self.client.get(f'/api/mobile/photos/{id}/file').status_code,200)

if __name__ == '__main__': unittest.main()
