"""Isolated authenticated tests for list navigation and account isolation."""
import unittest
from urllib.parse import urlparse, parse_qs
import security_smoke as fixture
from models import User, db, UserListPreference
from list_preferences import FILTERS
application = fixture.application

class PreferenceTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):fixture.SecuritySmokeTests.setUpClass()
 def setUp(self):
  self.client=application.app.test_client()
  with application.app.app_context():
   db.session.query(UserListPreference).delete();db.session.commit()
  self.signin('admin-test')
 def signin(self,name,client=None):
  client=client or self.client
  with application.app.app_context():
   user=User.query.filter_by(username=name).one();uid,version=user.id,user.auth_version
  with client.session_transaction() as s:s.clear();s['user_id']=uid;s['auth_version']=version
 def path(self,endpoint):
  with application.app.test_request_context():return fixture.application.url_for(endpoint)
 def test_all_lists_restore_and_clear(self):
  cases={'customer_list':{'search':'synthetic'},'product_list':{'search':'synthetic','sort':'name','page':'2'},'pi_list':{'country':'Brazil'},'procurement_select':{'order_status':['pending','partial']},'packing_list_index':{'status':'draft'},'fees_report':{'profit_status':'incomplete_cost'},'sales_stats':{'sp':'Alice'},'audit_logs':{'entity_type':'payment','page':'2'},'finance_reconciliation':{'tab':'expense','month':'','status':'unpaid'}}
  for endpoint,args in cases.items():
   with self.subTest(endpoint=endpoint):
    path=self.path(endpoint)
    self.assertEqual(self.client.get(path,query_string=args).status_code,200)
    restored=self.client.get(path);self.assertEqual(restored.status_code,302)
    actual=parse_qs(urlparse(restored.location).query,keep_blank_values=True)
    for k,v in args.items():self.assertEqual(actual[k],v if isinstance(v,list) else [v])
    self.assertEqual(self.client.get(path+'?clear_filters=1',follow_redirects=True).status_code,200)
    self.assertEqual(self.client.get(path).status_code,200)
 def test_users_and_explicit_empty_are_independent(self):
  path=self.path('product_list')
  self.client.get(path+'?search=demo&filter=inactive&page=2')
  other=application.app.test_client();self.signin('alice',other)
  self.assertEqual(other.get(path).status_code,200)
  other.get(path+'?search=alice')
  self.assertIn('demo',self.client.get(path).location)
  self.client.get(path+'?search=')
  restored=self.client.get(path)
  self.assertEqual(parse_qs(urlparse(restored.location).query,keep_blank_values=True),{'search':['']})
  fresh=application.app.test_client();self.signin('alice',fresh)
  self.assertIn('alice',fresh.get(path).location)
 def test_customer_detail_preferences_are_per_customer(self):
  path='/customers/'+str(fixture.SecuritySmokeTests.alice_customer)
  other='/customers/'+str(fixture.SecuritySmokeTests.bob_customer)
  self.assertEqual(self.client.get(path+'?pi_number=TEST').status_code,200)
  self.assertIn('pi_number=TEST',self.client.get(path).location)
  self.assertEqual(self.client.get(other).status_code,200)
  self.assertEqual(self.client.get(path+'?clear_filters=1',follow_redirects=True).status_code,200)

 def test_presets_freeze_range_and_unknown_keys_are_not_saved(self):
  path=self.path('fees_report')
  self.client.get(path+'?preset=last_month&unsafe=https://example.invalid')
  restored=self.client.get(path)
  params=parse_qs(urlparse(restored.location).query)
  self.assertIn('date_from',params);self.assertIn('date_to',params)
  self.assertNotIn('preset',params);self.assertNotIn('unsafe',params)
 def test_legacy_procurement_session(self):
  with self.client.session_transaction() as s:s['procurement_filters']={'order_status':'pending,partial','pi_number':'demo'}
  path=self.path('procurement_select')
  self.assertIn('demo',self.client.get(path).location)
  self.client.get(path+'?clear_filters=1')
  self.assertEqual(self.client.get(path).status_code,200)

if __name__=='__main__':unittest.main()
