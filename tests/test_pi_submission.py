"""Isolated regression checks for PI numbering and replay protection."""
import re
import uuid
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
import security_smoke as fixture
from models import db, PI, Product
application=fixture.application

class SubmissionTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):fixture.SecuritySmokeTests.setUpClass()
 def setUp(self):
  self.helper=fixture.SecuritySmokeTests();self.helper.setUp();self.helper.login('alice');self.client=self.helper.client
 def data(self):
  page=self.client.get('/pi/create').text
  token=re.search('name="pi_submission_token" value="([^"]+)"',page).group(1)
  with application.app.app_context():pid=Product.query.first().id
  return dict(csrf_token=self.helper.token('/pi/create'),pi_submission_token=token,customer_id=self.helper.alice_customer,salesperson='Alice',notes='replay-'+uuid.uuid4().hex,account_id=self.helper.approved_account,currency='USD',exchange_rate='7',price_terms='FOB',product_order='1',selected_1='on',row_product_1=pid,qty_1='1',unit_price_1='10')
 def test_replay_and_independent_submission(self):
  data=self.data()
  with patch.object(application,'_generate_default_pi_documents',return_value=('demo.pdf','demo.xlsx')) as generate:
   first=self.client.post('/pi/create',data=data);second=self.client.post('/pi/create',data=data)
   self.assertEqual(first.status_code,302);self.assertEqual(first.location,second.location);self.assertEqual(generate.call_count,1)
   data['pi_submission_token']=uuid.uuid4().hex
   third=self.client.post('/pi/create',data=data);self.assertNotEqual(first.location,third.location)
 def test_pdf_failure_can_retry_same_token(self):
  data=self.data()
  with patch.object(application,'_generate_default_pi_documents',side_effect=RuntimeError('synthetic failure')):
   response=self.client.post('/pi/create',data=data);self.assertEqual(response.status_code,200);self.assertIn(data['pi_submission_token'],response.text)
  with patch.object(application,'_generate_default_pi_documents',return_value=('demo.pdf','demo.xlsx')):
   self.assertEqual(self.client.post('/pi/create',data=data).status_code,302)
 def test_parallel_number_reservations(self):
  def create(i):
   with application.app.app_context():
    number=application._generate_pi_number();db.session.add(PI(pi_number=number,salesperson='Alice',customer_id=self.helper.alice_customer));db.session.commit();return number
  with ThreadPoolExecutor(max_workers=5) as pool:numbers=list(pool.map(create,range(10)))
  self.assertEqual(len(set(numbers)),10)

if __name__=='__main__':unittest.main()
