"""Authenticated, isolated checks for the full-page dispatch editor."""
from datetime import datetime
from unittest import TestCase
from unittest.mock import patch
from urllib.parse import parse_qs, urlencode, urlsplit

import security_smoke as fixture
from models import Customer, Expense, PI, ShippingBatch, User, db
from werkzeug.security import generate_password_hash


application = fixture.application


class DispatchPageTests(TestCase):
    @classmethod
    def setUpClass(cls):
        with application.app.app_context():
            password = generate_password_hash('DispatchPageTest123!')
            for username, role, salesperson in (
                    ('dispatch-page-admin', 'admin', ''),
                    ('dispatch-page-owner', 'salesperson', 'Dispatch page owner'),
                    ('dispatch-page-other', 'salesperson', 'Dispatch page other')):
                db.session.add(User(account=username, username=username, password_hash=password,
                                    role=role, salesperson_name=salesperson, must_change_password=False))
            customer = Customer(name='Dispatch page buyer', salesperson='Dispatch page owner')
            cls.pi_number = 'PI-DISPATCH-PAGE'
            pi = PI(pi_number=cls.pi_number, customer=customer, salesperson='Dispatch page owner',
                    currency='USD', total_amount=100, received_amount=0)
            deleted = PI(pi_number='PI-DISPATCH-PAGE-DELETED', customer=customer,
                         salesperson='Dispatch page owner', deleted_at=datetime.utcnow())
            db.session.add_all([pi, deleted])
            db.session.commit()
            cls.pi_id, cls.deleted_pi_id = pi.id, deleted.id

    def setUp(self):
        self.client = application.app.test_client()
        self.path = '/pi/{}/dispatch'.format(self.pi_id)

    def as_user(self, username):
        with application.app.app_context():
            user = User.query.filter_by(username='dispatch-page-' + username).one()
            uid, version = user.id, user.auth_version
        with self.client.session_transaction() as session:
            session['user_id'], session['auth_version'] = uid, version

    def page(self, return_to=None):
        contexts = []
        original = application.render_template

        def render(template, **context):
            if template == 'dispatch_detail.html':
                contexts.append(context)
            return original(template, **context)

        with patch.object(application, 'render_template', side_effect=render):
            response = self.client.get(self.path, query_string=(
                {'return_to': return_to} if return_to is not None else {}))
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        self.assertEqual(len(contexts), 1)
        return response, contexts[0]

    def assert_return(self, context, filters):
        destination = urlsplit(context['return_to'])
        self.assertEqual((destination.scheme, destination.netloc, destination.path), ('', '', '/pi/list'))
        self.assertEqual(destination.fragment, 'pi-row-{}'.format(self.pi_id))
        self.assertEqual(parse_qs(destination.query, keep_blank_values=True), filters)

    def test_anonymous_other_user_missing_and_deleted_orders(self):
        response = self.client.get(self.path)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(urlsplit(response.location).path, '/login')
        self.as_user('other')
        self.assertEqual(self.client.get(self.path).status_code, 403)
        for username in ('owner', 'admin'):
            self.as_user(username)
            self.assertEqual(self.client.get('/pi/999999999/dispatch').status_code, 404)
            self.assertEqual(self.client.get('/pi/{}/dispatch'.format(self.deleted_pi_id)).status_code, 404)

    def test_owner_and_admin_share_editor_without_changing_order(self):
        with application.app.app_context():
            before = (PI.query.count(), Expense.query.count(), ShippingBatch.query.count())
            pi = db.session.get(PI, self.pi_id)
            before_state = (pi.version, pi.shipping_completed, pi.customs_required, pi.freight_forwarder)
        for username in ('owner', 'admin'):
            self.as_user(username)
            response, context = self.page()
            self.assertEqual(context['pi'].id, self.pi_id)
            self.assertIs(context['dispatch_page'], True)
            html = response.get_data(as_text=True)
            self.assertIn(self.pi_number, html)
            for element_id in ('customsModal', 'dispatchForwarderTab', 'dispatchExpensesTab',
                               'dispatchShippingTab', 'dispatchInfoBtn', 'dispatchNextBtn',
                               'shippingSaveBtn', 'shippingBatchHistory'):
                self.assertIn('id="{}"'.format(element_id), html)
            self.assertIn('/static/dispatch.js', html)
            self.assertIn('/static/dispatch.css', html)
            self.assertIn('no-store', response.headers['Cache-Control'])
            self.assert_return(context, {'stage': ['']})
        with application.app.app_context():
            self.assertEqual((PI.query.count(), Expense.query.count(), ShippingBatch.query.count()), before)
            pi = db.session.get(PI, self.pi_id)
            self.assertEqual((pi.version, pi.shipping_completed, pi.customs_required, pi.freight_forwarder), before_state)

    def test_return_preserves_allowed_filters_and_targets_current_order(self):
        self.as_user('owner')
        filters = {'country': ['巴拉圭'], 'customer_name': ['Buyer & Sons'],
                   'salesperson': ['Dispatch page owner'], 'stage': [''],
                   'order_status': ['pending', 'partial'], 'date_from': ['2026-11-01'],
                   'payment_reference': ['1104/01'], 'international_freight': ['yes']}
        source = '/pi/list?' + urlencode(dict(filters, next=['https://invalid.example']), doseq=True) + '#untrusted'
        response, context = self.page(source)
        self.assert_return(context, filters)
        self.assertNotIn('https://invalid.example', response.get_data(as_text=True))

    def test_invalid_return_destinations_fall_back_to_safe_order_link(self):
        self.as_user('owner')
        for destination in ('https://invalid.example/pi/list?country=China',
                            '//invalid.example/pi/list', '/login', '/pi/list/extra',
                            'https://[invalid', '/pi/list?next=https://invalid.example'):
            with self.subTest(destination=destination):
                _, context = self.page(destination)
                self.assert_return(context, {'stage': ['']})

    def test_standalone_page_and_quick_modal_use_same_controls(self):
        self.as_user('owner')
        standalone, _ = self.page('/pi/list?pi_number=' + self.pi_number)
        listing = self.client.get('/pi/list', query_string={'pi_number': self.pi_number})
        self.assertEqual(listing.status_code, 200)
        for response in (standalone, listing):
            html = response.get_data(as_text=True)
            for element_id in ('dispatchForwarderTab', 'dispatchExpensesTab', 'dispatchShippingTab',
                               'customsForwarder', 'expenseHistory', 'shippingBatchHistory'):
                self.assertEqual(html.count('id="{}"'.format(element_id)), 1, element_id)
            self.assertIn('/static/dispatch.js', html)

