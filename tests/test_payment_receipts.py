"""Receipt registration and private thumbnails using the isolated smoke fixture."""
import os
import unittest
import uuid
from datetime import date, datetime
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from PIL import Image

import security_smoke as fixture
from models import AuditLog, FinanceReview, Payment, PI, db


class PaymentReceiptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture.SecuritySmokeTests.setUpClass()

    def setUp(self):
        self.helper = fixture.SecuritySmokeTests()
        self.helper.setUp()
        self.helper.login('alice')
        self.client = self.helper.client
        self.token = self.helper.token('/pi/list')
        with fixture.application.app.app_context():
            pi = PI(pi_number='RECEIPT-' + uuid.uuid4().hex[:12],
                    customer_id=self.helper.alice_customer, salesperson='Alice',
                    currency='USD', total_amount=100)
            db.session.add(pi)
            db.session.commit()
            self.pi_id = pi.id
        self.path = f'/pi/{self.pi_id}/toggle-paid'

    def receipt_form(self):
        return {
            'received_on': '2026-11-01',
            'received_amount': '10', 'fee': '0', 'order_no': uuid.uuid4().hex,
            'receiving_account_id': self.helper.approved_account,
            'idempotency_key': uuid.uuid4().hex, 'csrf_token': self.token,
            'attachment': self.helper.image_upload(),
        }

    def test_missing_or_blank_arrival_date_saves_nothing(self):
        for missing_date in (None, '', '   '):
            with self.subTest(received_on=missing_date):
                form = self.receipt_form()
                if missing_date is None:
                    form.pop('received_on')
                else:
                    form['received_on'] = missing_date
                before_files = set(os.listdir(fixture.application.app.config['UPLOAD_DIR']))
                with fixture.application.app.app_context():
                    review_count = FinanceReview.query.count()
                    audit_count = AuditLog.query.count()
                with patch.object(fixture.application, 'receipt_performance_snapshot') as quote:
                    response = self.client.post(self.path, data=form, follow_redirects=True)
                    quote.assert_not_called()
                self.assertEqual(response.status_code, 200)
                self.assertIn('请选择实际到账日期。', response.text)
                self.assertEqual(set(os.listdir(fixture.application.app.config['UPLOAD_DIR'])), before_files)
                with fixture.application.app.app_context():
                    self.assertEqual(Payment.query.filter_by(pi_id=self.pi_id).count(), 0)
                    self.assertEqual(FinanceReview.query.count(), review_count)
                    self.assertEqual(AuditLog.query.count(), audit_count)
                    self.assertEqual(db.session.get(PI, self.pi_id).received_amount or 0, 0)

    def test_explicit_arrival_date_is_saved_and_returned(self):
        response = self.client.post(self.path, data=self.receipt_form())
        self.assertEqual(response.status_code, 302)
        data = self.client.get(f'/api/pi/{self.pi_id}/payments').json
        self.assertEqual(len(data['payments']), 1)
        self.assertEqual(data['payments'][0]['received_on'], '2026-11-01')
        self.assertTrue(data['payments'][0]['registered_at'])
        with fixture.application.app.app_context():
            payment = Payment.query.filter_by(pi_id=self.pi_id).one()
            self.assertEqual(payment.performance_date, date(2026, 11, 1))
            review = FinanceReview.query.filter_by(kind='payment', record_id=payment.id).one()
            self.assertEqual(review.occurred_on, date(2026, 11, 1))

    def make_receipt_image(self):
        filename = 'receipt-' + uuid.uuid4().hex + '.png'
        path = Path(fixture.application.app.config['UPLOAD_DIR']) / filename
        Image.new('RGB', (960, 600), '#e5eefb').save(path, format='PNG')
        with fixture.application.app.app_context():
            payment = Payment(pi_id=self.pi_id, amount=10, order_no=uuid.uuid4().hex,
                              attachment=filename)
            db.session.add(payment)
            db.session.commit()
            self.payment_id = payment.id
        return f'/payments/{self.payment_id}/attachment', path

    def test_owner_and_admin_receive_small_private_thumbnail_and_original_is_unchanged(self):
        url, path = self.make_receipt_image()
        original = path.read_bytes()
        for account in ('alice', 'admin-test'):
            with self.subTest(account=account):
                self.helper.login(account)
                with self.client.get(url + '?thumbnail=1') as response:
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.mimetype, 'image/webp')
                    self.assertIn('private', response.headers['Cache-Control'])
                    self.assertIn('no-store', response.headers['Cache-Control'])
                    with Image.open(BytesIO(response.data)) as thumbnail:
                        self.assertEqual(thumbnail.size, (320, 200))
                with self.client.get(url) as response:
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.mimetype, 'image/png')
                    self.assertEqual(response.data, original)
                self.assertEqual(path.read_bytes(), original)
        self.assertEqual(self.client.get('/uploads/thumb/' + path.name).status_code, 404)

    def test_thumbnail_rejects_unrelated_and_logged_out_users_before_generation(self):
        url, _ = self.make_receipt_image()
        self.helper.login('bob')
        with patch.object(fixture.application, '_ensure_product_thumbnail') as thumbnail:
            self.assertEqual(self.client.get(url + '?thumbnail=1').status_code, 403)
            self.client.get('/logout')
            self.assertEqual(self.client.get(url + '?thumbnail=1').status_code, 302)
            thumbnail.assert_not_called()

    def test_thumbnail_rejects_deleted_payment_or_pi_even_after_caching(self):
        url, _ = self.make_receipt_image()
        with self.client.get(url + '?thumbnail=1') as response:
            self.assertEqual(response.status_code, 200)
        with fixture.application.app.app_context():
            payment = db.session.get(Payment, self.payment_id)
            payment.deleted_at = datetime.utcnow()
            db.session.commit()
        for account in ('alice', 'admin-test'):
            self.helper.login(account)
            self.assertEqual(self.client.get(url + '?thumbnail=1').status_code, 404)
        with fixture.application.app.app_context():
            db.session.get(Payment, self.payment_id).deleted_at = None
            db.session.get(PI, self.pi_id).deleted_at = datetime.utcnow()
            db.session.commit()
        for account in ('alice', 'admin-test'):
            self.helper.login(account)
            self.assertEqual(self.client.get(url + '?thumbnail=1').status_code, 404)


if __name__ == '__main__':
    unittest.main()
