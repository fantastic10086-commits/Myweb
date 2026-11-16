import unittest
import security_smoke as fixture
from models import db,CustomerFile
class AttachmentTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):fixture.SecuritySmokeTests.setUpClass()
 def test_upload_folder_and_access(self):
  h=fixture.SecuritySmokeTests();h.setUp();h.login('alice');path=f'/api/pi/{h.alice_pi}/customs-attachments'
  self.assertEqual(h.client.post(path,data={'files':h.image_upload()}).status_code,400)
  r=h.client.post(path,data={'csrf_token':h.token('/pi/list'),'files':h.image_upload()});self.assertEqual(r.status_code,200)
  self.assertEqual(len(r.json['files']),1)
  with fixture.application.app.app_context():
   f=CustomerFile.query.filter_by(pi_id=h.alice_pi,note='报关资料').one();self.assertEqual(f.customer_id,h.alice_customer)
  self.assertEqual(h.client.get(r.json['files'][0]['download_url']).status_code,200)
  page=h.client.get('/pi/list');self.assertIn('function uploadCustomsAttachments',page.text)
  h.login('bob');self.assertEqual(h.client.get(path).status_code,403)
if __name__=='__main__':unittest.main()
