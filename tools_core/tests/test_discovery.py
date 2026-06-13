import json
import socket
from unittest import mock

from django.core.cache import cache
from django.test import SimpleTestCase, TestCase, override_settings

from tools_core.connectors import ConnectorError
from tools_core.connectors.discovery import _subdomain_suggestion, detect_databases

PUBLIC = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('203.0.113.10', 0))]
PRIVATE = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('192.168.1.10', 0))]

GETADDRINFO = 'tools_core.connectors.xmlrpc_connector.socket.getaddrinfo'
URLOPEN = 'tools_core.connectors.discovery.urllib.request.urlopen'


def fake_response(payload):
    response = mock.MagicMock()
    response.__enter__.return_value.read.return_value = json.dumps(payload).encode()
    response.__exit__.return_value = False
    return response


class DetectDatabasesTests(SimpleTestCase):
    def test_single_database_from_server_list(self):
        with mock.patch(GETADDRINFO, return_value=PUBLIC), \
                mock.patch(URLOPEN, return_value=fake_response({'result': ['boss-prod']})) as urlopen:
            result = detect_databases('https://erp.example.com')
        self.assertEqual(result, {'databases': ['boss-prod'],
                                  'suggestion': 'boss-prod', 'source': 'server'})
        request = urlopen.call_args[0][0]
        self.assertTrue(request.full_url.endswith('/web/database/list'))

    def test_multiple_databases_no_autofill_suggestion(self):
        with mock.patch(GETADDRINFO, return_value=PUBLIC), \
                mock.patch(URLOPEN, return_value=fake_response({'result': ['a', 'b']})):
            result = detect_databases('https://erp.example.com')
        self.assertEqual(result['databases'], ['a', 'b'])
        self.assertEqual(result['suggestion'], '')
        self.assertEqual(result['source'], 'server')

    def test_blocked_list_falls_back_to_odoo_com_subdomain(self):
        with mock.patch(GETADDRINFO, return_value=PUBLIC), \
                mock.patch(URLOPEN, side_effect=OSError('403')):
            result = detect_databases('https://boss-continental.odoo.com')
        self.assertEqual(result, {'databases': [], 'suggestion': 'boss-continental',
                                  'source': 'heuristic'})

    def test_blocked_list_and_custom_domain_yields_nothing(self):
        with mock.patch(GETADDRINFO, return_value=PUBLIC), \
                mock.patch(URLOPEN, side_effect=OSError('403')):
            result = detect_databases('https://erp.bosscontinental.com')
        self.assertEqual(result['source'], '')
        self.assertEqual(result['suggestion'], '')

    def test_empty_or_malformed_list_falls_back(self):
        for payload in ({'result': []}, {'error': 'denied'}, ['nope']):
            with mock.patch(GETADDRINFO, return_value=PUBLIC), \
                    mock.patch(URLOPEN, return_value=fake_response(payload)):
                result = detect_databases('https://shop.odoo.com')
            self.assertEqual(result['source'], 'heuristic')
            self.assertEqual(result['suggestion'], 'shop')

    def test_ssrf_still_enforced(self):
        with mock.patch(GETADDRINFO, return_value=PRIVATE):
            with self.assertRaises(ConnectorError):
                detect_databases('https://internal.bidatia.xyz')

    def test_subdomain_heuristic_edges(self):
        self.assertEqual(_subdomain_suggestion('mycompany.odoo.com'), 'mycompany')
        self.assertEqual(_subdomain_suggestion('project.odoo.sh'), 'project')
        self.assertEqual(_subdomain_suggestion('www.odoo.com'), '')
        self.assertEqual(_subdomain_suggestion('a.b.odoo.com'), '')   # multi-level
        self.assertEqual(_subdomain_suggestion('odoo.com'), '')
        self.assertEqual(_subdomain_suggestion('erp.example.com'), '')


@override_settings(ALLOWED_HOSTS=['testserver'])
class DetectDatabaseApiTests(TestCase):
    URL = '/en/tools/api/detect-database/'
    DETECT = 'tools_core.views.detect_databases'

    def setUp(self):
        cache.clear()

    def _post(self, payload):
        return self.client.post(self.URL, json.dumps(payload),
                                content_type='application/json')

    def test_get_not_allowed(self):
        self.assertEqual(self.client.get(self.URL).status_code, 405)

    def test_missing_url_rejected(self):
        self.assertEqual(self._post({}).status_code, 400)

    def test_success_shape(self):
        detected = {'databases': ['boss-prod'], 'suggestion': 'boss-prod', 'source': 'server'}
        with mock.patch(self.DETECT, return_value=detected):
            data = self._post({'url': 'https://erp.example.com'}).json()
        self.assertEqual(data, {'ok': True, **detected})

    def test_connector_error_returns_friendly_json(self):
        with mock.patch(self.DETECT,
                        side_effect=ConnectorError('Only https:// Odoo URLs are supported.')):
            data = self._post({'url': 'http://example.com'}).json()
        self.assertFalse(data['ok'])
        self.assertIn('https', data['error'])

    def test_rate_limited(self):
        with mock.patch(self.DETECT, return_value={'databases': [], 'suggestion': '', 'source': ''}):
            for _ in range(15):
                self.assertEqual(self._post({'url': 'https://x.example.com'}).status_code, 200)
            self.assertEqual(self._post({'url': 'https://x.example.com'}).status_code, 429)
