"""Procurement attachments remain private and separate from customer folders."""
import json
import os
import unittest
import uuid
from datetime import date, datetime
from io import BytesIO
from unittest.mock import patch

from werkzeug.datastructures import FileStorage
import security_smoke as fixture
from models import AuditLog, CustomerFile, PI, ProcurementAttachment, db
from order_archive import sync_order_files


class ProcurementAttachmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture.SecuritySmokeTests.setUpClass()

    def setUp(self):
        self.helper = fixture.SecuritySmokeTests()
        self.helper.setUp()
        self.helper.login('admin-test')
        self.client = self.helper.client
        self.token = self.helper.token('/pi/list')
        with fixture.application.app.app_context():
            pi = PI(pi_number='ATTACH-' + uuid.uuid4().hex[:12],
                    customer_id=self.helper.alice_customer, salesperson='Alice',
                    currency='USD', exchange_rate=6.5, total_amount=100,
                    procurement_status='发货完成', shipping_completed=True,
                    shipping_date=date(2026, 11, 1), shipping_tracking_no='UNCHANGED')
            db.session.add(pi)
            db.session.commit()
            self.pi_id = pi.id
        self.path = '/api/pi/{}/procurement-attachments'.format(self.pi_id)

    def upload(self, files):
        return self.client.post(self.path, data={'csrf_token': self.token, 'files': files})

    def records(self):
        with fixture.application.app.app_context():
            return ProcurementAttachment.query.filter_by(pi_id=self.pi_id).count()

    def disk_files(self):
        return set(os.listdir(fixture.application.app.config['UPLOAD_DIR']))

    def test_multi_upload_is_private_and_preserves_shipping(self):
        before_disk = self.disk_files()
        response = self.upload([
            self.helper.image_upload('采购截图.png'),
            (BytesIO(b'%PDF-1.4\n procurement document'), '采购资料.pdf'),
            (BytesIO('供应商,金额\n测试,10'.encode('utf-8')), '采购.csv'),
        ])
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(len(data['files']), 3)
        self.assertNotIn('folder_url', data)
        self.assertIn('no-store', response.headers['Cache-Control'])
        files_by_name = {item['name']: item for item in data['files']}
        image = files_by_name['采购截图.png']
        self.assertTrue(image['is_image'])
        self.assertTrue(image['thumbnail_url'])
        self.assertEqual(files_by_name['采购资料.pdf']['thumbnail_url'], '')
        self.assertFalse(files_by_name['采购.csv']['is_image'])
        self.assertEqual(len(self.disk_files() - before_disk), 3)
        self.assertEqual(self.client.get(image['url']).status_code, 200)
        self.assertEqual(self.client.get(image['thumbnail_url']).status_code, 200)
        downloaded = self.client.get(image['download_url'])
        self.assertEqual(downloaded.status_code, 200)
        self.assertIn('attachment;', downloaded.headers['Content-Disposition'])
        with fixture.application.app.app_context():
            records = ProcurementAttachment.query.filter_by(pi_id=self.pi_id).all()
            self.assertEqual(len(records), 3)
            for record in records:
                self.assertEqual(record.created_by, 'admin-test')
                self.assertTrue(os.path.isfile(os.path.join(
                    fixture.application.app.config['UPLOAD_DIR'], record.stored_name)))
                audit = AuditLog.query.filter_by(entity_type='procurement_attachment', entity_id=record.id).one()
                self.assertEqual(json.loads(audit.after_json)['pi_id'], self.pi_id)
            pi = db.session.get(PI, self.pi_id)
            self.assertTrue(pi.shipping_completed)
            self.assertEqual(pi.shipping_date, date(2026, 11, 1))
            self.assertEqual(pi.shipping_tracking_no, 'UNCHANGED')
            self.assertEqual(pi.procurement_status, '发货完成')
            self.assertEqual(sync_order_files(db.session, pi), 0)
            db.session.commit()
            self.assertEqual(CustomerFile.query.filter_by(pi_id=self.pi_id).count(), 0)
            private_name = records[0].stored_name
        self.assertEqual(self.records(), 3)
        self.assertEqual(self.client.get('/uploads/' + private_name).status_code, 404)
        customer_page = self.client.get('/customers/' + str(self.helper.alice_customer)).get_data(as_text=True)
        self.assertNotIn('采购截图.png', customer_page)
        customs = self.client.get('/api/pi/{}/customs-attachments'.format(self.pi_id))
        self.assertEqual(customs.json['files'], [])
        self.assertEqual(len(self.client.get(self.path).json['files']), 3)

    def test_permissions_csrf_and_salespeople_denied(self):
        self.assertEqual(self.client.post(self.path, data={
            'files': self.helper.image_upload(),
        }).status_code, 400)
        data = self.upload([self.helper.image_upload()]).get_json()
        item = data['files'][0]
        self.assertEqual(self.client.post(item['delete_url']).status_code, 400)
        self.helper.login('alice')
        self.token = self.helper.token('/pi/list')
        self.assertEqual(self.client.get(self.path).status_code, 403)
        for key in ('url', 'thumbnail_url', 'download_url'):
            self.assertEqual(self.client.get(item[key]).status_code, 403)
        self.assertEqual(self.client.post(item['delete_url'], data={'csrf_token': self.token}).status_code, 403)
        self.assertEqual(self.upload([self.helper.image_upload()]).status_code, 403)
        self.assertEqual(self.client.post(item['delete_url'], data={'csrf_token': self.token}).status_code, 403)
        self.helper.login('bob')
        self.token = self.helper.token('/pi/list')
        self.assertEqual(self.client.get(self.path).status_code, 403)
        self.assertEqual(self.upload([self.helper.image_upload()]).status_code, 403)
        for key in ('url', 'thumbnail_url', 'download_url'):
            self.assertEqual(self.client.get(item[key]).status_code, 403)
        self.assertEqual(self.records(), 1)

    def test_invalid_batch_and_limits_save_nothing(self):
        cases = [
            [],
            [(BytesIO(b'hello'), 'file{}.txt'.format(i)) for i in range(9)],
            [self.helper.image_upload(), (BytesIO(b'not an image'), 'invalid.png')],
            [(BytesIO(b'<script>alert(1)</script>'), 'bad.html')],
            [(BytesIO(), 'empty.txt')],
            [(BytesIO(b'x' * (21 * 1024 * 1024)), 'oversize.txt')],
            [(BytesIO(b'x' * (16 * 1024 * 1024)), 'one.txt'),
             (BytesIO(b'x' * (15 * 1024 * 1024)), 'two.txt')],
        ]
        before_disk = self.disk_files()
        for uploads in cases:
            with self.subTest(files=len(uploads)):
                response = self.upload(uploads)
                self.assertEqual(response.status_code, 400)
                self.assertTrue(response.json['error'])
                self.assertEqual(self.records(), 0)
                self.assertEqual(self.disk_files(), before_disk)

    def test_deleted_records_hidden_and_deleted_pi_rejected(self):
        item = self.upload([self.helper.image_upload()]).json['files'][0]
        deleted = self.client.post(item['delete_url'],
                                   data={'csrf_token': self.token})
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(deleted.json['files'], [])
        self.assertEqual(self.client.get(self.path).json['files'], [])
        self.assertEqual(self.client.get(item['url']).status_code, 404)
        self.assertEqual(self.client.get(item['thumbnail_url']).status_code, 404)
        second = self.upload([self.helper.image_upload()]).json['files'][0]
        with fixture.application.app.app_context():
            pi = db.session.get(PI, self.pi_id)
            pi.deleted_at = datetime.utcnow()
            db.session.commit()
        self.assertEqual(self.client.get(self.path).status_code, 404)
        self.assertEqual(self.upload([self.helper.image_upload()]).status_code, 404)
        self.assertEqual(self.client.get(second['url']).status_code, 404)
        self.assertEqual(self.client.get(second['thumbnail_url']).status_code, 404)
        self.assertEqual(self.client.post(second['delete_url'], data={'csrf_token': self.token}).status_code, 404)

    def test_partial_file_write_rolls_back_whole_batch(self):
        before_disk = self.disk_files()
        save = FileStorage.save
        calls = []

        def fail_second(storage, destination, *args, **kwargs):
            calls.append(destination)
            if len(calls) == 2:
                with open(destination, 'wb') as target:
                    target.write(b'partial')
                raise OSError('simulated disk write failure')
            return save(storage, destination, *args, **kwargs)

        with patch.object(FileStorage, 'save', fail_second), \
                patch.dict(fixture.application.app.config, {'PROPAGATE_EXCEPTIONS': True}):
            with self.assertRaisesRegex(OSError, 'simulated disk write failure'):
                self.upload([self.helper.image_upload('first.png'),
                             self.helper.image_upload('second.png')])
        self.assertEqual(self.records(), 0)
        self.assertEqual(self.disk_files(), before_disk)
        with fixture.application.app.app_context():
            audits = AuditLog.query.filter_by(summary='上传采购附件').all()
            self.assertFalse(any(json.loads(a.after_json).get('pi_id') == self.pi_id for a in audits))

    def test_commit_failure_removes_files_and_audit(self):
        before_disk = self.disk_files()
        with patch.object(db.session, 'commit', side_effect=RuntimeError('simulated commit failure')), \
                patch.dict(fixture.application.app.config, {'PROPAGATE_EXCEPTIONS': True}):
            with self.assertRaisesRegex(RuntimeError, 'simulated commit failure'):
                self.upload([self.helper.image_upload()])
        self.assertEqual(self.records(), 0)
        self.assertEqual(self.disk_files(), before_disk)
        with fixture.application.app.app_context():
            audits = AuditLog.query.filter_by(summary='上传采购附件').all()
            self.assertFalse(any(json.loads(a.after_json).get('pi_id') == self.pi_id for a in audits))


if __name__ == '__main__':
    unittest.main(verbosity=2)
