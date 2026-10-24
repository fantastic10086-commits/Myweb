"""Finance integration checks against isolated application data, with real auth/CSRF."""
import html
import json
import re
import unittest
import uuid
from datetime import date
from io import BytesIO
import security_smoke as fixture
from openpyxl import load_workbook
from models import db, PI, Payment, Expense, FinanceReview, FinanceAccount, User
application = fixture.application


class FinanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture.SecuritySmokeTests.setUpClass()

    def setUp(self):
        self.client = application.app.test_client()
        self.suffix = uuid.uuid4().hex[:8]
        with application.app.app_context():
            admin = User.query.filter_by(username='admin-test').one()
            self.admin_id, self.auth_version = admin.id, admin.auth_version
            pi = PI(pi_number='FINANCE-'+self.suffix, salesperson='Alice', customer_id=fixture.SecuritySmokeTests.alice_customer,
                    total_amount=100, currency='USD')
            db.session.add(pi); db.session.flush()
            exp = Expense(pi_id=pi.id, category='Demo shipping', amount=30, currency='RMB')
            payment = Payment(pi_id=pi.id, amount=90, fee=10, order_no='=DEMO-'+self.suffix)
            db.session.add_all([exp, payment]); db.session.commit()
            self.pi_id, self.expense_id = pi.id, exp.id
        with self.client.session_transaction() as state:
            state['user_id'], state['auth_version'] = self.admin_id, self.auth_version

    def page(self, tab='expense', **args):
        return self.client.get('/admin/finance', query_string=dict(tab=tab, month='', q='FINANCE-'+self.suffix, **args))

    def form(self, tab='expense'):
        page = self.page(tab)
        self.assertEqual(page.status_code, 200)
        csrf = re.search(r'<meta name="csrf-token" content="([^"]+)"', page.text).group(1)
        data = json.loads(html.unescape(re.search("data-record='([^']+)'", page.text).group(1)))
        data['csrf_token'] = csrf
        return data

    def test_real_auth_and_csrf(self):
        self.assertEqual(self.client.post('/admin/finance/accounts', data={'name':'No CSRF'}).status_code, 400)
        with application.app.app_context():
            user = User.query.filter_by(username='alice').one()
            uid, version = user.id, user.auth_version
        with self.client.session_transaction() as state:
            state['user_id'], state['auth_version'] = uid, version
        for path in ('/admin/finance','/admin/finance/export','/admin/finance/expense/1/attachment'):
            self.assertEqual(self.client.get(path).status_code, 403)

    def test_payment_validation_stale_edits_and_source_change(self):
        data = self.form()
        data.update(payment_status='paid', paid_on=date.today().isoformat(), checked='1')
        self.client.post('/admin/finance/review',data=data)
        with application.app.app_context():
            self.assertIsNone(FinanceReview.query.filter_by(kind='expense',record_id=self.expense_id).first())
        result = self.client.post('/admin/finance/accounts', data={'name':'Demo RMB '+self.suffix,'csrf_token':data['csrf_token']})
        self.assertEqual(result.status_code,302)
        with application.app.app_context():
            data['account_id']=FinanceAccount.query.filter_by(name='Demo RMB '+self.suffix).one().id
        self.client.post('/admin/finance/review',data=data)
        with application.app.app_context():
            r=FinanceReview.query.filter_by(kind='expense',record_id=self.expense_id).one()
            self.assertTrue(r.checked)
            self.assertEqual(r.payment_status,'paid')
            self.assertEqual(db.session.get(Expense,self.expense_id).amount,30)
            self.assertEqual(db.session.get(PI,self.pi_id).total_amount,100)
            version=r.version
        self.client.post('/admin/finance/review',data=data)
        with application.app.app_context():
            self.assertEqual(FinanceReview.query.filter_by(kind='expense',record_id=self.expense_id).one().version,version)
            exp=db.session.get(Expense,self.expense_id);exp.amount=31;db.session.commit()
        page=self.page(checked='no')
        self.assertIn('FINANCE-'+self.suffix,page.text)
        self.assertIn('待核对',page.text)
        self.assertEqual(self.page(basis='paid',status='paid').status_code,200)

    def test_deleted_expense_cannot_leave_payment_metadata(self):
        data = self.form()
        data.update(payment_status='unpaid', checked='1')
        self.client.post('/admin/finance/review',data=data)
        with application.app.app_context():
            self.assertIsNotNone(FinanceReview.query.filter_by(kind='expense',record_id=self.expense_id).first())
            db.session.delete(db.session.get(Expense,self.expense_id))
            db.session.commit()
            self.assertIsNone(FinanceReview.query.filter_by(kind='expense',record_id=self.expense_id).first())

    def test_receipt_export_literal_and_date_fallback(self):
        page=self.page('payment')
        self.assertIn('登记日期',page.text)
        self.assertIn('finance-edit',page.text)
        response=self.client.get('/admin/finance/export',query_string={'tab':'payment','month':'','q':'FINANCE-'+self.suffix})
        self.assertEqual(response.status_code,200)
        sheet=load_workbook(BytesIO(response.data)).active
        self.assertEqual(sheet['I2'].value,'=DEMO-'+self.suffix)
        self.assertEqual(sheet['I2'].data_type,'s')
        self.assertIn('no-store',response.headers['Cache-Control'])
        self.assertEqual(self.client.get('/admin/finance?month=bad').status_code,400)


if __name__=='__main__':
    unittest.main()
