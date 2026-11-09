"""Read-only system rate page and upstream failure handling."""
import unittest
from unittest.mock import patch
import security_smoke as fixture
from models import User


class ExchangeRatePageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture.SecuritySmokeTests.setUpClass()

    def test_access_display_and_api_failure(self):
        application = fixture.application
        client = application.app.test_client()
        self.assertEqual(client.get('/exchange-rates').status_code, 302)
        with application.app.app_context():
            user = User.query.filter_by(username='alice').one()
            uid, version = user.id, user.auth_version
        with client.session_transaction() as state:
            state['user_id'], state['auth_version'] = uid, version
        with patch.object(application, '_get_exchange_rate', return_value=6.75), patch('fx_rates.latest_eur_rates') as rates:
            response = client.get('/exchange-rates')
            self.assertEqual(response.status_code, 200)
            self.assertIn('no-store', response.headers['Cache-Control'])
            self.assertIn('1 USD = 6.7500 RMB', response.text)
            self.assertIn('1 USD = 7.0000 RMB', response.text)
            self.assertIn('系统汇率', response.text)
            self.assertIn('参考日期', response.text)
            rates.assert_not_called()  # External latency cannot block page rendering.
        with patch('fx_rates.latest_eur_rates', return_value=dict(eur_usd_rate=1.1, eur_rmb_rate=8.0, fx_reference_date='2026-11-09', fx_source='Frankfurter')):
            self.assertEqual(client.get('/api/exchange-rates/eur').json['eur_usd_rate'], 1.1)
        with patch('fx_rates.latest_eur_rates', side_effect=TimeoutError):
            self.assertEqual(client.get('/api/exchange-rates/eur').status_code, 503)


if __name__ == '__main__':
    unittest.main()
