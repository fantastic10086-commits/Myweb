"""PI charge filtering across legacy invoices, multiple charges and saved queries."""
import unittest
from datetime import datetime
from urllib.parse import parse_qs, urlparse
from unittest.mock import patch

import security_smoke as fixture
from models import db, Expense, PI

app = fixture.application.app


class FreightFilterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture.SecuritySmokeTests.setUpClass()
        with app.app_context():
            common = dict(customer_id=fixture.SecuritySmokeTests.alice_customer, salesperson='Alice',
                          currency='USD', total_amount=100, customs_required=False)
            cases = [
                ('LEGACY', dict(shipping_cost=20, shipping_note='国际运费')),
                ('ENGLISH', dict(shipping_cost=20, shipping_note_en='International Freight')),
                ('MULTIPLE', dict(shipping_cost=0, customer_adjustments=[
                    {'name': '折扣', 'english': 'Discount', 'amount': -20},
                    {'name': '国际运费', 'english': 'International Freight', 'amount': 20},
                ])),
                ('DOMESTIC', dict(shipping_cost=20, shipping_note='国内运费')),
                ('GENERIC', dict(shipping_cost=20, shipping_note='运费')),
                ('ZERO', dict(shipping_cost=0, shipping_note='国际运费')),
                ('REFUND', dict(shipping_cost=-20, shipping_note='国际运费')),
                ('EMPTY', dict(shipping_cost=20, shipping_note='国际运费', customer_adjustments=[])),
                ('EXPENSE', {}),
            ]
            for name, fields in cases:
                pi = PI(pi_number='FREIGHT-' + name, **common, **fields)
                db.session.add(pi)
                db.session.flush()
                if name == 'EXPENSE':
                    db.session.add(Expense(pi_id=pi.id, category='国际运费', amount=100, currency='RMB'))
            for name, fields in [
                ('BOB', dict(salesperson='Bob', customer_id=fixture.SecuritySmokeTests.bob_customer)),
                ('DELETED', dict(salesperson='Alice', customer_id=fixture.SecuritySmokeTests.alice_customer,
                                 deleted_at=datetime.utcnow())),
            ]:
                db.session.add(PI(pi_number='FREIGHT-' + name, shipping_note='国际运费', shipping_cost=20,
                                  currency='USD', total_amount=100, **fields))
            db.session.commit()

    def setUp(self):
        self.helper = fixture.SecuritySmokeTests()
        self.helper.setUp()
        self.helper.login('alice')
        self.client = self.helper.client

    def listing(self, **params):
        rendered = []

        render = fixture.application.render_template

        def capture(template, **context):
            if template == 'pi_list.html':
                rendered.append(context)
            return render(template, **context)

        with patch.object(fixture.application, 'render_template', side_effect=capture):
            response = self.client.get('/pi/list', query_string=dict(pi_number='FREIGHT-', **params))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(rendered), 1)
        return response, rendered[0]

    def test_legacy_multiple_fees_and_totals(self):
        response, context = self.listing(international_freight='yes')
        self.assertEqual({p.pi_number for p in context['pis']},
                         {'FREIGHT-LEGACY', 'FREIGHT-ENGLISH', 'FREIGHT-MULTIPLE'})
        self.assertEqual(context['filtered_totals'], {'USD': 340})
        self.assertIn('id="internationalFreightFilter"', response.text)
        self.assertIn('collapse show', response.text)
        _, context = self.listing(international_freight='no')
        self.assertEqual({p.pi_number for p in context['pis']}, {
            'FREIGHT-DOMESTIC', 'FREIGHT-GENERIC', 'FREIGHT-ZERO',
            'FREIGHT-REFUND', 'FREIGHT-EMPTY', 'FREIGHT-EXPENSE',
        })
        _, context = self.listing(international_freight='yes', stage='customs', customer_name='Alice Customer')
        self.assertEqual(len(context['pis']), 3)
        _, context = self.listing(international_freight='invalid')
        self.assertEqual(len(context['pis']), 9)
        self.helper.login('admin-test')
        _, context = self.listing(international_freight='yes')
        self.assertEqual(len(context['pis']), 4)
        _, context = self.listing(international_freight='yes', salesperson='Bob')
        self.assertEqual([p.pi_number for p in context['pis']], ['FREIGHT-BOB'])

    def test_restore_clear_and_empty_selection(self):
        self.listing(international_freight='no', stage='customs')
        self.client.get('/')
        restored = self.client.get('/pi/list')
        self.assertEqual(restored.status_code, 302)
        params = parse_qs(urlparse(restored.location).query)
        self.assertEqual(params['international_freight'], ['no'])
        self.assertEqual(params['stage'], ['customs'])
        self.listing(international_freight='')
        params = parse_qs(urlparse(self.client.get('/pi/list').location).query, keep_blank_values=True)
        self.assertEqual(params['international_freight'], [''])
        self.client.get('/pi/list?clear_filters=1', follow_redirects=True)
        self.assertEqual(self.client.get('/pi/list').status_code, 200)


if __name__ == '__main__':
    unittest.main()
