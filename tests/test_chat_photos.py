import uuid
from test_order_chat import ChatTests, application
from models import db, CustomerFile, OrderMessage, OrderMessagePhoto


class ChatPhotoTests(ChatTests):
    def photo_message(self, ids, body='', key=None, order=None):
        return self.post(f'orders/{order or self.paid}/messages',
                         {'body':body,'photo_ids':ids,'request_id':key or str(uuid.uuid4())})

    def test_reference_shares_archive_and_retry_is_idempotent(self):
        self.login(); photo=self.upload().json['photo']['id']; key=str(uuid.uuid4())
        with application.app.app_context(): before=CustomerFile.query.count()
        first=self.photo_message([photo],key=key); retry=self.photo_message([photo],key=key)
        self.assertEqual(first.status_code,201); self.assertEqual(retry.status_code,200)
        self.assertEqual(first.json['message']['id'],retry.json['message']['id'])
        self.assertEqual(first.json['message']['photos'][0]['id'],photo)
        self.assertFalse(first.json['message']['photos'][0]['deleted'])
        with application.app.app_context():
            self.assertEqual(CustomerFile.query.count(),before)
            self.assertEqual(OrderMessagePhoto.query.filter_by(message_id=first.json['message']['id']).count(),1)
        self.assertEqual(self.photo_message([],body='different',key=key).status_code,409)

    def test_photo_validation_and_cross_order_blocked(self):
        self.login(); photo=self.upload().json['photo']['id']
        for ids in ([photo,photo], [True], ['1'], list(range(1,10)), [999999999]):
            self.assertEqual(self.photo_message(ids).status_code,400)
        # Even an accessible second order cannot reference the first order's image.
        self.assertEqual(self.photo_message([photo],order=self.unpaid).status_code,400)
        self.assertEqual(self.photo_message([photo],order=self.other).status_code,403)
        with application.app.app_context():
            record=db.session.get(CustomerFile,photo);record.mime_type='application/pdf';db.session.commit()
        self.assertEqual(self.photo_message([photo]).status_code,400)

    def test_deleted_photo_tombstone_preserves_text_and_retry(self):
        self.login();photo=self.upload().json['photo']['id'];key=str(uuid.uuid4())
        self.assertEqual(self.photo_message([photo],body='请确认',key=key).status_code,201)
        self.assertEqual(self.post(f'photos/{photo}/delete',{}).status_code,403)
        self.login('admin-test-login','AdminPass123!')
        self.assertEqual(self.post(f'photos/{photo}/delete',{}).status_code,200)
        self.login()
        message=self.client.get(f'/api/mobile/orders/{self.paid}/messages').json['messages'][0]
        self.assertEqual(message['body'],'请确认');self.assertTrue(message['photos'][0]['deleted'])
        self.assertEqual(self.client.get(f'/api/mobile/photos/{photo}/file').status_code,404)
        self.assertEqual(self.photo_message([photo]).status_code,400)
        self.assertEqual(self.photo_message([photo],body='请确认',key=key).status_code,200)
        result=self.client.get(f'/api/mobile/orders/{self.paid}/photos/status?ids={photo}')
        self.assertEqual(result.json['active_ids'],[])

    def test_permanent_removal_keeps_message_tombstone(self):
        self.login();photo=self.upload().json['photo']['id'];self.photo_message([photo],body='保留对话')
        with application.app.app_context():
            CustomerFile.query.filter_by(id=photo).delete();db.session.commit()
        message=self.client.get(f'/api/mobile/orders/{self.paid}/messages').json['messages'][0]
        self.assertTrue(message['photos'][0]['deleted']);self.assertEqual(message['body'],'保留对话')

    def test_multiple_references_keep_order_and_reject_key_reuse(self):
        self.login();a=self.upload().json['photo']['id'];self.key=str(uuid.uuid4());b=self.upload().json['photo']['id']
        key=str(uuid.uuid4()); result=self.photo_message([b,a],body='两张照片',key=key)
        self.assertEqual(result.status_code,201)
        self.assertEqual([p['id'] for p in result.json['message']['photos']],[b,a])
        self.assertEqual(self.photo_message([a,b],body='两张照片',key=key).status_code,409)
        self.assertEqual(set(self.client.get(f'/api/mobile/orders/{self.paid}/photos/status?ids={a},{b}').json['active_ids']),{a,b})
        self.assertEqual(self.client.get(f'/api/mobile/orders/{self.other}/photos/status?ids={a}').status_code,403)
