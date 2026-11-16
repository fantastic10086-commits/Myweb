import json
import unittest
import security_smoke as fixture
from models import db, Customer, PI

class RequiredContactsTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls): fixture.SecuritySmokeTests.setUpClass()
 def test_quick_add_and_customer_forms_require_named_contact(self):
  h=fixture.SecuritySmokeTests();h.setUp();h.login('alice')
  csrf=h.token('/pi/create')
  base={'csrf_token':csrf,'name':'Quick Contact Customer'}
  self.assertEqual(h.client.post('/api/customers/add',data=base).status_code,400)
  self.assertEqual(h.client.post('/api/customers/add',data=dict(base,contacts_json='[]')).status_code,400)
  entry=dict(name='Maria',position='Manager',phone='123',email='maria@example.com',whatsapp='456',wechat='maria',note='联系备注',is_default=True)
  r=h.client.post('/api/customers/add',data=dict(base,contacts_json=json.dumps([entry])))
  self.assertEqual(r.status_code,200,r.data)
  cid=r.json['customer']['id']
  with fixture.application.app.app_context():
   customer=db.session.get(Customer,cid);saved=customer.contact_entries[0]
   for key,value in entry.items():self.assertEqual(saved[key],value)
   version=customer.version
  edit=f'/customers/{cid}/edit'
  r=h.client.post(edit,data={'csrf_token':csrf,'version':version,'name':'Must not change','contacts_json':'[]'})
  self.assertEqual(r.status_code,200)
  self.assertIn('请至少添加一位联系人',r.text)
  with fixture.application.app.app_context():self.assertEqual(db.session.get(Customer,cid).name,base['name'])
  malformed=[entry,dict(name=' ',phone='999')]
  self.assertEqual(h.client.post('/api/customers/add',data=dict(base,contacts_json=json.dumps(malformed))).status_code,400)
  r=h.client.post('/customers/add',data=dict(base,contacts_json='[]'))
  self.assertEqual(r.status_code,200);self.assertIn('请至少添加一位联系人',r.text)
  r=h.client.post('/customers/add',data=dict(base,name='Standard Contact Customer',contacts_json=json.dumps([entry])))
  self.assertEqual(r.status_code,302)
  with fixture.application.app.app_context():
   customer=Customer.query.filter_by(name='Standard Contact Customer').one()
   self.assertEqual(customer.contact_entries[0]['name'],'Maria')
  for path in ['/pi/create',f'/pi/{h.alice_pi}/edit']:
   page=h.client.get(path)
   self.assertEqual(page.status_code,200)
   self.assertIn('联系人姓名（必填）',page.text)
   self.assertIn('qaContactDetails',page.text)
   self.assertIn('quick_customer_contact.js',page.text)
   self.assertIn('appendQuickCustomerContact(fd)',page.text)
if __name__=='__main__':unittest.main()
