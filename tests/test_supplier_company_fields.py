import unittest
import security_smoke as fixture
from models import db,Supplier

class SupplierCompanyTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):fixture.SecuritySmokeTests.setUpClass()
 def test_optional_company_fields_and_required_name(self):
  h=fixture.SecuritySmokeTests();h.setUp();h.login('admin-test')
  token=h.token('/suppliers/add');headers={'X-CSRFToken':token}
  self.assertEqual(h.client.post('/api/suppliers',json={'name':'  ','company_name':'Only company'},headers=headers).status_code,400)
  r=h.client.post('/api/suppliers',json={'name':'Short supplier'},headers=headers)
  self.assertEqual(r.status_code,201,r.data)
  self.assertEqual(r.json['supplier']['company_name'],'');self.assertEqual(r.json['supplier']['tax_number'],'')
  r=h.client.post('/suppliers/add',data={'csrf_token':token,'name':'Full supplier','company_name':'公司全称有限公司','tax_number':'00123456789012345678'})
  self.assertEqual(r.status_code,302)
  with fixture.application.app.app_context():
   supplier=Supplier.query.filter_by(name='Full supplier').one();sid=supplier.id
   self.assertEqual(supplier.tax_number,'00123456789012345678')
  edit=f'/suppliers/{sid}/edit'
  r=h.client.post(edit,data={'csrf_token':token,'name':'Full supplier','company_name':'更新后公司全称','tax_number':'=00123'})
  self.assertEqual(r.status_code,302)
  with fixture.application.app.app_context():
   supplier=db.session.get(Supplier,sid);self.assertEqual(supplier.company_name,'更新后公司全称');self.assertEqual(supplier.tax_number,'=00123')
  self.assertIn('更新后公司全称',h.client.get(f'/suppliers/{sid}').text)
  self.assertIn('name="tax_number"',h.client.get(edit).text)
  self.assertEqual(h.client.post('/api/suppliers',json={'name':'Too long','company_name':'x'*301},headers=headers).status_code,400)
  self.assertEqual(h.client.post('/api/suppliers',json={'name':'API full','company_name':'API Company','tax_number':'000123'},headers=headers).json['supplier']['tax_number'],'000123')
if __name__=='__main__':unittest.main()
