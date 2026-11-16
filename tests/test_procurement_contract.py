import os
import unittest
import zipfile
from io import BytesIO
from openpyxl import load_workbook
import security_smoke as fixture
from models import db, PI, PIItem, Supplier, CustomerFile

class ContractTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls): fixture.SecuritySmokeTests.setUpClass()
 def test_contract_export_archive_and_permissions(self):
  h=fixture.SecuritySmokeTests();h.setUp();h.login('admin-test')
  with fixture.application.app.app_context():
   pi=db.session.get(PI,h.alice_pi);pi.received_amount=1
   supplier=Supplier(name='测试供应商',address='供应商地址',phone='123')
   db.session.add(supplier);db.session.commit()
   sid=supplier.id;item=PIItem.query.filter_by(pi_id=pi.id).first();iid=item.id
  url=f'/procurement/{h.alice_pi}/supplier-orders/export'
  payload={'supplier_id':sid,'document_type':'contract','contract_terms':{'payment':'=付款时确认','delivery':'交货时间另行填写'},'items':[{'pi_item_id':iid,'supplier_id':sid,'quantity':3,'unit_price':7.25}]}
  headers={'X-CSRFToken':h.token('/pi/list')}
  response=h.client.post(url,json=payload,headers=headers)
  self.assertEqual(response.status_code,200,response.data[:100])
  book=load_workbook(BytesIO(response.data));sheet=book.active
  self.assertEqual(sheet.title,'采购合同');self.assertEqual(sheet['A1'].value,'采购合同')
  self.assertIn('-CG-',sheet['C4'].value);self.assertEqual(sheet['H12'].value,21.75)
  cells=[c for row in sheet for c in row if c.value is not None]
  cell=next(c for c in cells if c.value=='=付款时确认');self.assertEqual(cell.data_type,'s')
  self.assertFalse(any('Alice Customer' in str(c.value) for c in cells))
  with fixture.application.app.app_context():
   record=CustomerFile.query.filter_by(pi_id=h.alice_pi,note='采购合同').one()
   self.assertEqual(record.customer_id,h.alice_customer)
   with open(os.path.join(fixture.application.app.config['UPLOAD_DIR'],record.stored_name),'rb') as f:self.assertEqual(f.read(),response.data)
  payload.pop('supplier_id');r=h.client.post(url,json=payload,headers=headers)
  self.assertEqual(r.status_code,200)
  with zipfile.ZipFile(BytesIO(r.data)) as bundle:self.assertEqual(len(bundle.namelist()),1)
  payload['contract_terms']={'payment':'x'*1501}
  self.assertEqual(h.client.post(url,json=payload,headers=headers).status_code,400)
  h.login('alice');self.assertEqual(h.client.post(url,json=payload,headers={'X-CSRFToken':h.token('/pi/list')}).status_code,403)
if __name__=='__main__':unittest.main()
