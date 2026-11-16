import unittest
from io import BytesIO
from datetime import date
from openpyxl import load_workbook
import security_smoke as fixture
from models import db,PI,Payment,FinanceReview

class ExportTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):fixture.SecuritySmokeTests.setUpClass()
 def test_filtered_export_permissions_and_text(self):
  app=fixture.application
  with app.app.app_context():
   for owner,customer in [('Alice',self.helper_customer('Alice')),('Bob',self.helper_customer('Bob'))]:
    pi=PI(pi_number='EXPORT-'+owner,customer_id=customer,salesperson=owner,currency='USD',total_amount=100)
    db.session.add(pi);db.session.flush()
    p=Payment(pi_id=pi.id,amount=50,order_no='=12345678901234567890',performance_usd_rate=1)
    db.session.add(p);db.session.flush();db.session.add(FinanceReview(kind='payment',record_id=p.id,occurred_on=date(2026,10,15)))
   db.session.commit()
  helper=fixture.SecuritySmokeTests();helper.setUp();helper.login('alice')
  response=helper.client.get('/sales-stats?export=xlsx&sp=Alice&sp=Bob&date_from=2026-10-01&date_to=2026-10-31')
  self.assertEqual(response.status_code,200)
  wb=load_workbook(BytesIO(response.data));ws=wb['实际到账明细']
  self.assertEqual(ws.max_row,3);self.assertEqual(ws['C2'].value,'Alice')
  self.assertEqual(ws['F2'].data_type,'s');self.assertEqual(ws['F2'].value,'=12345678901234567890')
  self.assertEqual(ws['K3'].value,50)
  helper.login('admin-test')
  response=helper.client.get('/sales-stats?export=xlsx&sp=Alice&sp=Bob&date_from=2026-10-01&date_to=2026-10-31')
  ws=load_workbook(BytesIO(response.data)).active;self.assertEqual(ws.max_row,4);self.assertEqual(ws['K4'].value,100)
 def helper_customer(self,name):
  return fixture.SecuritySmokeTests.alice_customer if name=='Alice' else fixture.SecuritySmokeTests.bob_customer

if __name__=='__main__':unittest.main()
