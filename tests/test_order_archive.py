import os
import unittest
import security_smoke as fixture
from models import db, PI, Payment, Expense, CustomerFile
from order_archive import sync_order_files

class ArchiveTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls): fixture.SecuritySmokeTests.setUpClass()
 def test_automatic_archive_and_history(self):
  h=fixture.SecuritySmokeTests();h.setUp()
  with fixture.application.app.app_context():
   app=fixture.application.app
   name='archive-receipt.png'
   with open(os.path.join(app.config['UPLOAD_DIR'],name),'wb') as f:f.write(b'original receipt')
   pi=db.session.get(PI,h.alice_pi)
   db.session.add(Payment(pi_id=pi.id,amount=1,attachment=name))
   db.session.add(Expense(pi_id=pi.id,category='运费',amount=1,attachment=name))
   pi.shipping_attachment=name
   db.session.commit()
   files=CustomerFile.query.filter_by(pi_id=pi.id,original_name=name).all()
   self.assertEqual(len(files),1)
   self.assertEqual(files[0].customer_id,h.alice_customer)
   archive_id=files[0].id
   path=os.path.join(app.config['UPLOAD_DIR'],files[0].stored_name)
   with open(path,'rb') as f:self.assertEqual(f.read(),b'original receipt')
   with open(os.path.join(app.config['UPLOAD_DIR'],name),'wb') as f:f.write(b'changed receipt')
   pi.shipping_record_note='changed';db.session.commit()
   self.assertEqual(CustomerFile.query.filter_by(pi_id=pi.id,original_name=name).count(),2)
   f=db.session.get(CustomerFile,archive_id);f.deleted_at=__import__('datetime').datetime.utcnow();db.session.commit()
   sync_order_files(db.session,pi);db.session.commit()
   self.assertEqual(CustomerFile.query.filter_by(pi_id=pi.id,original_name=name).count(),2)
   active_id=CustomerFile.query.filter_by(pi_id=pi.id,original_name=name,deleted_at=None).one().id
  h.login('alice');self.assertEqual(h.client.get('/customer-files/'+str(archive_id)).status_code,404)
  h.login('bob');self.assertEqual(h.client.get('/customer-files/'+str(active_id)).status_code,403)
if __name__=='__main__':unittest.main()
