"""Mobile web shell checks plus the existing authorization/upload regression suite."""
from test_mobile_photos import MobilePhotosTests


class MobileWebTests(MobilePhotosTests):
    def test_installable_shell_exposes_no_customer_data(self):
        response = self.client.get('/mobile/')
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('/mobile/manifest.webmanifest', html)
        self.assertNotIn('Alice Customer', html)
        self.assertIn('no-store', response.headers['Cache-Control'])
        self.assertIn("frame-ancestors 'none'", response.headers['Content-Security-Policy'])
        manifest = self.client.get('/mobile/manifest.webmanifest')
        self.assertEqual(manifest.mimetype, 'application/manifest+json')
        self.assertEqual(manifest.json['start_url'], '/mobile/')
        for path in ('/static/mobile/mobile.js', '/static/mobile/mobile.css', '/static/mobile/icon.png'):
            self.assertEqual(self.client.get(path).status_code, 200)

    def test_browser_session_has_same_order_permissions(self):
        self.login()
        self.assertEqual(self.client.get('/mobile/').status_code, 200)
        self.assertEqual(self.client.get(f'/api/mobile/orders/{self.other}').status_code, 403)
        self.assertEqual(self.client.get(f'/api/mobile/orders/{self.other}/messages').status_code, 403)
        self.assertEqual(self.client.get(f'/api/mobile/orders/{self.mixed}/photos').status_code, 403)
        self.assertEqual(self.client.post('/api/mobile/logout', headers={'X-CSRFToken': self.csrf}).status_code, 200)
        self.assertEqual(self.client.get(f'/api/mobile/orders/{self.paid}/messages').status_code, 401)
