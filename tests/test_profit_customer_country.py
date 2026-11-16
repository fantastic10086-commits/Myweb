import unittest
from unittest.mock import patch
import security_smoke as fixture
from models import db,Customer,PI,PIItem,Payment,Product

class ProfitFilterTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):fixture.SecuritySmokeTests.setUpClass()
 def test_filters_summary_memory_and_access(self):
  h=fixture.SecuritySmokeTests();h.setUp()
  with fixture.application.app.app_context():
   product=Product.query.first()
   for i,(name,country,amount) in enumerate([('Alpha Buyer','中国',20),('Beta Buyer','美国',30)]):
    customer=Customer(name=name,country=country,salesperson='Alice',contact_person='Anna' if i==0 else 'Ben');db.session.add(customer);db.session.flush()
    pi=PI(pi_number='PI-FILTER-'+str(i),customer_id=customer.id,salesperson='Alice',currency='USD',exchange_rate=6.5,total_amount=amount,received_amount=amount)
    db.session.add(pi);db.session.flush();db.session.add(PIItem(pi_id=pi.id,product_id=product.id,quantity=1,unit_price=amount,amount=amount));db.session.add(Payment(pi_id=pi.id,amount=amount))
   db.session.commit()
  h.login('admin-test')
  captured=[]
  original=fixture.application.render_template
  def receive(template,**context):
   if template=='fees.html':captured.append(context)
   return original(template,**context)
  capture=patch.object(fixture.application,'render_template',side_effect=receive);capture.start()
  try:
   r=h.client.get('/profit-report?customer_name=Alpha&country=China')
   self.assertEqual(r.status_code,200);context=captured[-1]
   self.assertEqual(len(context['pi_list']),1)
   self.assertEqual(context['summary']['received_rmb'],130)
   self.assertEqual(context['country_filter'],'中国')
   self.assertIn('id="profitCustomerFilter"',r.text);self.assertIn('id="profitCountryFilter"',r.text)
   self.assertLess(r.text.index('name="date_to"'),r.text.index('id="profitCustomerFilter"'))
   restored=h.client.get('/profit-report');self.assertEqual(restored.status_code,302);self.assertIn('customer_name=Alpha',restored.location);self.assertIn('country=China',restored.location)
   h.client.get('/profit-report?customer_name=Alpha&country=美国');self.assertEqual(len(captured[-1]['pi_list']),0);self.assertEqual(captured[-1]['summary']['received_rmb'],0)
   h.client.get('/profit-report?customer_name=Anna&country=中国&profit_status=incomplete_cost');self.assertEqual(len(captured[-1]['pi_list']),1)
   cleared=h.client.get('/profit-report?clear_filters=1',follow_redirects=True);self.assertEqual(cleared.status_code,200);self.assertEqual(len(captured[-1]['pi_list']),2)
   h.login('alice');self.assertEqual(h.client.get('/profit-report?country=中国').status_code,403)
  finally:capture.stop()
if __name__=='__main__':unittest.main()
