"""Receipt-month attribution using isolated database and authenticated routes."""
import unittest
from datetime import date
from unittest.mock import patch
import security_smoke as fixture
from models import db, PI, Payment, FinanceReview, User


class ReceiptMonthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture.SecuritySmokeTests.setUpClass()

    def test_split_months_missing_dates_and_deleted_receipts(self):
        app = fixture.application
        with app.app.app_context():
            admin = User.query.filter_by(username='admin-test').one()
            uid, version = admin.id, admin.auth_version
            pi = PI(pi_number='MONTH-TEST', salesperson='Alice',
                    customer_id=fixture.SecuritySmokeTests.alice_customer,
                    issue_date=date(2026, 9, 1), currency='EUR', eur_usd_rate=1.2,
                    total_amount=1000, received_amount=9999)
            db.session.add(pi)
            db.session.flush()
            for amount, day, deleted in [(100, date(2026, 10, 31), False),
                                         (200, date(2026, 11, 1), False),
                                         (300, None, False),
                                         (400, date(2026, 11, 2), True)]:
                payment = Payment(pi_id=pi.id, amount=amount)
                if deleted:
                    payment.deleted_at = app.datetime.utcnow()
                db.session.add(payment)
                db.session.flush()
                if day:
                    db.session.add(FinanceReview(kind='payment', record_id=payment.id, occurred_on=day))
            db.session.commit()
        client = app.app.test_client()
        with client.session_transaction() as state:
            state['user_id'], state['auth_version'] = uid, version
        for month, amount in [('10', 120), ('11', 240)]:
            with patch.object(app, 'render_template', return_value='ok') as render:
                response = client.get('/sales-stats', query_string={
                    'date_from': f'2026-{month}-01', 'date_to': f'2026-{month}-' + ('31' if month == '10' else '30'), 'sp': 'Alice'})
                self.assertEqual(response.status_code, 200)
                context = render.call_args[1]
                expected = amount
                self.assertAlmostEqual(context['grand_total'], expected)
                self.assertEqual(context['missing_date_count'], 1)
        response = client.get('/sales-stats?date_from=2026-10-31&date_to=2026-11-30&sp=Alice')
        self.assertEqual(response.status_code, 200)
        self.assertIn('实际到账明细（2 笔）', response.text)
        self.assertIn('$360.00', response.text)


if __name__ == '__main__':
    unittest.main()
