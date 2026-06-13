import socket
from unittest import mock

from django.core.cache import cache
from django.test import SimpleTestCase, TestCase, override_settings

from tools_core.models import ToolEvent

from . import detector
from .detector import DetectorError, detect

PUBLIC = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('203.0.113.10', 0))]
PRIVATE = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('192.168.1.10', 0))]

GETADDRINFO = 'tools_core.connectors.xmlrpc_connector.socket.getaddrinfo'
FETCH = 'tool_odoo_detector.detector._fetch'
VERSION_PROBE = 'tool_odoo_detector.detector._version_probe'

ODOO_HOME = """
<!DOCTYPE html><html><head>
<meta name="generator" content="Odoo">
<link rel="stylesheet" href="/web/assets/1/web.assets_frontend.min.css">
<script src="/web/assets/1/web.assets_frontend_lazy.min.js"></script>
</head><body>
<div id="wrapwrap"><section class="oe_structure" data-oe-model="ir.ui.view"></section></div>
</body></html>
"""

PLAIN_HOME = """
<!DOCTYPE html><html><head><title>Just a website</title>
<meta name="generator" content="WordPress 6.4">
<link rel="stylesheet" href="/wp-content/themes/x/style.css">
</head><body><p>Hello</p></body></html>
"""

ODOO_LOGIN = '<form class="oe_login_form" action="/web/login"><input name="login"></form>'


class _Headers:
    """Minimal stand-in for http.client.HTTPMessage."""

    def __init__(self, cookies=()):
        self._cookies = list(cookies)

    def get_all(self, name):
        return self._cookies if name == 'Set-Cookie' else None


class DetectorLogicTests(SimpleTestCase):
    def test_odoo_homepage_yields_yes_high(self):
        with mock.patch(GETADDRINFO, return_value=PUBLIC), \
                mock.patch(FETCH, return_value=(ODOO_HOME, _Headers())), \
                mock.patch(VERSION_PROBE, return_value='17.0'):
            result = detect('https://erp.example.com')
        self.assertEqual(result['detected'], 'yes')
        self.assertEqual(result['confidence'], 'high')
        self.assertEqual(result['version'], '17.0')
        self.assertEqual(result['hosting'], 'self_hosted')
        self.assertIn('generator_meta', result['evidence'])
        self.assertIn('asset_bundle', result['evidence'])
        self.assertEqual(result['domain'], 'erp.example.com')

    def test_non_odoo_homepage_yields_no(self):
        with mock.patch(GETADDRINFO, return_value=PUBLIC), \
                mock.patch(FETCH, return_value=(PLAIN_HOME, _Headers())) as fetch:
            result = detect('https://example.com')
        self.assertEqual(result['detected'], 'no')
        self.assertEqual(result['version'], '')
        self.assertEqual(result['hosting'], 'unknown')
        # homepage + login probe — never more than two page fetches
        self.assertLessEqual(fetch.call_count, 2)

    def test_inconclusive_homepage_falls_back_to_login_page(self):
        def fetch_side_effect(url):
            if url.endswith('/web/login'):
                return ODOO_LOGIN, _Headers()
            return PLAIN_HOME, _Headers(['frontend_lang=en_US; Path=/'])

        with mock.patch(GETADDRINFO, return_value=PUBLIC), \
                mock.patch(FETCH, side_effect=fetch_side_effect), \
                mock.patch(VERSION_PROBE, return_value=''):
            result = detect('https://shop.example.com')
        self.assertEqual(result['detected'], 'yes')
        self.assertIn('login_page', result['evidence'])
        self.assertIn('frontend_cookie', result['evidence'])

    def test_odoo_com_host_is_odoo_online(self):
        with mock.patch(GETADDRINFO, return_value=PUBLIC), \
                mock.patch(FETCH, return_value=(ODOO_HOME, _Headers())), \
                mock.patch(VERSION_PROBE, return_value=''):
            result = detect('https://mycompany.odoo.com')
        self.assertEqual(result['detected'], 'yes')
        self.assertEqual(result['hosting'], 'odoo_online')
        self.assertIn('odoo_online_host', result['evidence'])

    def test_unreachable_site_is_unknown_not_error(self):
        with mock.patch(GETADDRINFO, return_value=PUBLIC), \
                mock.patch(FETCH, return_value=(None, None)):
            result = detect('https://down.example.com')
        self.assertEqual(result['detected'], 'unknown')
        self.assertEqual(result['confidence'], 'low')

    def test_private_address_is_blocked(self):
        with mock.patch(GETADDRINFO, return_value=PRIVATE), \
                override_settings(DEBUG=False):
            with self.assertRaises(DetectorError):
                detect('https://intranet.internal')

    def test_invalid_url_is_blocked(self):
        with self.assertRaises(DetectorError):
            detect('not a url at all')

    def test_clean_version(self):
        self.assertEqual(detector._clean_version('17.0+e'), '17.0')
        self.assertEqual(detector._clean_version('saas~16.4'), '')
        self.assertEqual(detector._clean_version(''), '')

    def test_generator_version_extraction(self):
        html = '<meta name="generator" content="Odoo 16.0"/>'
        self.assertEqual(detector._extract_generator_version(html), '16.0')
        self.assertEqual(detector._extract_generator_version(ODOO_HOME), '')


@override_settings(ALLOWED_HOSTS=['testserver'])
class LandingViewTests(TestCase):
    URL = '/en/tools/odoo-detector/'
    DETECT = 'tool_odoo_detector.views.detect'

    RESULT = {
        'detected': 'yes', 'confidence': 'high', 'version': '17.0',
        'hosting': 'odoo_online', 'evidence': ['generator_meta', 'asset_bundle'],
        'domain': 'mycompany.odoo.com',
    }

    def setUp(self):
        cache.clear()

    def test_page_renders_in_all_languages(self):
        for prefix, marker in (('en', 'Is this website running on Odoo?'),
                               ('es', 'Odoo'), ('ar', 'Odoo')):
            response = self.client.get(f'/{prefix}/tools/odoo-detector/')
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, marker)

    def test_page_view_event_recorded(self):
        self.client.get(self.URL)
        self.assertTrue(ToolEvent.objects.filter(
            tool='odoo_detector', event='odoo_detector_page_view').exists())

    def test_successful_check_renders_result_and_tracks(self):
        with mock.patch(self.DETECT, return_value=dict(self.RESULT)):
            response = self.client.post(self.URL, {'url': 'https://mycompany.odoo.com'})
        self.assertContains(response, 'appears to be running on Odoo')
        self.assertContains(response, 'mycompany.odoo.com')
        self.assertContains(response, '17.0')
        events = set(ToolEvent.objects.filter(tool='odoo_detector')
                     .values_list('event', flat=True))
        self.assertIn('odoo_detector_started', events)
        self.assertIn('odoo_detector_completed', events)
        completed = ToolEvent.objects.get(tool='odoo_detector',
                                          event='odoo_detector_completed')
        self.assertEqual(completed.metadata['domain'], 'mycompany.odoo.com')
        self.assertEqual(completed.metadata['detected'], 'yes')

    def test_non_odoo_result_shows_rescue_cta(self):
        result = dict(self.RESULT, detected='no', confidence='medium',
                      version='', hosting='unknown', evidence=[])
        with mock.patch(self.DETECT, return_value=result):
            response = self.client.post(self.URL, {'url': 'https://example.com'})
        self.assertContains(response, "We didn't find Odoo signals")
        self.assertContains(response, 'go/rescue')

    def test_invalid_url_fails_politely(self):
        with mock.patch(self.DETECT, side_effect=DetectorError('bad url')):
            response = self.client.post(self.URL, {'url': 'http://localhost'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'public website addresses')
        self.assertFalse(ToolEvent.objects.filter(
            event='odoo_detector_completed').exists())

    def test_empty_url_fails_politely(self):
        response = self.client.post(self.URL, {'url': '   '})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Please enter a website URL')

    def test_honeypot_redirects_without_detection(self):
        with mock.patch(self.DETECT) as detect_mock:
            response = self.client.post(
                self.URL, {'url': 'https://example.com', 'website': 'spam'})
        self.assertEqual(response.status_code, 302)
        detect_mock.assert_not_called()

    def test_rate_limited_after_ten_checks(self):
        with mock.patch(self.DETECT, return_value=dict(self.RESULT)):
            for _ in range(10):
                self.client.post(self.URL, {'url': 'https://x.example.com'})
            response = self.client.post(self.URL, {'url': 'https://x.example.com'})
        self.assertContains(response, 'Too many checks')


@override_settings(ALLOWED_HOSTS=['testserver'])
class CtaRedirectTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_cta_redirects_track_then_redirect(self):
        cases = [
            ('/en/tools/odoo-detector/go/xray/', 'odoo_detector_xray_clicked',
             '/en/tools/studio-xray/'),
            ('/en/tools/odoo-detector/go/rescue/', 'odoo_detector_rescue_clicked',
             '/en/tools/erp-rescue/'),
            ('/en/tools/odoo-detector/go/demo/', 'odoo_detector_demo_clicked',
             '/en/tools/studio-xray/demo/'),
        ]
        for url, event, target in cases:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 302)
                self.assertEqual(response['Location'], target)
                self.assertTrue(ToolEvent.objects.filter(
                    tool='odoo_detector', event=event).exists())


@override_settings(ALLOWED_HOSTS=['testserver'])
class HubCardTests(TestCase):
    def test_hub_shows_detector_card(self):
        response = self.client.get('/en/tools/')
        self.assertContains(response, 'Odoo Instant Detector')
        self.assertContains(response, '/en/tools/odoo-detector/')
