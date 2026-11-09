"""Configurable currencies: permissions, reference validation, HKD business flow."""
import json
import re
import subprocess
import unittest
import uuid
from datetime import date
from io import BytesIO
from unittest.mock import patch
from openpyxl import load_workbook
import security_smoke as fixture
from models import db, Currency, Account, PI, Payment, Product, PIDraft, AuditLog
from currency_utils import to_usd, to_rmb, currency_symbol
from document_export import render_excel_template
import fx_rates
application = fixture.application


def rate(code='HKD', on=None):
    return dict(currency=code,currency_usd_rate=.13,currency_rmb_rate=.91,
                fx_reference_date=(on or date(2026,11,9)).isoformat(),fx_source='Frankfurter')


class CurrencyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture.SecuritySmokeTests.setUpClass()

    def setUp(self):
        self.helper=fixture.SecuritySmokeTests();self.helper.setUp();self.helper.login('alice')
        self.client=self.helper.client
        with application.app.app_context():
            db.session.get(Currency,'HKD').enabled=True
            db.session.commit()

    def check_scripts(self,response):
        self.assertEqual(response.status_code,200)
        for script in re.findall(r'<script(?:\s[^>]*)?>([\s\S]*?)</script>',response.text):
            if not script.strip() or script.lstrip().startswith(('[','{')):continue
            result=subprocess.run(['node','--check'],input=script,universal_newlines=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            self.assertEqual(result.returncode,0,result.stderr)

    def test_add_validate_edit_and_admin_toggle(self):
        page=self.client.get('/currencies');self.check_scripts(page)
        self.assertIn('HKD',page.text)
        with application.app.app_context():
            from currencies import currency_allowed
            self.assertFalse(currency_allowed(''))
            self.assertFalse(currency_allowed('XXX'))
        data=dict(code='GBP',name='英镑',symbol='£',current_password='StrongPass123!',csrf_token=self.helper.token('/currencies'))
        self.assertEqual(self.client.post('/currencies/add',data={**data,'csrf_token':''}).status_code,400)
        with patch('fx_rates.currency_reference_rates',side_effect=ValueError('not supported')):
            self.client.post('/currencies/add',data={**data,'code':'XYZ'})
        with application.app.app_context():self.assertIsNone(db.session.get(Currency,'XYZ'))
        with patch('fx_rates.currency_reference_rates',return_value=rate('GBP')) as quote:
            self.client.post('/currencies/add',data=data)
            quote.assert_called_once_with('GBP')
        self.client.post('/currencies/GBP/edit',data={**data,'name':'英镑账户币种','symbol':'GBP£'})
        self.assertEqual(self.client.post('/currencies/GBP/toggle',data=data).status_code,403)
        with application.app.app_context():
            row=db.session.get(Currency,'GBP');self.assertEqual(row.name,'英镑账户币种');self.assertEqual(row.symbol,'GBP£')
            self.assertIsNotNone(AuditLog.query.filter_by(entity_type='currency',action='create').first())
        self.helper.login('admin-test')
        self.client.post('/currencies/GBP/toggle',data={'csrf_token':self.helper.token('/currencies')})
        with application.app.app_context():self.assertFalse(db.session.get(Currency,'GBP').enabled)
        with patch('fx_rates.currency_reference_rates',side_effect=TimeoutError):
            self.client.post('/currencies/GBP/toggle',data={'csrf_token':self.helper.token('/currencies')})
        with application.app.app_context():self.assertFalse(db.session.get(Currency,'GBP').enabled)

    def test_hkd_invoice_receipt_export_copy_draft_reports(self):
        # Add a real same-currency bank account through the newly opened sales permission.
        self.client.post('/accounts/add',data=dict(name='HKD demo',currency='HKD',brand='klista',
            current_password='StrongPass123!',csrf_token=self.helper.token('/accounts/add')))
        with application.app.app_context():
            account_id=Account.query.filter_by(name='HKD demo').one().id
            product_id=Product.query.first().id
        name=uuid.uuid4().hex
        data=dict(csrf_token=self.helper.token('/pi/create'),pi_submission_token=uuid.uuid4().hex,
            customer_id=self.helper.alice_customer,salesperson='Alice',notes=name,account_id=account_id,
            currency='HKD',exchange_rate='6.5',currency_usd_rate='.125',currency_rmb_rate='.875',
            fx_reference_date='2026-11-02',fx_source='手动填写',price_terms='FOB',product_order='1',selected_1='on',
            row_product_1=product_id,qty_1='1',unit_price_1='100',shipping_cost='0')
        with patch.object(application,'_generate_default_pi_documents',return_value=('demo.pdf','demo.xlsx')):
            result=self.client.post('/pi/create',data=data)
        self.assertEqual(result.status_code,302,result.text)
        with application.app.app_context():
            pi=PI.query.filter_by(notes=name).one();pi_id=pi.id
            self.assertEqual(pi.currency,'HKD');self.assertEqual(to_usd(pi,100),12.5);self.assertEqual(to_rmb(pi,100),87.5)
            self.assertEqual(currency_symbol('HKD'),'HK$')
            copy=application._pi_export_copy(pi);self.assertEqual(copy.currency_usd_rate,.125)
            path=fixture.TEST_ROOT.name+'/hkd.xlsx'
            render_excel_template(application.SYSTEM_DEFAULT_TEMPLATE_SOURCE,copy,path)
            values=[str(c.value) for row in load_workbook(path).active for c in row if c.value is not None]
            self.assertTrue(any('HKD' in x for x in values))
            from pdf_generator import currency_symbol as pdf_sym,currency_label
            self.assertEqual(pdf_sym('HKD'),'HK$');self.assertEqual(currency_label('HKD'),'HKD')
        payment=dict(csrf_token=self.helper.token('/pi/create'),idempotency_key=uuid.uuid4().hex,
            received_amount='100',fee='0',received_on='2026-11-02',order_no=name,
            receiving_account_id=self.helper.approved_account,attachment=self.helper.image_upload())
        self.client.post(f'/pi/{pi_id}/toggle-paid',data=payment)
        with application.app.app_context():self.assertEqual(Payment.query.filter_by(pi_id=pi_id).count(),0)
        payment['receiving_account_id']=account_id;payment['attachment']=self.helper.image_upload()
        with patch('fx_rates.currency_reference_rates',side_effect=rate) as quote:
            self.client.post(f'/pi/{pi_id}/toggle-paid',data=payment)
            quote.assert_called_once_with('HKD',date(2026,11,2))
        with application.app.app_context():
            pi=db.session.get(PI,pi_id);self.assertTrue(pi.paid)
            self.assertEqual(Payment.query.filter_by(pi_id=pi_id).one().performance_usd_rate,.13)
            self.assertEqual(pi.currency_usd_rate,.125)
            application._migrate_db();db.session.expire_all()
            self.assertEqual(db.session.get(PI,pi_id).currency_rmb_rate,.875)
        data.update(draft_rows='[]',csrf_token=self.helper.token('/pi/create'))
        draft=self.client.post('/pi/drafts/save',data=data);self.assertEqual(draft.status_code,200)
        with application.app.app_context():self.assertEqual(json.loads(db.session.get(PIDraft,draft.json['id']).payload)['fields']['currency_usd_rate'],'.125')
        with patch.object(application,'_generate_default_pi_documents',return_value=('copy.pdf','copy.xlsx')):
            response=self.client.post(f'/pi/{pi_id}/copy',data={'csrf_token':self.helper.token('/pi/create')})
        new_id=int(response.location.split('/pi/')[1].split('/')[0])
        with application.app.app_context():self.assertEqual(db.session.get(PI,new_id).currency_rmb_rate,.875)
        for path in ('/pi/create',f'/pi/{pi_id}/edit','/pi/list','/exchange-rates'):
            self.check_scripts(self.client.get(path))
        self.helper.login('admin-test')
        for path in ('/profit-report',f'/procurement/{pi_id}'):
            self.check_scripts(self.client.get(path))
        self.helper.login('alice')
        with application.app.app_context():db.session.get(Currency,'HKD').enabled=False;db.session.commit()
        self.client.post('/accounts/add',data=dict(name='Should not add',currency='HKD',brand='klista',
            current_password='StrongPass123!',csrf_token=self.helper.token('/accounts/add')))
        with application.app.app_context():self.assertIsNone(Account.query.filter_by(name='Should not add').first())
        self.assertIn('HKD',self.client.get(f'/pi/{pi_id}/edit').text)
        response=self.client.post(f'/pi/{pi_id}/copy',data={'csrf_token':self.helper.token('/pi/create')})
        self.assertIn('/pi/list',response.location)

    def test_generic_historical_reference(self):
        fx_rates._daily_cache.clear()
        rows=[dict(date='2026-11-06',quote='CNY',rate=7),dict(date='2026-11-06',quote='HKD',rate=8)]
        with patch('fx_rates.urlopen',return_value=BytesIO(json.dumps(rows).encode())):
            quote=fx_rates.currency_reference_rates('HKD',date(2026,11,8))
            self.assertEqual(quote['currency_usd_rate'],.125)
            self.assertEqual(quote['currency_rmb_rate'],.875)
            self.assertEqual(quote['fx_reference_date'],'2026-11-06')


if __name__=='__main__':unittest.main()
