"""Salesperson account maintenance uses own password and preserves admin boundaries."""
import re
import unittest
import security_smoke as fixture
from models import db, User, Account, AuditLog


class SalesAccountTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture.SecuritySmokeTests.setUpClass()

    def test_salesperson_add_edit_currency_and_admin_boundaries(self):
        application = fixture.application
        client = application.app.test_client()
        with application.app.app_context():
            user = User.query.filter_by(username='alice').one()
            uid, version = user.id, user.auth_version
        with client.session_transaction() as state:
            state['user_id'], state['auth_version'] = uid, version
        page = client.get('/accounts')
        self.assertEqual(page.status_code, 200)
        self.assertIn('收款账户与币种', page.text)
        self.assertIn('href="/accounts"', page.text)
        self.assertNotIn('confirm_value', page.text)
        self.assertEqual(client.get('/field-management').status_code, 403)
        form = client.get('/accounts/add')
        self.assertEqual(form.status_code, 200)
        token = re.search(r'<meta name="csrf-token" content="([^"]+)"', form.text).group(1)
        data = dict(name='Sales EUR Test', brand='klista', currency='EUR',
                    current_password='StrongPass123!', csrf_token=token)
        self.assertEqual(client.post('/accounts/add', data={**data, 'csrf_token': ''}).status_code, 400)
        self.assertEqual(client.post('/accounts/add', data={**data, 'current_password': 'wrong'}).status_code, 403)
        self.assertEqual(client.post('/accounts/add', data={**data, 'currency': 'BAD'}).status_code, 400)
        created = client.post('/accounts/add', data=data)
        self.assertEqual(created.status_code, 302)
        self.assertEqual(client.get(created.location).status_code, 200)
        with application.app.app_context():
            account = Account.query.filter_by(name=data['name']).one()
            account_id = account.id
            self.assertEqual(account.currency, 'EUR')
            self.assertIsNotNone(AuditLog.query.filter_by(entity_type='account', entity_id=account_id, action='create').first())
        path = f'/accounts/{account_id}/edit'
        self.assertEqual(client.get(path).status_code, 200)
        data.update(currency='RMB', name='Sales RMB Test')
        self.assertEqual(client.post(path, data=data).status_code, 302)
        self.assertEqual(client.post(f'/accounts/{account_id}/delete', data=data).status_code, 403)
        self.assertEqual(client.post('/field-options/add', data=data).status_code, 403)
        with application.app.app_context():
            account = db.session.get(Account, account_id)
            self.assertEqual(account.currency, 'RMB')
            self.assertEqual(account.name, 'Sales RMB Test')
            self.assertIsNotNone(AuditLog.query.filter_by(entity_type='account', entity_id=account_id, action='update').first())


if __name__ == '__main__':
    unittest.main()
