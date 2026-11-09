import unittest
import uuid
from unittest.mock import patch
from openpyxl import load_workbook
from werkzeug.datastructures import MultiDict
import security_smoke as fixture
from models import db, PI, Account, Product
from currency_utils import to_usd, to_rmb
from document_export import render_excel_template
application=fixture.application

class EuroTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):fixture.SecuritySmokeTests.setUpClass()
 def setUp(self):
  self.helper=fixture.SecuritySmokeTests();self.helper.setUp();self.helper.login('alice');self.client=self.helper.client
  rate_mock=patch('fx_rates.usd_reference_rates',return_value={'eur_usd_rate':1.3,'rmb_usd_rate':1/7,'fx_reference_date':'2026-11-02','fx_source':'Frankfurter'})
  rate_mock.start();self.addCleanup(rate_mock.stop)
 def test_euro_invoice_payment_and_reports(self):
  with application.app.app_context():
   account=Account(name='EUR Test',currency='EUR',bank_name='Example',brand='klista');db.session.add(account);db.session.commit();account_id=account.id;product=Product.query.first().id
  name='EUR-'+uuid.uuid4().hex
  data={'csrf_token':self.helper.token('/pi/create'),'pi_submission_token':uuid.uuid4().hex,'customer_id':self.helper.alice_customer,'salesperson':'Alice','notes':name,'account_id':account_id,'currency':'EUR','exchange_rate':'7','eur_usd_rate':'1.2','eur_rmb_rate':'8','fx_reference_date':'2026-10-30','fx_source':'手动填写','price_terms':'FOB','product_order':'1','selected_1':'on','row_product_1':product,'qty_1':'1','unit_price_1':'100','shipping_cost':'0'}
  with patch.object(application,'_generate_default_pi_documents',return_value=('demo.pdf','demo.xlsx')):
   result=self.client.post('/pi/create',data=data)
  self.assertEqual(result.status_code,302,result.text)
  with application.app.app_context():
   pi=PI.query.filter_by(notes=name).one();pi_id=pi.id
   self.assertEqual(to_usd(pi,100,True),120);self.assertEqual(to_rmb(pi,100),800)
   self.assertEqual(to_rmb(pi,10,'USD'),70)
   self.assertEqual(application._preload_products(pi)[0]['price_usd'],120)
   copy=application._pi_export_copy(pi);self.assertEqual(copy.eur_usd_rate,1.2)
   path=fixture.TEST_ROOT.name+'/eur.xlsx';render_excel_template(application.SYSTEM_DEFAULT_TEMPLATE_SOURCE,copy,path)
   values=[str(c.value) for row in load_workbook(path).active for c in row if c.value is not None];self.assertTrue(any('EUR' in x for x in values))
  payment={'csrf_token':self.helper.token('/pi/create'),'idempotency_key':uuid.uuid4().hex,'received_amount':'100','fee':'0','received_on':'2026-11-02','order_no':name,'receiving_account_id':self.helper.approved_account,'attachment':self.helper.image_upload()}
  self.client.post('/pi/%s/toggle-paid'%pi_id,data=payment)
  with application.app.app_context():self.assertEqual(db.session.get(PI,pi_id).received_amount,0)
  payment['receiving_account_id']=account_id;payment['attachment']=self.helper.image_upload()
  self.client.post('/pi/%s/toggle-paid'%pi_id,data=payment)
  with application.app.app_context():
   pi=db.session.get(PI,pi_id);self.assertEqual(pi.received_amount,100);self.assertTrue(pi.paid)
   self.assertEqual(pi.customer.total_deal_usd,130)
   application._migrate_db();self.assertEqual(pi.customer.total_deal_usd,130)
  self.helper.login('admin-test')
  for path in ('/pi/create','/pi/list','/sales-stats','/pi/%s/edit'%pi_id,'/procurement/%s'%pi_id):
   response=self.client.get(path);self.assertIn(response.status_code,(200,302),path)
   if path=='/sales-stats':self.assertIn('130.00',response.text)
   import re, subprocess
   for script in re.findall(r'<script(?:\s[^>]*)?>([\s\S]*?)</script>',response.text):
    if not script.strip() or script.lstrip().startswith(('[','{')):continue
    checked=subprocess.run(['node','--check'],input=script,universal_newlines=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    self.assertEqual(checked.returncode,0,checked.stderr)
  with patch.object(application,'_generate_default_pi_documents',return_value=('copy.pdf','copy.xlsx')):
   copied=self.client.post('/pi/%s/copy'%pi_id,data={'csrf_token':self.helper.token('/pi/create')})
  copied_id=int(copied.location.split('/pi/')[1].split('/')[0])
  with application.app.app_context():self.assertEqual(db.session.get(PI,copied_id).eur_rmb_rate,8)
  data['draft_rows']='[]';data['csrf_token']=self.helper.token('/pi/create')
  draft=self.client.post('/pi/drafts/save',data=data);self.assertEqual(draft.status_code,200)
  import json
  from models import PIDraft
  with application.app.app_context():self.assertEqual(json.loads(db.session.get(PIDraft,draft.json['id']).payload)['fields']['eur_usd_rate'],'1.2')
  self.helper.login('admin-test')
  response=self.client.get('/profit-report');self.assertEqual(response.status_code,200)
  # Retrieval failure remains an explicit manual-entry path.
  with patch('fx_rates.latest_eur_rates',side_effect=ValueError('offline')):
   self.assertEqual(self.client.get('/api/exchange-rates/eur').status_code,503)
 def test_invalid_rates_rejected(self):
  for value in ('','0','-1','nan','inf'):
   with self.assertRaises(ValueError):application._eur_snapshot(MultiDict({'eur_usd_rate':value,'eur_rmb_rate':'8'}),'EUR')

if __name__=='__main__':unittest.main()
