"""Invoice charge/discount records survive creation, draft payloads and export."""
import json
import unittest
import uuid
from unittest.mock import patch
from openpyxl import load_workbook
import security_smoke as fixture
from models import db, PI, Product, FieldOption
from document_export import render_excel_template
application=fixture.application

class AdjustmentTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):fixture.SecuritySmokeTests.setUpClass()
 def setUp(self):
  self.helper=fixture.SecuritySmokeTests();self.helper.setUp();self.helper.login('alice');self.client=self.helper.client
 def test_multiple_charges_and_discount_export(self):
  with application.app.app_context():
   product=Product.query.first().id
   options=FieldOption.query.filter_by(field_key='shipping_note').all()
   self.assertGreaterEqual(len(options),2)
   rows=[{'name':options[0].value,'amount':10},{'name':options[1].value,'amount':-3}]
  name='ADJUST-'+uuid.uuid4().hex
  data={'csrf_token':self.helper.token('/pi/create'),'pi_submission_token':uuid.uuid4().hex,'customer_id':self.helper.alice_customer,'salesperson':'Alice','notes':name,'account_id':self.helper.approved_account,'currency':'USD','exchange_rate':'7','price_terms':'FOB','product_order':'1','selected_1':'on','row_product_1':product,'qty_1':'1','unit_price_1':'10','shipping_cost':'10','shipping_note':rows[0]['name'],'adjustment_operation':'add','customer_adjustments_json':json.dumps(rows)}
  with patch.object(application,'_generate_default_pi_documents',return_value=('demo.pdf','demo.xlsx')):
   result=self.client.post('/pi/create',data=data)
  self.assertEqual(result.status_code,302,result.text)
  with application.app.app_context():
   pi=PI.query.filter_by(notes=name).one()
   self.assertEqual(pi.shipping_cost,7)
   self.assertEqual(pi.grand_total,17)
   self.assertEqual(len(pi.customer_adjustments),2)
   copied=application._pi_export_copy(pi)
   self.assertEqual(copied.customer_adjustments,pi.customer_adjustments)
   path=fixture.TEST_ROOT.name+'/adjustments.xlsx'
   render_excel_template(application.SYSTEM_DEFAULT_TEMPLATE_SOURCE,copied,path)
   ws=load_workbook(path).active
   values=[str(cell.value) for row in ws for cell in row if cell.value is not None]
   self.assertTrue(any('USD +10.00' in v for v in values),values)
   self.assertTrue(any('USD -3.00' in v for v in values),values)
   self.assertIn('17',values)
   # Legacy single-charge forms/templates remain valid.
   pi.customer_adjustments=None
   from customer_adjustments import adjustment_rows
   self.assertEqual(len(adjustment_rows(pi)),1)
  # Draft field payload must retain every adjustment record.
  draft=self.client.post('/pi/drafts/save', data=dict(data, draft_rows='[]'))
  self.assertEqual(draft.status_code,200,draft.text)
  with application.app.app_context():
   from models import PIDraft
   saved=json.loads(db.session.get(PIDraft,draft.json['id']).payload)
   self.assertEqual(json.loads(saved['fields']['customer_adjustments_json']),rows)
   original=PI.query.filter_by(notes=name).one()
   original.customer_adjustments=[{'name':rows[0]['name'],'english':'First','amount':10},{'name':rows[1]['name'],'english':'Second','amount':-3}]
   db.session.commit();original_id=original.id
  with patch.object(application,'_generate_default_pi_documents',return_value=('copy.pdf','copy.xlsx')):
   copied_response=self.client.post('/pi/%s/copy'%original_id,data={'csrf_token':self.helper.token('/pi/create')})
  self.assertEqual(copied_response.status_code,302)
  copied_id=int(copied_response.location.split('/pi/')[1].split('/')[0])
  with application.app.app_context():
   self.assertEqual(len(db.session.get(PI,copied_id).customer_adjustments),2)
  page=self.client.get('/pi/create')
  self.assertIn('customer_adjustments_json',page.text)
 def test_invalid_rows_and_zero_net_are_handled(self):
  from werkzeug.datastructures import MultiDict
  with application.app.test_request_context():
   with self.assertRaises(ValueError):application._parse_customer_adjustments(MultiDict({'customer_adjustments_json':'{"bad":1}'}))
   with self.assertRaises(ValueError):application._parse_customer_adjustments(MultiDict({'customer_adjustments_json':'[{"name":"","amount":3}]'}))
   option=FieldOption.query.filter_by(field_key='shipping_note').first()
   rows=application._parse_customer_adjustments(MultiDict({'customer_adjustments_json':json.dumps([{'name':option.value,'amount':5},{'name':option.value,'amount':-5}])}))
   self.assertEqual(len(rows),2);self.assertEqual(sum(r['amount'] for r in rows),0)

if __name__=='__main__':unittest.main()
