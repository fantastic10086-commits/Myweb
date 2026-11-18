"""Isolated, authenticated checks for saved expenses before shipment."""
import json
import unittest
import uuid
from datetime import date
import security_smoke as fixture
from models import db, PI, PIItem, Product, Supplier, Procurement, Payment, Expense, User, AuditLog

application = fixture.application


def seed_order(suffix):
    pi = PI(pi_number='DISPATCH-' + suffix, customer_id=fixture.SecuritySmokeTests.alice_customer,
            salesperson='Alice', currency='RMB', total_amount=100, received_amount=100,
            procurement_confirmed=True)
    supplier = Supplier(name='Dispatch supplier ' + suffix)
    db.session.add_all([pi, supplier]); db.session.flush()
    item = PIItem(pi_id=pi.id, product_id=Product.query.first().id, quantity=1, unit_price=100, amount=100)
    db.session.add(item); db.session.flush()
    db.session.add_all([
        Procurement(pi_id=pi.id, pi_item_id=item.id, supplier_id=supplier.id, quantity=1, unit_price=20, total=20),
        Payment(pi_id=pi.id, amount=100, order_no='DISPATCH-PAY-' + suffix),
    ])
    db.session.commit()
    return pi.id


class DispatchStepTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture.SecuritySmokeTests.setUpClass()

    def setUp(self):
        self.client = application.app.test_client()
        with application.app.app_context():
            self.pi_id = seed_order(uuid.uuid4().hex[:10])
        self.as_user('alice')
        self.csrf = fixture.SecuritySmokeTests.token(self, '/pi/list')

    def as_user(self, name):
        with application.app.app_context():
            user = User.query.filter_by(username=name).one()
            uid, version = user.id, user.auth_version
        with self.client.session_transaction() as session:
            session['user_id'], session['auth_version'] = uid, version

    def state(self):
        return self.client.get('/api/pi/{}/shipping-record'.format(self.pi_id)).get_json()

    def payload(self, **overrides):
        data = dict(token=str(uuid.uuid4()), version=self.state()['version'], action='save', step='forwarder',
                    freight_forwarder='客户货代', customs_required=False, customs_note='', expenses=[],
                    no_expenses=False, edit_shipping=False, shipping_date='2026-11-18')
        data.update(overrides)
        return data

    def post(self, data):
        return self.client.post('/api/pi/{}/dispatch'.format(self.pi_id), data={'payload': json.dumps(data)},
                                headers={'X-CSRFToken': self.csrf})

    def expense(self, amount=0):
        return {'category': '报关费', 'amount': amount, 'note': '无需费用'}

    def test_save_next_zero_cost_then_confirm_and_edit(self):
        first = self.post(self.payload(action='next')).get_json()
        self.assertTrue(first['success']); self.assertTrue(first['forwarder_ready'])
        self.assertFalse(first['can_ship']); self.assertEqual(first['expense_count'], 0)
        for action in ('save', 'next'):
            result = self.post(self.payload(action=action, step='expenses'))
            self.assertEqual(result.status_code, 400)
        saved = self.payload(action='next', step='expenses', expenses=[self.expense()])
        result = self.post(saved)
        self.assertEqual(result.status_code, 200, result.get_json())
        self.assertEqual(result.get_json()['expense_count'], 1)
        self.assertTrue(result.get_json()['can_ship'])
        # Lost-response retries must not duplicate a zero cost record.
        self.assertEqual(self.post(saved).status_code, 200)
        history = self.client.get('/api/expenses?pi_id=' + str(self.pi_id)).get_json()
        self.assertEqual(len(history), 1); self.assertEqual(history[0]['amount'], 0)
        self.assertEqual(self.post(self.payload(action='next', step='expenses')).status_code, 200)
        complete = self.post(self.payload(action='complete', step='shipping', tracking_no='TRACK-ONE'))
        self.assertEqual(complete.status_code, 200, complete.get_json())
        self.assertTrue(complete.get_json()['shipping_completed'])
        edited = self.post(self.payload(step='shipping', edit_shipping=True, tracking_no='TRACK-TWO'))
        self.assertEqual(edited.status_code, 200); self.assertTrue(edited.get_json()['shipping_completed'])
        self.assertEqual(edited.get_json()['tracking_no'], 'TRACK-TWO')
        with application.app.app_context():
            pi = db.session.get(PI, self.pi_id)
            self.assertEqual(pi.grand_total, 100); self.assertEqual(pi.received_amount, 100)
            self.assertEqual(Expense.query.filter_by(pi_id=self.pi_id).count(), 1)
            self.assertTrue(AuditLog.query.filter_by(entity_type='expense', entity_id=history[0]['id']).count())

    def test_cannot_bypass_with_checkbox_pending_expense_or_legacy_routes(self):
        for overrides in ({'no_expenses': True}, {'expenses': [self.expense()]}):
            result = self.post(self.payload(action='complete', step='shipping', **overrides))
            self.assertEqual(result.status_code, 400)
        self.post(self.payload(no_expenses=True))
        self.assertFalse(self.state()['can_ship'])
        self.as_user('admin-test')
        for route in ('shipping-record', 'shipping-complete'):
            response = self.client.post('/api/pi/{}/{}'.format(self.pi_id, route),
                                        json={'shipping_date': '2026-11-18', 'completed': True},
                                        headers={'X-CSRFToken': self.csrf})
            self.assertEqual(response.status_code, 400, response.get_json())
        with application.app.app_context():
            self.assertFalse(db.session.get(PI, self.pi_id).shipping_completed)
            self.assertEqual(Expense.query.filter_by(pi_id=self.pi_id).count(), 0)

    def test_amount_category_forwarder_validation_and_atomic_batch(self):
        for amount in ('', None, True, -1, 'nan', 'inf', 'not a number'):
            result = self.post(self.payload(step='expenses', expenses=[self.expense(amount)]))
            self.assertEqual(result.status_code, 400, str(amount))
        for change in ({'freight_forwarder': ''}, {'customs_required': None}):
            self.assertEqual(self.post(self.payload(action='next', **change)).status_code, 400)
        bad = self.expense(12); bad['category'] = ''
        self.assertEqual(self.post(self.payload(step='expenses', expenses=[self.expense(), bad])).status_code, 400)
        with application.app.app_context():
            self.assertEqual(Expense.query.filter_by(pi_id=self.pi_id).count(), 0)
        good = self.post(self.payload(step='expenses', expenses=[self.expense(), self.expense(23.45)]))
        self.assertEqual(good.status_code, 200, good.get_json())
        with application.app.app_context():
            self.assertAlmostEqual(sum(e.amount for e in Expense.query.filter_by(pi_id=self.pi_id)), 23.45)

    def test_authorization_csrf_and_stale_version(self):
        data = self.payload(step='expenses', expenses=[self.expense()])
        response = self.client.post('/api/pi/{}/dispatch'.format(self.pi_id), data={'payload': json.dumps(data)})
        self.assertEqual(response.status_code, 400)
        self.as_user('bob')
        self.assertEqual(self.post(data).status_code, 403)
        self.as_user('alice')
        other = self.payload(); self.assertEqual(self.post(other).status_code, 200)
        self.assertEqual(self.post(data).status_code, 409)
        with application.app.app_context():
            self.assertEqual(Expense.query.filter_by(pi_id=self.pi_id).count(), 0)

    def test_paid_and_procured_rules_remain_after_zero_record(self):
        self.assertEqual(self.post(self.payload(step='expenses', expenses=[self.expense()])).status_code, 200)
        with application.app.app_context():
            payment = Payment.query.filter_by(pi_id=self.pi_id).one(); payment.amount = 40
            db.session.commit()
        self.assertFalse(self.state()['can_ship'])
        self.assertEqual(self.post(self.payload(action='complete', step='shipping')).status_code, 400)
        with application.app.app_context():
            Payment.query.filter_by(pi_id=self.pi_id).one().amount = 100
            db.session.get(PI, self.pi_id).procurement_confirmed = False; db.session.commit()
        self.assertFalse(self.state()['can_ship'])
        self.assertEqual(self.post(self.payload(action='complete', step='shipping')).status_code, 400)

    def test_existing_shipping_preserved_and_removed_last_cost_blocks_completion(self):
        with application.app.app_context():
            pi = db.session.get(PI, self.pi_id); pi.shipping_completed = True
            pi.shipping_date = date(2026, 11, 1); pi.shipping_tracking_no = 'HISTORICAL'
            db.session.commit()
        result = self.post(self.payload(step='shipping', edit_shipping=True, shipping_date='2026-11-02', tracking_no='CORRECTED'))
        self.assertEqual(result.status_code, 200, result.get_json())
        self.assertTrue(result.get_json()['shipping_completed']); self.assertEqual(result.get_json()['expense_count'], 0)
        with application.app.app_context():
            pi = db.session.get(PI, self.pi_id); pi.shipping_completed = False; db.session.commit()
        self.post(self.payload(step='expenses', expenses=[self.expense()]))
        history = self.client.get('/api/expenses?pi_id=' + str(self.pi_id)).get_json()
        self.as_user('admin-test')
        deleted = self.client.delete('/api/expenses/' + str(history[0]['id']), headers={'X-CSRFToken': self.csrf})
        self.assertEqual(deleted.status_code, 200)
        self.assertFalse(self.state()['can_ship'])
        self.assertEqual(self.post(self.payload(action='complete', step='shipping')).status_code, 400)


if __name__ == '__main__':
    unittest.main()
