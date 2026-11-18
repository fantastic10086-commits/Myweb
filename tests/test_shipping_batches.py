"""Authenticated batch registration, legacy preservation, archive and status regression."""
import io
import json
import os
import unittest
import uuid
from datetime import date, datetime
from PIL import Image
import test_dispatch_steps as steps
from models import db, PI, ShippingBatch, Payment, CustomerFile, PackingList, PIItem
from shipping_batches import migrate_shipping_batches

application = steps.application


class ShippingBatchTests(unittest.TestCase):
    setUpClass = classmethod(lambda cls: steps.fixture.SecuritySmokeTests.setUpClass())
    def setUp(self):
        self.client = application.app.test_client()
        with application.app.app_context():
            self.pi_id = steps.seed_order(uuid.uuid4().hex[:10])
        self.as_user('alice')
        self.csrf = steps.fixture.SecuritySmokeTests.token(self, '/')
    as_user = steps.DispatchStepTests.as_user
    state = steps.DispatchStepTests.state
    payload = steps.DispatchStepTests.payload
    post = steps.DispatchStepTests.post

    def ready(self):
        response = self.post(self.payload(action='confirm_no_expenses', step='expenses'))
        self.assertEqual(response.status_code, 200, response.get_json())

    def ship(self, **kwargs):
        payload = dict(action='complete', step='shipping', new_batch=True, final_batch=False,
                       shipping_date='2026-11-17', tracking_no='FIRST')
        payload.update(kwargs)
        response = self.post(self.payload(**payload))
        self.assertEqual(response.status_code, 200, response.get_json())
        return response.get_json()

    def test_two_batches_draft_final_edit_and_retry(self):
        self.ready()
        payload = self.payload(action='complete', step='shipping', new_batch=True, final_batch=False,
                               tracking_no='FIRST', shipping_note='第一批')
        first = self.post(payload).get_json()
        self.assertFalse(first['shipping_completed']); self.assertEqual(first['shipped_batch_count'], 1)
        self.assertEqual(self.post(payload).status_code, 200)
        first_id = first['batches'][0]['id']
        saved = self.post(self.payload(step='shipping', edit_shipping=True, new_batch=True,
                                      final_batch=True, tracking_no='SECOND', shipping_note='第二批')).get_json()
        self.assertEqual(len(saved['batches']), 2); self.assertEqual(saved['shipped_batch_count'], 1)
        self.assertFalse(saved['shipping_completed']); self.assertTrue(saved['batches'][1]['is_final'])
        second_id = saved['batches'][1]['id']
        self.assertEqual(self.post(self.payload(step='shipping', edit_shipping=True, new_batch=True)).status_code, 400)
        final = self.ship(new_batch=False, batch_id=second_id, final_batch=True, tracking_no='SECOND')
        self.assertTrue(final['shipping_completed']); self.assertEqual(final['shipped_batch_count'], 2)
        edited = self.post(self.payload(step='shipping', edit_shipping=True, batch_id=first_id,
                                        tracking_no='FIRST-EDITED', shipping_note='补充第一批')).get_json()
        self.assertTrue(edited['shipping_completed'])
        self.assertEqual(edited['batches'][1]['tracking_no'], 'SECOND')
        self.assertEqual(edited['batches'][0]['note'], '补充第一批')
        self.assertEqual(self.post(self.payload(action='complete', batch_id=second_id)).status_code, 400)
        # Adding a later partial batch reopens the order without erasing previous shipments.
        third = self.ship(tracking_no='THIRD')
        self.assertFalse(third['shipping_completed']); self.assertEqual(third['shipped_batch_count'], 3)
        self.assertFalse(any(b['is_final'] for b in third['batches']))

    def test_legacy_migration_is_idempotent_and_preserves_information(self):
        with application.app.app_context():
            pi = db.session.get(PI, self.pi_id)
            pi.shipping_completed = True; pi.shipping_date = date(2026, 10, 7)
            pi.shipping_tracking_no = 'HISTORY'; pi.shipping_record_note = '历史发货'
            pi.shipping_attachment = 'historical.png'; pi.shipping_recorded_by = 'old-user'
            pi.shipping_recorded_at = datetime(2026, 10, 7, 2, 30)
            db.session.commit()
            migrate_shipping_batches(); migrate_shipping_batches()
            batch = ShippingBatch.query.filter_by(pi_id=self.pi_id).one()
            self.assertEqual(batch.note, '历史发货'); self.assertEqual(batch.attachment, 'historical.png')
            self.assertEqual(batch.recorded_by, 'old-user'); self.assertEqual(batch.status, 'shipped')
            self.assertTrue(batch.is_final); self.assertEqual(batch.shipping_date, date(2026, 10, 7))
        self.ready()
        state = self.ship(tracking_no='NEW-HISTORY')
        self.assertEqual(state['batches'][0]['tracking_no'], 'HISTORY')
        self.assertEqual(state['batches'][0]['recorded_at'], '2026-10-07 10:30')
        self.assertFalse(state['shipping_completed'])

    def test_batch_images_archive_and_access(self):
        self.ready()
        ids = []
        for color in ('red', 'blue'):
            image = io.BytesIO(); Image.new('RGB', (2, 2), color).save(image, format='PNG'); image.seek(0)
            data = self.payload(action='complete', step='shipping', new_batch=True, final_batch=False, tracking_no=color)
            response = self.client.post('/api/pi/{}/dispatch'.format(self.pi_id),
                data={'payload': json.dumps(data), 'shipping_attachment': (image, color + '.png')},
                headers={'X-CSRFToken': self.csrf})
            self.assertEqual(response.status_code, 200, response.get_json())
            ids.append(response.get_json()['batches'][-1]['attachment_url'])
        for url in ids:
            response = self.client.get(url); self.assertEqual(response.status_code, 200); response.close()
        with application.app.app_context():
            files = CustomerFile.query.filter_by(pi_id=self.pi_id).all()
            self.assertEqual(len(files), 2)
            self.assertTrue(all(os.path.isfile(os.path.join(application.app.config['UPLOAD_DIR'], f.stored_name)) for f in files))
        self.as_user('bob')
        for url in ids:
            self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.get('/api/pi/{}/shipping-record'.format(self.pi_id)).status_code, 403)

    def test_cancel_only_selected_batch_admin_and_version_protection(self):
        self.ready(); first = self.ship(); first_id = first['batches'][0]['id']
        second = self.ship(final_batch=True, tracking_no='SECOND'); second_id = second['batches'][1]['id']
        url = '/api/pi/{}/shipping-batches/{}/cancel'.format(self.pi_id, second_id)
        self.assertEqual(self.client.post(url, json={'version':second['version']}, headers={'X-CSRFToken':self.csrf}).status_code, 403)
        self.as_user('admin-test')
        self.assertEqual(self.client.post(url, json={'version':first['version']}, headers={'X-CSRFToken':self.csrf}).status_code, 409)
        result = self.client.post(url, json={'version':second['version']}, headers={'X-CSRFToken':self.csrf}).get_json()
        self.assertFalse(result['shipping_completed']); self.assertEqual(result['shipped_batch_count'], 1)
        self.assertEqual(result['batches'][1]['status'], 'cancelled')
        self.assertEqual(result['batches'][1]['tracking_no'], 'SECOND')
        self.assertEqual(result['batches'][0]['id'], first_id)
        third = self.ship(final_batch=True, tracking_no='THIRD')
        self.assertEqual(third['batches'][2]['batch_no'], 3); self.assertTrue(third['shipping_completed'])
        old = self.post(self.payload(step='shipping', edit_shipping=True, batch_id=second_id))
        self.assertEqual(old.status_code, 400)

    def test_filter_all_tracking_numbers_and_partial_payment_warning(self):
        self.ready(); self.ship(tracking_no='A' * 200)
        state = self.ship(tracking_no='SECOND-LONG-TRACK')
        with application.app.app_context():
            Payment.query.filter_by(pi_id=self.pi_id).one().amount = 30; db.session.commit()
            self.assertTrue(db.session.get(PI, self.pi_id).shipping_payment_shortfall)
            number = db.session.get(PI, self.pi_id).pi_number
        self.client.get('/pi/list?clear_filters=1', follow_redirects=True)
        html = self.client.get('/pi/list?tracking_no=SECOND-LONG-TRACK').get_data(as_text=True)
        self.assertIn(number, html); self.assertIn('部分发货', html); self.assertIn('已发货 · 回款未付清', html)
        self.assertFalse(self.state()['can_ship'])
        self.assertEqual(self.post(self.payload(action='complete', new_batch=True, final_batch=True)).status_code, 400)
        self.assertEqual(self.state()['shipped_batch_count'], state['shipped_batch_count'])

    def test_new_batch_permissions_validation_and_stale_submit(self):
        self.ready(); first = self.ship()
        with application.app.app_context():
            other_id = steps.seed_order('OTHER-BATCH-ORDER')
            other = ShippingBatch(pi_id=other_id, batch_no=1, status='shipped', is_final=True)
            db.session.add(other); db.session.commit(); other_batch_id = other.id
        self.assertEqual(self.post(self.payload(edit_shipping=True, batch_id=other_batch_id)).status_code, 400)
        payload = self.payload(action='complete', new_batch=True, final_batch=False)
        self.assertEqual(self.client.post('/api/pi/{}/dispatch'.format(self.pi_id), data={'payload':json.dumps(payload)}).status_code, 400)
        self.as_user('bob'); self.assertEqual(self.post(payload).status_code, 403)
        self.as_user('alice')
        self.assertEqual(self.post(self.payload(action='save')).status_code, 200)
        self.assertEqual(self.post(payload).status_code, 409)
        for bad in ({'shipping_date':''}, {'shipping_date':'bad'}, {'final_batch':'false'}, {'tracking_no':'x'*201}):
            data = self.payload(action='complete', new_batch=True); data.update(bad)
            self.assertEqual(self.post(data).status_code, 400)
        self.assertEqual(self.state()['shipped_batch_count'], 1)
        for route in ('shipping-record', 'shipping-complete'):
            self.as_user('admin-test')
            self.assertEqual(self.client.post('/api/pi/{}/{}'.format(self.pi_id, route), json={'completed':True},
                            headers={'X-CSRFToken':self.csrf}).status_code, 409)

    def test_packing_save_does_not_erase_batch_status(self):
        self.ready(); self.ship(final_batch=True)
        self.as_user('admin-test')
        response = self.client.post('/api/packing-list/{}'.format(self.pi_id), json={'action':'draft', 'boxes':[{'box_no':'1', 'items':[]}]},
                                    headers={'X-CSRFToken':self.csrf})
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertTrue(self.state()['shipping_completed']); self.assertEqual(self.state()['shipped_batch_count'], 1)

    def test_pause_procurement_edit_and_restore_preserves_batches(self):
        self.ready(); self.ship(); self.ship(final_batch=True, tracking_no='FINAL')
        original = self.state()['batches']
        self.as_user('admin-test')
        headers = {'X-CSRFToken': self.csrf}
        confirm_url = '/api/procurement/{}/confirm'.format(self.pi_id)
        pause_url = '/api/procurement/{}/shipping-pause'.format(self.pi_id)
        self.assertEqual(self.client.post(confirm_url + '?action=unconfirm', headers=headers).status_code, 409)
        paused = self.client.post(pause_url, json={'action':'pause', 'version':self.state()['version']}, headers=headers)
        self.assertEqual(paused.status_code, 200, paused.get_json())
        self.assertEqual(self.post(self.payload(action='complete', new_batch=True)).status_code, 400)
        self.assertEqual(self.client.post(confirm_url + '?action=unconfirm', headers=headers).status_code, 200)
        self.assertEqual(self.client.post(confirm_url, headers=headers).status_code, 200)
        restored = self.client.post(pause_url, json={'action':'restore', 'version':self.state()['version']}, headers=headers)
        self.assertEqual(restored.status_code, 200, restored.get_json())
        self.assertTrue(self.state()['shipping_completed'])
        self.assertEqual(self.state()['batches'], original)


if __name__ == '__main__':
    unittest.main()
