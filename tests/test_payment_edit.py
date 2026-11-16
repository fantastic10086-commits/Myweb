import unittest
from datetime import date,datetime,timedelta
from unittest.mock import patch
import security_smoke as fixture
from models import db,PI,Payment,FinanceReview,AuditLog

class PaymentEditTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):fixture.SecuritySmokeTests.setUpClass()
 def setUp(self):
  self.h=fixture.SecuritySmokeTests();self.h.setUp();self.h.login('alice')
  with fixture.application.app.app_context():
   pi=db.session.get(PI,self.h.alice_pi);pi.total_amount=100;pi.items[0].amount=100;pi.items[0].unit_price=100
   pi.shipping_completed=True;pi.shipping_date=date(2026,11,1);pi.shipping_tracking_no='KEEP-TRACK';pi.shipping_record_note='KEEP-NOTE'
   for p in pi.payments:db.session.delete(p)
   db.session.flush()
   p=Payment(pi_id=pi.id,amount=100,order_no='EDIT-REF',fee=0,performance_usd_rate=1,performance_date=date(2026,11,1),performance_reference_date='2026-11-01',performance_source='USD原币',receiving_account_name='Original account',attachment='original.png')
   db.session.add(p);db.session.flush();self.pid=p.id
   AuditLog.query.filter_by(entity_type='payment',entity_id=p.id).delete(synchronize_session=False)
   db.session.add(FinanceReview(kind='payment',record_id=p.id,occurred_on=date(2026,11,1),checked=True,checked_by='admin-test',checked_at=datetime.utcnow()))
   fixture.application._recalculate_pi_payments(pi);db.session.commit()
  self.url=f'/api/pi/{self.h.alice_pi}/payments/{self.pid}/edit';self.headers={'X-CSRFToken':self.h.token('/pi/list?stage=&transition=')}
 def payload(self,**overrides):
  payment=self.h.client.get(f'/api/pi/{self.h.alice_pi}/payments').json['payments'][0]
  data=dict(amount=60,received_on='2026-11-01',reason='实际金额录入更正',revision=payment['revision']);data.update(overrides);return data
 def test_edit_is_immediate_audited_and_preserves_shipping(self):
  payload=self.payload()
  with patch.object(fixture.application,'receipt_performance_snapshot',side_effect=AssertionError('must preserve same-day rate')):
   r=self.h.client.post(self.url,json=payload,headers=self.headers)
  self.assertEqual(r.status_code,200,r.data);self.assertTrue(r.json['shipping_payment_shortfall'])
  with fixture.application.app.app_context():
   pi=db.session.get(PI,self.h.alice_pi);self.assertEqual(pi.received_amount,60);self.assertFalse(pi.paid)
   self.assertTrue(pi.shipping_completed);self.assertEqual(pi.shipping_date,date(2026,11,1));self.assertEqual(pi.shipping_tracking_no,'KEEP-TRACK');self.assertEqual(pi.shipping_record_note,'KEEP-NOTE')
   p=db.session.get(Payment,self.pid);self.assertEqual(p.order_no,'EDIT-REF');self.assertEqual(p.attachment,'original.png');self.assertEqual(p.receiving_account_name,'Original account')
   review=FinanceReview.query.filter_by(kind='payment',record_id=self.pid).one();self.assertFalse(review.checked)
   audit=AuditLog.query.filter_by(entity_type='payment',entity_id=self.pid,action='update').one();self.assertIn('实际金额录入更正',audit.after_json)
  self.assertEqual(self.h.client.post(self.url,json=payload,headers=self.headers).status_code,409)
  response=self.h.client.get(f'/api/pi/{self.h.alice_pi}/payments').json
  self.assertEqual(response['payments'][0]['received_on'],'2026-11-01');self.assertEqual(len(response['payments'][0]['edits']),1)
  page=self.h.client.get('/pi/list?stage=&transition=');self.assertIn('已发货 · 回款未付清',page.text)
  r=self.h.client.post(self.url,json=self.payload(amount=100),headers=self.headers);self.assertEqual(r.status_code,200);self.assertFalse(r.json['shipping_payment_shortfall'])
 def test_concurrent_change_is_not_overwritten(self):
  payload=self.payload(received_on='2026-10-16')
  def concurrent_quote(currency,day):
   with fixture.application.app.app_context():
    pi=db.session.get(PI,self.h.alice_pi);p=db.session.get(Payment,self.pid);p.amount=90
    fixture.application._recalculate_pi_payments(pi);db.session.commit()
   return dict(performance_usd_rate=1,performance_date=day,performance_reference_date=day.isoformat(),performance_source='USD原币')
  with patch.object(fixture.application,'receipt_performance_snapshot',side_effect=concurrent_quote):
   r=self.h.client.post(self.url,json=payload,headers=self.headers)
  self.assertEqual(r.status_code,409,r.data)
  with fixture.application.app.app_context():self.assertEqual(db.session.get(Payment,self.pid).amount,90)
 def test_validation_and_ownership(self):
  for fields in [dict(reason=' '),dict(amount=0),dict(amount=-1),dict(amount='NaN'),dict(amount=1.001),dict(amount=101),dict(received_on='bad'),dict(received_on='2099-01-01')]:
   r=self.h.client.post(self.url,json=self.payload(**fields),headers=self.headers);self.assertEqual(r.status_code,400,r.data)
  self.assertEqual(self.h.client.post(self.url,json=self.payload()).status_code,400)
  payload=self.payload();self.h.login('bob');self.assertEqual(self.h.client.post(self.url,json=payload,headers={'X-CSRFToken':self.h.token('/pi/list')}).status_code,403)
 def test_changed_date_reprices_and_failure_keeps_original(self):
  with fixture.application.app.app_context():
   pi=db.session.get(PI,self.h.alice_pi);pi.currency='RMB';db.session.commit()
  data=self.payload(received_on='2026-10-15')
  with patch.object(fixture.application,'receipt_performance_snapshot',side_effect=ValueError('reference unavailable')):
   r=self.h.client.post(self.url,json=data,headers=self.headers);self.assertEqual(r.status_code,503)
  with fixture.application.app.app_context():self.assertEqual(db.session.get(Payment,self.pid).amount,100)
  snapshot=dict(performance_usd_rate=.15,performance_date=date(2026,10,15),performance_reference_date='2026-10-15',performance_source='test')
  with patch.object(fixture.application,'receipt_performance_snapshot',return_value=snapshot) as quote:
   r=self.h.client.post(self.url,json=data,headers=self.headers);self.assertEqual(r.status_code,200,r.data);quote.assert_called_once_with('RMB',date(2026,10,15))
  with fixture.application.app.app_context():
   p=db.session.get(Payment,self.pid);self.assertEqual(p.performance_date,date(2026,10,15));self.assertEqual(p.performance_usd_rate,.15)
   self.assertAlmostEqual(p.pi.customer.total_deal_usd,9)
  with patch.object(fixture.application,'render_template',return_value='') as render:
   self.assertEqual(self.h.client.get('/sales-stats?date_from=2026-10-01&date_to=2026-10-31').status_code,200)
   self.assertEqual(render.call_args[1]['grand_total'],9)
   self.assertEqual(self.h.client.get('/sales-stats?date_from=2026-11-01&date_to=2026-11-30').status_code,200)
   self.assertEqual(render.call_args[1]['grand_total'],0)
if __name__=='__main__':unittest.main()
