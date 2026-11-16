"""Verify editable order download names against the public export routes."""
from io import BytesIO
from unittest import TestCase
from zipfile import ZipFile

from openpyxl import load_workbook
from werkzeug.http import parse_options_header

import security_smoke as fixture
import export_filenames as names
from models import (db, PI, PIItem, Supplier, ExportFilenameSettings,
                    CustomerFile, PackingList, PackingBatch)


class ExportFilenameTests(TestCase):
    @classmethod
    def setUpClass(cls):
        fixture.SecuritySmokeTests.setUpClass()

    def setUp(self):
        self.h = fixture.SecuritySmokeTests()
        self.h.setUp()
        self.h.login('admin-test')
        self.client = self.h.client
        self.url = '/document-templates/filenames'
        self.pi = f'/pi/{self.h.alice_pi}'
        self.form = {'csrf_token': self.h.token(self.url), 'version': '0',
                     'omit_prefix': '1', 'current_password': 'AdminPass123!'}
        with fixture.application.app.app_context():
            ExportFilenameSettings.query.delete()
            db.session.commit()

    def filename(self, response):
        self.assertEqual(response.status_code, 200)
        return parse_options_header(response.headers['Content-Disposition'])[1]['filename']

    def test_admin_preview_save_conflict_and_pi_downloads(self):
        form = dict(self.form, **{'rule_system-default': '{客户名称}_{PI编号}_订单'})
        self.assertIn('20261023-008_', self.client.get(self.url).get_data(as_text=True))
        preview = self.client.post(self.url, data=dict(form, action='preview')).get_json()
        self.assertEqual(preview['previews']['system-default'], '示例客户_20261023-008_订单.pdf')
        self.assertEqual(preview['errors'], {})
        invalid = self.client.post(self.url, data=dict(form, **{'rule_customs': '{供应商}'}))
        self.assertIn('不支持字段', invalid.get_data(as_text=True))
        wrong = self.client.post(self.url, data=dict(form, current_password='wrong'))
        self.assertIn('密码不正确', wrong.get_data(as_text=True))
        self.assertEqual(self.client.post(self.url, data=form).status_code, 302)
        self.client.post(self.url, data=dict(form, omit_prefix='0'))
        with fixture.application.app.app_context():
            self.assertTrue(names.settings().omit_pi_prefix)
            pi = db.session.get(PI, self.h.alice_pi)
            item = pi.items[0]
            fields = {f'qty_{item.id}': item.quantity, f'price_{item.id}': item.unit_price}
        self.h.login('alice')
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.client.post(self.url, data={'csrf_token':self.h.token('/')}).status_code, 403)
        direct = self.client.get(self.pi + '/excel')
        self.assertEqual(self.filename(direct), 'Alice Customer_TEST-001_订单.xlsx')
        direct.close()
        with fixture.application.app.app_context():
            archived = CustomerFile.query.filter_by(pi_id=self.h.alice_pi, note='PI Excel').one()
            self.assertEqual(archived.original_name, 'Alice Customer_TEST-001_订单.xlsx')
        export = self.client.post(self.pi + '/export', data=dict(fields, mode='download',
            output_format='xlsx', csrf_token=self.h.token(self.pi + '/export')))
        self.assertEqual(self.filename(export), 'Alice Customer_TEST-001_订单.xlsx')
        workbook = load_workbook(BytesIO(export.data), read_only=True)
        self.assertTrue(any('PI-TEST-001' in str(cell) for row in workbook.active.values for cell in row))
        workbook.close()
        export.close()
        self.h.login('admin-test')
        self.client.post(self.url, data=dict(form, csrf_token=self.h.token(self.url), version='1', omit_prefix='0'))
        direct = self.client.get(self.pi + '/excel')
        self.assertEqual(self.filename(direct), 'Alice Customer_PI-TEST-001_订单.xlsx')
        direct.close()

    def test_contract_and_packing_names(self):
        with fixture.application.app.app_context():
            pi = db.session.get(PI, self.h.alice_pi)
            pi.received_amount = 1
            first = pi.items[0]
            second = PIItem(pi_id=pi.id, product_id=first.product_id, quantity=1, unit_price=5, amount=5)
            suppliers = [Supplier(name='同名/示例'), Supplier(name='同名:示例')]
            packing = PackingList(pi=pi)
            db.session.add_all([second, packing, PackingBatch(packing_list=packing,batch_no=1)] + suppliers)
            db.session.commit()
            rows = [{'pi_item_id':item.id,'supplier_id':supplier.id,'quantity':1,'unit_price':5}
                    for item, supplier in zip((first, second),suppliers)]
        self.client.post(self.url, data=dict(self.form, **{'rule_packing-a4':'第{批次}批_{PI编号}'}))
        packed = self.client.get(f'/packing-list/{self.h.alice_pi}/export.xlsx')
        self.assertEqual(self.filename(packed), '第1批_TEST-001-DRAFT.xlsx')
        url = f'/procurement/{self.h.alice_pi}/supplier-orders/export'
        headers = {'X-CSRFToken': self.h.token('/')}
        payload = {'document_type':'contract','items':rows}
        bulk = self.client.post(url, json=payload, headers=headers)
        self.assertEqual(self.filename(bulk), 'TEST-001_采购合同_全部供应商.zip')
        with ZipFile(BytesIO(bulk.data)) as bundle:
            files = bundle.namelist()
            self.assertEqual(len(set(files)), 2)
            for name in files:
                workbook = load_workbook(BytesIO(bundle.read(name)), read_only=True)
                self.assertIn('PI-TEST-001', workbook.active['C4'].value)
                workbook.close()
        single = self.client.post(url, json=dict(payload,supplier_id=rows[1]['supplier_id']),headers=headers)
        self.assertIn(self.filename(single), files)
        with fixture.application.app.app_context():
            archived = CustomerFile.query.filter_by(pi_id=self.h.alice_pi,note='采购合同').all()
            self.assertEqual({record.original_name for record in archived}, set(files))

    def test_unicode_and_filename_boundaries(self):
        values = {'PI编号':'PI-20261023-008','客户名称':'客户/甲','模板名称':'进出口贸易合同'}
        self.assertEqual(names.render_name('{PI编号}_{模板名称}', True, values, 'xlsx'),
                         '20261023-008_进出口贸易合同.xlsx')
        self.assertEqual(names.render_name('{客户名称}', True, values, 'pdf'), '客户_甲.pdf')
        self.assertEqual(names.safe_filename('CON', 'pdf'), '_CON.pdf')
        long_name = names.safe_filename('测'*180, 'xlsx', '-DRAFT')
        self.assertTrue(long_name.endswith('-DRAFT.xlsx'))
        self.assertLessEqual(len(long_name.encode('utf-8')), 240)
        cartons = '-Cartons-' + '-'.join(str(i) for i in range(100))
        many_boxes = names.safe_filename('测' * 180, 'pdf', cartons + '-DRAFT')
        self.assertTrue(many_boxes.endswith('-DRAFT.pdf'))
        self.assertLessEqual(len(many_boxes.encode()), 240)
        for invalid in ('{客户名称', '{未知}', '{{PI编号}}', '{PI编号}.pdf', '目录/单据', '..'):
            with self.subTest(rule=invalid), self.assertRaises(ValueError):
                names.validate_pattern(invalid, ())
