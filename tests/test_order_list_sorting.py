"""Authenticated operational-list ordering, against a disposable database."""
import unittest
from datetime import date, datetime, timedelta
from urllib.parse import parse_qs, urlparse
from unittest.mock import patch

import security_smoke as fixture
from models import db, PI, User, UserListPreference

application = fixture.application


class OrderListSortingTests(unittest.TestCase):
    paths = ('/pi/list', '/procurement', '/packing-lists')

    @classmethod
    def setUpClass(cls):
        fixture.SecuritySmokeTests.setUpClass()
        cls.ids = {}
        cls.updates = {}
        with application.app.app_context():
            # This unrelated fixture must not displace the five synthetic orders
            # from the dashboard's latest-five window.
            db.session.execute(PI.__table__.update().values(
                created_at=datetime(2026, 1, 1), updated_at=datetime(2026, 1, 1)))
            # Amount order in RMB: 005=1050, 003=975, 001=900, 004=850, 002=800.
            # 001 is the oldest created PI, but has the newest business update.
            cases = [
                ('001', 'Alice', 'RMB', 900, 0, 6.5),
                ('002', 'Alice', 'EUR', 100, 0, 6.5),
                ('003', 'Alice', 'USD', 100, 50, 6.5),
                ('004', 'Alice', 'RMB', 1000, -150, 6.5),
                ('005', 'Bob', 'USD', 150, 0, 7.0),
            ]
            for index, (suffix, salesperson, currency, amount, charge, rate) in enumerate(cases):
                stamp = datetime(2026, 11, 24 - index, 23, 15)
                pi = PI(pi_number='PI-SORT-' + suffix,
                        customer_id=(fixture.SecuritySmokeTests.alice_customer if salesperson == 'Alice'
                                     else fixture.SecuritySmokeTests.bob_customer),
                        salesperson=salesperson, currency=currency, total_amount=amount,
                        shipping_cost=charge, exchange_rate=rate, eur_usd_rate=1.1, eur_rmb_rate=8,
                        received_amount=1, issue_date=date(2026, 11, index + 1),
                        created_at=datetime(2026, 1, index + 1), updated_at=stamp)
                db.session.add(pi)
                db.session.flush()
                cls.ids[suffix] = pi.id
                cls.updates[suffix] = stamp
            db.session.commit()

    def setUp(self):
        self.client = application.app.test_client()
        with application.app.app_context():
            db.session.query(UserListPreference).delete()
            db.session.commit()
        self.signin('admin-test')

    def signin(self, username):
        with application.app.app_context():
            user = User.query.filter_by(username=username).one()
            user_id, version = user.id, user.auth_version
        with self.client.session_transaction() as session:
            session.clear()
            session.update(user_id=user_id, auth_version=version)

    def page(self, path, params=None):
        captured = {}

        render = application.render_template

        def receive(template, **context):
            for key in ('pis', 'recent_pis'):
                if key in context:
                    captured[key] = [pi.pi_number for pi in context[key]]
            for key in ('sort_key', 'sort_direction', 'sort_urls', 'order_updated_at'):
                if key in context:
                    captured[key] = context[key]
            return render(template, **context)

        with patch.object(application, 'render_template', side_effect=receive):
            response = self.client.get(path, query_string=params)
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True)[:500])
        return captured, response.get_data(as_text=True)

    def expected(self, *suffixes):
        return ['PI-SORT-' + suffix for suffix in suffixes]

    def test_default_latest_update_and_beijing_display_across_lists(self):
        for path in self.paths:
            with self.subTest(path=path):
                context, html = self.page(path, {'pi_number': 'PI-SORT-'})
                self.assertEqual(context['pis'], self.expected('001', '002', '003', '004', '005'))
                self.assertEqual((context['sort_key'], context['sort_direction']), ('updated_at', 'desc'))
                self.assertEqual(context['order_updated_at'][self.ids['001']],
                                 self.updates['001'] + timedelta(hours=8))
                self.assertIn('最近更新日期', html)
                self.assertIn('2026-11-25', html)
                self.assertIn('07:15', html)
                self.assertIn('开单日期：2026-11-01', html)

    def test_number_and_update_direction_and_header_toggle(self):
        for path in self.paths:
            for key, direction, suffixes in (
                    ('pi_number', 'asc', ('001', '002', '003', '004', '005')),
                    ('pi_number', 'desc', ('005', '004', '003', '002', '001')),
                    ('updated_at', 'asc', ('005', '004', '003', '002', '001'))):
                with self.subTest(path=path, key=key, direction=direction):
                    context, html = self.page(path, dict(pi_number='PI-SORT-', sort=key, direction=direction))
                    self.assertEqual(context['pis'], self.expected(*suffixes))
                    toggle = parse_qs(urlparse(context['sort_urls'][key]).query)
                    self.assertEqual(toggle['direction'], ['desc' if direction == 'asc' else 'asc'])
                    self.assertEqual(toggle['pi_number'], ['PI-SORT-'])
                    self.assertIn('aria-sort="' + ('ascending' if direction == 'asc' else 'descending') + '"', html)

    def test_amount_uses_saved_business_rates_and_total_including_adjustments(self):
        for path in ('/pi/list', '/procurement'):
            for direction, suffixes in (
                    ('desc', ('005', '003', '001', '004', '002')),
                    ('asc', ('002', '004', '001', '003', '005'))):
                with self.subTest(path=path, direction=direction):
                    context, html = self.page(path, dict(pi_number='PI-SORT-', sort='amount', direction=direction))
                    self.assertEqual(context['pis'], self.expected(*suffixes))
                    self.assertIn('按各 PI 保存的业务汇率折合人民币比较', html)

    def test_invalid_parameters_fall_back_without_changing_filters(self):
        for path in self.paths:
            context, _ = self.page(path, dict(pi_number='PI-SORT-', sort='untrusted_column', direction='asc'))
            self.assertEqual((context['sort_key'], context['sort_direction']), ('updated_at', 'desc'))
            self.assertEqual(context['pis'][0], 'PI-SORT-001')
            context, _ = self.page(path, dict(pi_number='PI-SORT-', sort='pi_number', direction='sideways'))
            self.assertEqual((context['sort_key'], context['sort_direction']), ('pi_number', 'desc'))
        context, _ = self.page('/packing-lists', dict(pi_number='PI-SORT-', sort='amount'))
        self.assertEqual(context['sort_key'], 'updated_at')
        self.assertNotIn('amount', context['sort_urls'])

    def test_sort_links_keep_multiselect_and_date_filters(self):
        params = {'pi_number': 'PI-SORT-', 'order_status': ['pending', 'partial'],
                  'salesperson': 'Alice', 'date_from': '2026-11-01', 'date_to': '2026-11-04',
                  'sort': 'amount', 'direction': 'asc'}
        context, html = self.page('/procurement', params)
        for link in context['sort_urls'].values():
            query = parse_qs(urlparse(link).query)
            for key in ('pi_number', 'order_status', 'salesperson', 'date_from', 'date_to'):
                self.assertEqual(query[key], params[key] if isinstance(params[key], list) else [params[key]])
        self.assertIn('name="sort" value="amount"', html)
        self.assertIn('name="direction" value="asc"', html)
        # Date filters still mean issue date, not the newly displayed update date.
        for path in self.paths:
            context, _ = self.page(path, dict(pi_number='PI-SORT-', date_from='2026-11-01', date_to='2026-11-01'))
            self.assertEqual(context['pis'], self.expected('001'))

    def test_sort_and_filters_are_restored_and_clear_resets_default(self):
        for path in self.paths:
            with self.subTest(path=path):
                self.page(path, dict(pi_number='PI-SORT-', sort='pi_number', direction='asc'))
                restored = self.client.get(path)
                self.assertEqual(restored.status_code, 302)
                query = parse_qs(urlparse(restored.location).query)
                self.assertEqual(query, {'pi_number': ['PI-SORT-'], 'sort': ['pi_number'], 'direction': ['asc']})
                self.assertEqual(self.client.get(path + '?clear_filters=1', follow_redirects=True).status_code, 200)
                context, _ = self.page(path)
                self.assertEqual((context['sort_key'], context['sort_direction']), ('updated_at', 'desc'))
                if path == '/pi/list':
                    self.assertIn('PI-TEST-001', context['pis'])

    def test_salesperson_sorting_does_not_expand_visibility(self):
        self.signin('alice')
        for path in ('/pi/list', '/packing-lists'):
            context, _ = self.page(path, dict(pi_number='PI-SORT-', sort='pi_number', direction='desc', salesperson='Bob'))
            self.assertNotIn('PI-SORT-005', context['pis'])
            # Explicit Bob filter may narrow Alice's results to empty; it must
            # never grant visibility to another salesperson's orders.
            context, _ = self.page(path, dict(pi_number='PI-SORT-', sort='pi_number', direction='desc'))
            self.assertEqual(context['pis'], self.expected('004', '003', '002', '001'))
        self.assertIn(self.client.get('/procurement?sort=pi_number').status_code, (302, 403))

    def test_dashboard_recent_orders_uses_same_effective_update_time(self):
        context, html = self.page('/')
        self.assertEqual(context['recent_pis'], self.expected('001', '002', '003', '004', '005'))
        self.assertEqual(context['order_updated_at'][self.ids['001']], self.updates['001'] + timedelta(hours=8))
        self.assertIn('最近更新日期', html)


if __name__ == '__main__':
    unittest.main()
