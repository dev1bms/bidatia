import json
from unittest import mock

from django.core.cache import cache
from django.test import TestCase, override_settings

from tools_core.connectors import ConnectionInfo, ConnectorError

URL = '/en/tools/api/test-connection/'
TEST_CONNECTION = 'tools_core.views.OdooXmlRpcConnector'

VALID_PAYLOAD = {
    'url': 'https://example.odoo.com',
    'database': 'example',
    'login': 'audit@example.com',
    'api_key': 'the-key',
}


@override_settings(ALLOWED_HOSTS=['testserver'])
class TestConnectionApiTests(TestCase):
    def setUp(self):
        cache.clear()

    def _post_json(self, payload):
        return self.client.post(URL, json.dumps(payload), content_type='application/json')

    def test_get_not_allowed(self):
        self.assertEqual(self.client.get(URL).status_code, 405)

    def test_missing_fields_rejected(self):
        resp = self._post_json({'url': 'https://example.odoo.com'})
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(resp.json()['ok'])

    def test_successful_connection(self):
        info = ConnectionInfo(server_version='17.0', edition='enterprise',
                              user_name='Audit User', db_name='example')
        with mock.patch(TEST_CONNECTION) as connector_cls:
            connector_cls.return_value.test_connection.return_value = info
            resp = self._post_json(VALID_PAYLOAD)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {
            'ok': True, 'server_version': '17.0',
            'edition': 'enterprise', 'user_name': 'Audit User',
        })

    def test_form_encoded_payload_also_accepted(self):
        info = ConnectionInfo('17.0', 'community', 'Audit User', 'example')
        with mock.patch(TEST_CONNECTION) as connector_cls:
            connector_cls.return_value.test_connection.return_value = info
            resp = self.client.post(URL, VALID_PAYLOAD)
        self.assertTrue(resp.json()['ok'])

    def test_connector_error_returned_as_friendly_json(self):
        with mock.patch(TEST_CONNECTION, side_effect=ConnectorError('Authentication failed — check the API key.')):
            resp = self._post_json(VALID_PAYLOAD)
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertFalse(body['ok'])
        self.assertIn('Authentication failed', body['error'])

    def test_rate_limited_after_ten_calls(self):
        with mock.patch(TEST_CONNECTION, side_effect=ConnectorError('nope')):
            for _ in range(10):
                self.assertEqual(self._post_json(VALID_PAYLOAD).status_code, 200)
            resp = self._post_json(VALID_PAYLOAD)
        self.assertEqual(resp.status_code, 429)
        self.assertFalse(resp.json()['ok'])

    def test_credentials_never_echoed_in_response(self):
        with mock.patch(TEST_CONNECTION, side_effect=ConnectorError('Could not reach the server.')):
            resp = self._post_json(VALID_PAYLOAD)
        self.assertNotIn('the-key', resp.content.decode())
