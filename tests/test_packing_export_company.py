from io import BytesIO
from unittest import TestCase
from unittest.mock import patch

from openpyxl import load_workbook
from werkzeug.security import generate_password_hash

import security_smoke as fixture
import packing_list_export
from models import Customer, PackingBatch, PackingBox, PackingItem, PackingList, PI, PIItem, Product, User, db


class PackingExportCompanyTests(TestCase):
    @classmethod
    def setUpClass(cls):
        with fixture.application.app.app_context():
            password = generate_password_hash('StrongPass123!')
            for name in ('packing-sales', 'packing-other'):
                db.session.add(User(account=name, username=name, password_hash=password,
                                    salesperson_name=name, role='salesperson', must_change_password=False))
            customer = Customer(name='Packing buyer', salesperson='packing-sales')
            pi = PI(pi_number='PI-PACK-CO', customer=customer, salesperson='packing-sales',
                    company='qisuo', received_amount=10, shipping_address='PI destination')
            product = Product(name='Packing product')
            item = PIItem(pi=pi, product=product, quantity=3, unit_price=5, amount=15)
            packing = PackingList(pi=pi)
            db.session.add_all([pi, product, item, packing])
            cls.batches = []
            for number in (1, 2):
                batch = PackingBatch(packing_list=packing, batch_no=number,
                                     shipping_address='Batch one destination' if number == 1 else '')
                box = PackingBox(packing_list=packing, shipment_batch=batch,
                                 box_no=str(number), carton_count=number)
                db.session.add(PackingItem(box=box, pi_item=item, product_name=product.name, quantity=1))
                db.session.flush()
                cls.batches.append(batch.id)
            db.session.commit()
            cls.pi_id = pi.id
            cls.url = f'/packing-list/{pi.id}'

    def setUp(self):
        self.login_helper = fixture.SecuritySmokeTests()
        self.login_helper.setUp()
        self.login_helper.login('packing-sales')
        self.client = self.login_helper.client

    def test_a4_export_uses_choice_on_every_batch_and_keeps_order(self):
        for brand, expected_name, address in (
                (None, 'Qisuo', 'Jingchuang'), ('qisuo', 'Qisuo', 'Jingchuang'),
                ('klista', 'KLISTA', 'Jinchuang')):
            with self.subTest(brand=brand):
                query = [('batch', batch) for batch in self.batches]
                if brand:
                    query.append(('company_header', brand))
                response = self.client.get(self.url + '/export.xlsx', query_string=query)
                self.assertEqual(response.status_code, 200)
                workbook = load_workbook(BytesIO(response.data))
                self.assertEqual(len(workbook.worksheets), 2)
                for sheet in workbook:
                    self.assertIn(expected_name, sheet['B4'].value)
                    self.assertIn(address, sheet['B5'].value)
                self.assertEqual([sheet['B7'].value for sheet in workbook],
                                 ['Batch one destination', 'PI destination'])
                workbook.close()
        with fixture.application.app.app_context():
            pi = db.session.get(PI, self.pi_id)
            self.assertEqual((pi.company, pi.shipping_address), ('qisuo', 'PI destination'))

    def test_each_carton_has_selected_company_in_xlsx_and_pdf(self):
        query = {'box': 1, 'batch': self.batches[-1], 'company_header': 'klista'}
        response = self.client.get(self.url + '/compact-100x150.xlsx', query_string=query)
        self.assertEqual(response.status_code, 200)
        workbook = load_workbook(BytesIO(response.data))
        self.assertEqual(len(workbook.worksheets), 2)
        for index, sheet in enumerate(workbook, 1):
            self.assertEqual(sheet['A2'].value, fixture.application.COMPANY_CONFIG['name'])
            self.assertIn(f'{index}/2', sheet['C5'].value)
            self.assertTrue(sheet['A2'].alignment.shrink_to_fit)
        workbook.close()
        with patch.object(packing_list_export, '_draw_compact_text',
                          wraps=packing_list_export._draw_compact_text) as draw_text:
            pdf = self.client.get(self.url + '/compact-100x150.pdf', query_string=query)
        self.assertTrue(pdf.data.startswith(b'%PDF-'))
        drawn = [call[0][-1] for call in draw_text.call_args_list]
        self.assertEqual(drawn.count(fixture.application.COMPANY_CONFIG['name']), 2)

    def test_invalid_selection_and_order_access_on_all_downloads(self):
        for path in ('/export.xlsx', '/export.pdf', '/compact-100x150.xlsx', '/compact-100x150.pdf'):
            for query in ('company_header=unknown', 'company_header=klista&company_header=qisuo'):
                self.assertEqual(self.client.get(self.url + path + '?' + query).status_code, 400)
        self.login_helper.login('packing-other')
        for path in ('/export.xlsx', '/export.pdf', '/compact-100x150.xlsx', '/compact-100x150.pdf'):
            self.assertEqual(self.client.get(self.url + path + '?company_header=klista').status_code, 403)
