"""Date-based market rates, frozen receipt accounting and atomic history migration."""
import json
import html
import re
import unittest
import uuid
from datetime import date, datetime
from io import BytesIO
from unittest.mock import patch
import security_smoke as fixture
from models import db, PI, Payment, FinanceReview, Account
import fx_rates
from ops.reprice_receipt_performance import reprice

application = fixture.application


def reference(day):
    rate = 7.0 if day.month == 10 else 8.0
    return dict(rmb_usd_rate=1/rate, eur_usd_rate=1.25 if day.month == 10 else 1.5,
                fx_reference_date=day.isoformat(), fx_source='Frankfurter')


class ReferenceTests(unittest.TestCase):
    def test_weekend_common_date_reciprocal_and_future_exclusion(self):
        fx_rates._daily_cache.clear()
        rows = [dict(date='2026-10-30', base='USD', quote='CNY', rate=7),
                dict(date='2026-10-30', base='USD', quote='EUR', rate=0.8),
                dict(date='2026-10-31', base='USD', quote='CNY', rate=7.1),
                dict(date='2026-11-02', base='USD', quote='EUR', rate=0.7)]
        with patch('fx_rates.urlopen', return_value=BytesIO(json.dumps(rows).encode())) as url:
            rates = fx_rates.usd_reference_rates(date(2026, 11, 1))
            self.assertEqual(rates['fx_reference_date'], '2026-10-30')
            self.assertAlmostEqual(rates['usd_rmb_rate'] * rates['rmb_usd_rate'], 1)
            self.assertAlmostEqual(rates['eur_usd_rate'], 1.25)
            self.assertAlmostEqual(rates['eur_rmb_rate'], 8.75)
            fx_rates.usd_reference_rates(date(2026, 11, 1))
            self.assertEqual(url.call_count, 1)
        fx_rates._daily_cache.clear()
        with patch('fx_rates.urlopen', return_value=BytesIO(b'[]')):
            with self.assertRaises(ValueError):
                fx_rates.usd_reference_rates(date(2026, 11, 1))
        with patch('fx_rates.urlopen') as url:
            with self.assertRaises(ValueError):
                fx_rates.usd_reference_rates(date(2099, 1, 1))
            url.assert_not_called()


class ReceiptRateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture.SecuritySmokeTests.setUpClass()

    def setUp(self):
        self.helper = fixture.SecuritySmokeTests()
        self.helper.setUp()
        self.helper.login('alice')
        self.client = self.helper.client
        self.name = uuid.uuid4().hex
        with application.app.app_context():
            pi = PI(pi_number=self.name, salesperson='Alice',
                    customer_id=self.helper.alice_customer, total_amount=2000,
                    currency='RMB', exchange_rate=6.5)
            account = Account(name=self.name, currency='RMB', brand='klista')
            db.session.add_all([pi, account])
            db.session.commit()
            self.pi_id, self.account_id = pi.id, account.id

    def post_receipt(self, day='2026-10-30', amount='700'):
        return self.client.post(f'/pi/{self.pi_id}/toggle-paid', data={
            'csrf_token': self.helper.token('/pi/create'), 'idempotency_key': uuid.uuid4().hex,
            'received_amount': amount, 'fee': '0', 'received_on': day,
            'order_no': uuid.uuid4().hex, 'receiving_account_id': self.account_id,
            'attachment': self.helper.image_upload()})

    def test_receipts_use_arrival_day_and_remain_frozen(self):
        with patch('fx_rates.usd_reference_rates', side_effect=reference) as rates:
            self.assertEqual(self.post_receipt().status_code, 302)
            self.assertEqual(self.post_receipt('2026-11-02', '800').status_code, 302)
            self.assertEqual([call[0][0] for call in rates.call_args_list], [date(2026,10,30), date(2026,11,2)])
        with application.app.app_context():
            pi = db.session.get(PI, self.pi_id)
            rows = Payment.query.filter_by(pi_id=pi.id).order_by(Payment.id).all()
            self.assertAlmostEqual(rows[0].performance_usd_rate, 1/7)
            self.assertAlmostEqual(rows[1].performance_usd_rate, 1/8)
            self.assertEqual(rows[0].performance_reference_date, '2026-10-30')
            self.assertEqual(pi.exchange_rate, 6.5)
            original_profit_rate = pi.exchange_rate
            application._migrate_db()
            db.session.expire_all()
            self.assertEqual(db.session.get(PI, self.pi_id).exchange_rate, original_profit_rate)
            self.assertAlmostEqual(db.session.get(Payment, rows[1].id).performance_usd_rate, 1/8)
        with patch('fx_rates.usd_reference_rates', side_effect=AssertionError('must use saved rates')):
            response = self.client.get('/sales-stats?date_from=2026-10-01&date_to=2026-11-30&sp=Alice')
            self.assertEqual(response.status_code, 200)
            self.assertIn('0.125000 USD', response.text)
            with patch.object(application, 'render_template', return_value='ok') as render:
                self.client.get('/sales-stats?date_from=2026-10-01&date_to=2026-11-30&sp=Alice')
                own = [r for r in render.call_args[1]['receipts'] if r.pi.id == self.pi_id]
                self.assertAlmostEqual(sum(r.amount_usd for r in own), 200)

    def test_failure_does_not_register_receipt(self):
        with patch('fx_rates.usd_reference_rates', side_effect=TimeoutError):
            response = self.post_receipt()
            self.assertEqual(response.status_code, 302)
        with application.app.app_context():
            self.assertEqual(Payment.query.filter_by(pi_id=self.pi_id).count(), 0)
            self.assertEqual(db.session.get(PI, self.pi_id).received_amount, 0)

    def test_edit_arrival_date_refreshes_rate_and_failure_is_atomic(self):
        with patch('fx_rates.usd_reference_rates', side_effect=reference):
            self.post_receipt()
        self.helper.login('admin-test')
        def form():
            response = self.client.get('/admin/finance', query_string={'tab':'payment','month':'','q':self.name})
            self.assertEqual(response.status_code,200)
            data = json.loads(html.unescape(re.search("data-record='([^']+)'",response.text).group(1)))
            data['csrf_token'] = re.search(r'<meta name="csrf-token" content="([^"]+)"',response.text).group(1)
            return data
        data = form()
        data['occurred_on'] = '2026-11-02'
        with patch('fx_rates.usd_reference_rates', side_effect=reference):
            self.assertEqual(self.client.post('/admin/finance/review',data=data).status_code,302)
        with application.app.app_context():
            payment = Payment.query.filter_by(pi_id=self.pi_id).one()
            self.assertAlmostEqual(payment.performance_usd_rate,1/8)
            self.assertEqual(payment.performance_date,date(2026,11,2))
        data = form()
        data['occurred_on'] = '2026-10-29'
        with patch('fx_rates.usd_reference_rates', side_effect=TimeoutError):
            self.client.post('/admin/finance/review',data=data)
        with application.app.app_context():
            payment = Payment.query.filter_by(pi_id=self.pi_id).one()
            review = FinanceReview.query.filter_by(kind='payment',record_id=payment.id).one()
            self.assertEqual(review.occurred_on,date(2026,11,2))
            self.assertAlmostEqual(payment.performance_usd_rate,1/8)

    def test_history_preview_apply_dates_and_idempotency(self):
        with application.app.app_context():
            p1 = Payment(pi_id=self.pi_id, amount=700, created_at=datetime(2026,9,1))
            p2 = Payment(pi_id=self.pi_id, amount=800, created_at=datetime(2026,10,31,18))
            db.session.add_all([p1,p2]);db.session.flush()
            db.session.add(FinanceReview(kind='payment', record_id=p1.id, occurred_on=date(2026,10,30)))
            db.session.commit()
            p1id,p2id=p1.id,p2.id
        with patch('fx_rates.usd_reference_rates', side_effect=reference):
            preview = reprice(application)
            self.assertGreaterEqual(preview['count'], 2)
            with application.app.app_context():
                self.assertIsNone(db.session.get(Payment,p1id).performance_usd_rate)
            reprice(application, apply=True)
        with application.app.app_context():
            p1,p2 = db.session.get(Payment,p1id),db.session.get(Payment,p2id)
            self.assertEqual(p1.performance_date,date(2026,10,30))
            self.assertEqual(p2.performance_date,date(2026,11,1))
            self.assertAlmostEqual(p1.performance_usd_rate,1/7)
            self.assertAlmostEqual(p2.performance_usd_rate,1/8)
            self.assertEqual((p1.amount,p2.amount),(700,800))
        with patch('fx_rates.usd_reference_rates', side_effect=AssertionError('already frozen')):
            self.assertEqual(reprice(application, apply=True)['count'],0)


if __name__ == '__main__':
    unittest.main()
