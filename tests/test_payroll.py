"""Payroll arithmetic, preview/confirmation, whole-order exclusions and access."""
import re
import unittest
from datetime import date, datetime
from decimal import Decimal as D
from types import SimpleNamespace

import security_smoke as fixture
from models import (db, AuditLog, FinanceReview, Payment, PI, PayrollSlip, Salesperson, User)
from sqlalchemy import create_engine
from payroll import calculate, commission, migrate_payroll_accounts, month_dates, paid_dates, token


def order(usd):
    return dict(usd=D(usd), reason='')


class PayrollMigration(unittest.TestCase):
    def test_atomic_migration_uses_bindings_and_preserves_locked_data(self):
        engine = create_engine('sqlite://')
        with engine.begin() as conn:
            for sql in (
                'CREATE TABLE users(id INTEGER PRIMARY KEY, username TEXT, salesperson_name TEXT)',
                'CREATE TABLE salespersons(id INTEGER PRIMARY KEY, name TEXT)',
                'CREATE TABLE payroll_profiles(employee_id INTEGER PRIMARY KEY, staff_no, mode, base, social, fund)',
                'CREATE TABLE payroll_slips(employee_id, month, inputs, confirmed, confirmed_by, confirmed_at, version)',
                "INSERT INTO users VALUES (7,'Office',''), (9,'Account','Sales')",
                "INSERT INTO salespersons VALUES (7,'Sales'), (9,'Office'), (10,'Missing')",
                "INSERT INTO payroll_profiles VALUES (7,'01','hourly',4150,NULL,0), (9,'02','monthly',8300,512,200)",
                """INSERT INTO payroll_slips VALUES (7,'2026-10','{}','{"net":"4100.00"}','admin','2026-11-01',3),
                     (10,'2026-10','{}',NULL,NULL,NULL,1)""",
            ):
                conn.exec_driver_sql(sql)
        with self.assertRaisesRegex(RuntimeError, 'Missing'):
            migrate_payroll_accounts(engine)
        with engine.begin() as conn:
            self.assertFalse(conn.exec_driver_sql(
                "SELECT 1 FROM sqlite_master WHERE name='user_payroll_profiles'").first())
            conn.exec_driver_sql("INSERT INTO users VALUES(25,'Staff','Missing')")
        migrate_payroll_accounts(engine)
        with engine.begin() as conn:
            self.assertEqual(conn.exec_driver_sql(
                "SELECT user_id, staff_no FROM user_payroll_profiles ORDER BY user_id").fetchall(), [(7,'02'),(9,'01')])
            self.assertEqual(conn.exec_driver_sql(
                'SELECT user_id,confirmed,confirmed_by,version FROM user_payroll_slips ORDER BY user_id').fetchall(),
                [(9,'{"net":"4100.00"}','admin',3),(25,None,None,1)])
            conn.exec_driver_sql('UPDATE user_payroll_profiles SET base=6000 WHERE user_id=7')
        migrate_payroll_accounts(engine)
        with engine.begin() as conn:
            self.assertEqual(conn.exec_driver_sql('SELECT base FROM user_payroll_profiles WHERE user_id=7').scalar(), 6000)


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
            account = User(account='payroll-login', username='Payroll account', salesperson_name=emp.name,
                           password_hash='synthetic', role='salesperson')
            db.session.add_all([emp, account])
            db.session.flush()
            cls.eid = account.id
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
        self.sheet = f'/admin/payroll/2026-09/users/{self.eid}'
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
        self.assertEqual(self.post(self.settings, action='user_profile', user_id=self.eid, mode='monthly',
                                   base='4000', social='', fund='0', staff_no='01', revision=token([self.eid, None])).status_code, 302)
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

    def test_account_roster_inactive_and_non_sales_pay(self):
        with self.app.app_context():
            u = User(account='office-qa', username='Office QA', password_hash='synthetic', role='admin')
            sp = Salesperson(name='Directory entry only')
            db.session.add_all([u, sp])
            db.session.commit()
            uid, spid = u.id, sp.id
        index = '/admin/payroll?month=2026-11'
        page = f'/admin/payroll/2026-11/users/{uid}'
        self.assertIn('Office QA', self.client.get(index).text)
        self.assertNotIn('Directory entry only', self.client.get(index).text)
        self.assertIn('该账号未关联业务员', self.client.get(page).text)
        self.assertEqual(self.client.get(f'/admin/payroll/2026-11/{spid}').location, index)
        self.assertEqual(self.post(self.settings, action='user_profile', user_id=uid, mode='monthly',
                                   base='4200', social='100', fund='0', staff_no='', revision=token([uid, None])).status_code, 302)
        self.assertEqual(self.post(page, action='save', revision=self.revision('save', page), required='20',
                                   actual='20', merit='88', bonus='0').status_code, 302)
        self.assertEqual(self.post(page, action='confirm', revision=self.revision('confirm', page)).status_code, 302)
        self.assertEqual(self.post(f'/users/{uid}/toggle-active').status_code, 302)
        self.assertEqual(self.post(f'/users/{uid}/delete').status_code, 302)
        with self.app.app_context():
            self.assertFalse(db.session.get(User, uid).active)
            frozen = db.session.get(PayrollSlip, ('2026-11', uid)).confirmed
            self.assertEqual((frozen['employee'], frozen['commission'], frozen['net']), ('Office QA', '0.00', '4588.00'))
        self.assertIn('Office QA', self.client.get(index).text)
        other_month = index.replace('2026-11', '2026-12')
        self.assertNotIn('Office QA', self.client.get(other_month).text)
        self.assertIn('Office QA', self.client.get(other_month + '&inactive=1').text)

    def test_conflicting_bindings_and_changed_owner(self):
        with self.app.app_context():
            owner = db.session.get(User, self.eid)
            other = User(account='binding-qa', username='Binding QA', salesperson_name=owner.salesperson_name,
                         password_hash='synthetic')
            db.session.add(other)
            db.session.commit()
            uid = other.id
        page = f'/admin/payroll/2026-10/users/{uid}'
        try:
            self.assertIn('多个用户关联了业务员', self.client.get(page).text)
            self.assertNotIn('PAYROLL-A', self.client.get(page).text)
            self.assertEqual(self.post(page + f'/orders/{self.pi_id}', action='exclude',
                                       revision=token(['','','']), reason='test').status_code, 404)
            with self.app.app_context():
                owner = db.session.get(User, self.eid)
                owner.salesperson_name = ''
                frozen = dict(commission([dict(id=self.pi_id, usd=D(500), reason='')]), employee=owner.username)
                db.session.add(PayrollSlip(month='2026-10', user_id=self.eid, inputs={}, confirmed=frozen))
                db.session.commit()
            html = self.client.get(page).text
            self.assertIn('PAYROLL-A', html)
            self.assertNotIn('PAYROLL-B', html)
            self.assertIn('¥525.00', html)
        finally:
            with self.app.app_context():
                frozen = db.session.get(PayrollSlip, ('2026-10', self.eid))
                if frozen:
                    db.session.delete(frozen)
                db.session.get(User, self.eid).salesperson_name = 'Payroll test'
                db.session.delete(db.session.get(User, uid))
                db.session.commit()
