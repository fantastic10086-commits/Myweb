"""Payroll arithmetic, preview/confirmation, whole-order exclusions and access."""
import re
import unittest
from datetime import date, datetime
from decimal import Decimal as D
from types import SimpleNamespace

import security_smoke as fixture
from models import (db, AuditLog, FinanceReview, Payment, PI, PayrollSlip, Salesperson, User)
from payroll import calculate, commission, month_dates, paid_dates, token


def order(usd):
    return dict(usd=D(usd), reason='')


class PayrollMath(unittest.TestCase):
    def test_all_commission_boundaries(self):
        for usd, percent in [('0', '1'), ('7500', '1'), ('7500.01', '1.2'), ('10000', '1.2'),
                             ('10000.01', '1.4'), ('15000', '1.4'), ('15000.01', '1.6'),
                             ('20000', '1.6'), ('20000.01', '1.8'), ('25000', '1.8'),
                             ('25000.01', '2'), ('30000', '2'), ('35000', '2')]:
            self.assertEqual(commission([order(usd)])['percent'], percent, usd)
        self.assertEqual(commission([order('13853.61')])['commission'], '1357.65')
        self.assertEqual(month_dates('2026-12')[2], date(2027, 1, 15))

    def test_hourly_example_and_fixed_salary(self):
        profile = SimpleNamespace(base=D('4000'), fund=D('0'), staff_no='01', mode='hourly', social=None)
        inputs = dict(required='21', actual='21', hours=None, paid=None, unpaid=None, merit='83.43',
                      bonus='0', social=None, fund=None)
        sales = commission([order('13853.61')])
        result = calculate(profile, inputs, {'2026-01-01': '元旦'}, D('512.30'), sales)
        self.assertEqual([result[k] for k in ('earned', 'meal', 'award', 'gross', 'net')],
                         ['3705.26', '210.00', '200', '5556.34', '5044.04'])
        profile.mode = 'monthly'
        self.assertEqual(calculate(profile, inputs, {}, None, sales)['earned'], '4000.00')
        inputs.update(required='22', bonus='30', fund='100', social='25')
        result = calculate(profile, inputs, {}, None, sales)
        self.assertEqual((result['earned'], result['award'], result['net']), ('3816.09', '0', '5372.17'))
        inputs.update(actual='0', required='0')
        self.assertEqual(calculate(profile, inputs, {}, None, sales)['award'], '0')


class PayrollRoutes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture.SecuritySmokeTests.setUpClass()
        cls.app = fixture.application.app
        with cls.app.app_context():
            emp = Salesperson(name='Payroll test')
            db.session.add(emp)
            db.session.flush()
            cls.eid = emp.id
            for serial, amount in [('A', 7500), ('B', 500)]:
                pi = PI(pi_number='PAYROLL-' + serial, salesperson=emp.name, currency='USD',
                        customer_id=fixture.SecuritySmokeTests.alice_customer)
                db.session.add(pi)
                db.session.flush()
                if serial == 'B':
                    cls.pi_id = pi.id
                for day in (date(2026, 9, 30), date(2026, 10, 3)):
                    pay = Payment(pi_id=pi.id, amount=amount, performance_usd_rate=1,
                                  created_at=datetime(2026, 9, 30, 18))
                    db.session.add(pay)
                    db.session.flush()
                    if day.month == 9:
                        db.session.add(FinanceReview(kind='payment', record_id=pay.id, occurred_on=day))
            db.session.commit()

    def setUp(self):
        self.client = self.app.test_client()
        self.login('admin-test')
        self.settings = '/admin/payroll/settings?month=2026-09'
        self.sheet = f'/admin/payroll/2026-09/{self.eid}'
        html = self.client.get(self.settings).text
        self.csrf = re.search(r'<meta name="csrf-token" content="([^"]+)"', html)[1]

    def login(self, name):
        with self.app.app_context():
            u = User.query.filter_by(username=name).one()
            uid, version = u.id, u.auth_version
        with self.client.session_transaction() as session:
            session['user_id'], session['auth_version'] = uid, version

    def post(self, path, **data):
        return self.client.post(path, data=dict(csrf_token=self.csrf, **data))

    def revision(self, action, path=None):
        html = self.client.get(path or self.sheet).text
        return re.search(f'name="action" value="{action}"><input type="hidden" name="revision" value="([^"]+)"', html)[1]

    def test_admin_access_and_calendar(self):
        with self.app.app_context():
            holidays = paid_dates(date(2026, 1, 1), date(2026, 12, 31))
            self.assertEqual(len(holidays), 13)
            self.assertIn('2026-06-19', holidays)
        self.assertEqual(self.post(self.settings, action='add_day', day='2026-09-29', name='公司假').status_code, 302)
        self.assertIn('公司假', self.client.get(self.settings).text)
        self.assertEqual(self.post(self.settings, action='remove_day', day='2026-09-29', revision=token('公司假')).status_code, 302)
        self.assertNotIn('公司假', self.client.get(self.settings).text)
        self.assertEqual(self.post(self.settings, action='remove_day', day='2026-09-25').status_code, 422)
        self.assertEqual(self.client.post(self.settings, data={'action': 'social'}).status_code, 400)
        self.login('alice')
        for url in ('/admin/payroll', self.settings, self.sheet):
            self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.post(self.sheet + f'/orders/{self.pi_id}', action='exclude').status_code, 403)
        self.assertNotIn('工资核算', self.client.get('/').text)

    def test_draft_exclude_confirm_restore(self):
        self.assertEqual(self.post(self.settings, action='social', social='512.30', revision=token(None)).status_code, 302)
        self.assertEqual(self.post(self.settings, action='employee', employee=self.eid, mode='monthly',
                                   base='4000', social='', fund='0', staff_no='01', revision=token(None)).status_code, 302)
        self.assertIn('8000.00 USD', self.client.get(self.sheet).text)
        data = dict(action='save', required='22', actual='21', merit='83.43', bonus='20',
                    social='', fund='', hours='', paid='', unpaid='')
        first = self.revision('save')
        self.assertEqual(self.post(self.sheet, revision=first, **dict(data, actual='-1')).status_code, 422)
        self.assertEqual(self.post(self.sheet, revision=first, **data).status_code, 302)
        self.assertEqual(self.post(self.sheet, revision=first, **data).status_code, 409)
        old_confirm = self.revision('confirm')
        path = self.sheet + f'/orders/{self.pi_id}'
        self.assertEqual(self.post(path, action='exclude', revision=token(['','','']), reason='  ').status_code, 302)
        self.assertEqual(self.post(path, action='exclude', revision=token(['','','']), reason='单独结算').status_code, 302)
        self.assertEqual(self.post(self.sheet, action='confirm', revision=old_confirm).status_code, 409)
        for month in ['09', '10']:
            html = self.client.get(self.sheet.replace('2026-09', '2026-' + month)).text
            self.assertIn('7500.00 USD', html)
            self.assertIn('¥525.00', html)
        self.assertIn('$8000.00', self.client.get('/sales-stats?date_from=2026-09-01&date_to=2026-09-30&sp=Payroll+test').text)
        self.assertEqual(self.post(self.sheet, action='confirm', revision=self.revision('confirm')).status_code, 302)
        with self.app.app_context():
            saved = db.session.get(PayrollSlip, ('2026-09', self.eid)).confirmed
            self.assertEqual((saved['commission'], saved['paid'], saved['net']), ('525.00','1','4142.22'))
        self.assertEqual(self.post(self.sheet, revision=old_confirm, **data).status_code, 409)
        oct_sheet = self.sheet.replace('2026-09', '2026-10')
        html = self.client.get(oct_sheet).text
        restore = re.search(r'name="revision" value="([^"]+)">\s*<button[^>]+value="restore"', html)[1]
        self.assertEqual(self.post(oct_sheet + f'/orders/{self.pi_id}', action='restore', revision=restore).status_code, 302)
        self.assertIn('¥672.00', self.client.get(oct_sheet).text)
        html = self.client.get(self.sheet).text
        self.assertIn('¥525.00', html)
        self.assertIn('单独结算', html)
        self.assertEqual(self.post(self.settings, action='social', social='700.00',
                                   revision=token(D('512.30'))).status_code, 302)
        self.assertEqual(self.post(oct_sheet + f'/orders/{self.pi_id}', action='exclude',
                                   revision=token(['','','']), reason='跨月处理').status_code, 302)
        settings_html = self.client.get(self.settings).text
        restore_settings = re.search(r'name="pi_id" value="\d+">\s*<input type="hidden" name="revision" value="([^"]+)"', settings_html)[1]
        self.assertEqual(self.post(self.settings, action='restore_order', pi_id=self.pi_id, revision=restore_settings).status_code, 302)
        self.assertIn('¥672.00', self.client.get(oct_sheet).text)
        self.assertIn('4142.22', self.client.get('/admin/payroll?month=2026-09').text)
        with self.app.app_context():
            actions = {row.action for row in AuditLog.query.filter_by(entity_type='payroll_commission', entity_id=self.pi_id).all()}
            self.assertEqual(actions, {'exclude', 'restore'})
