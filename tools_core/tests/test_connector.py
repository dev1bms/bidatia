import os
import socket
import unittest
from unittest import mock
from xmlrpc import client as xmlrpc_client

from django.test import SimpleTestCase, override_settings

from tools_core.connectors import ConnectorError, OdooXmlRpcConnector
from tools_core.connectors.xmlrpc_connector import MAX_CALLS_PER_RUN

PUBLIC_ADDRINFO = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('203.0.113.10', 0))]
PRIVATE_ADDRINFO = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('192.168.1.10', 0))]

GETADDRINFO = 'tools_core.connectors.xmlrpc_connector.socket.getaddrinfo'
SERVER_PROXY = 'tools_core.connectors.xmlrpc_connector.xmlrpc_client.ServerProxy'
NO_SLEEP = mock.patch('tools_core.connectors.xmlrpc_connector.CALL_SLEEP_SECONDS', 0)


def make_connector(**overrides):
    kwargs = {
        'url': 'https://example.odoo.com',
        'db': 'example',
        'login': 'audit@example.com',
        'api_key': 'secret-api-key',
    }
    kwargs.update(overrides)
    with mock.patch(GETADDRINFO, return_value=PUBLIC_ADDRINFO):
        return OdooXmlRpcConnector(**kwargs)


class FakeProxies:
    """Patches ServerProxy and routes /common and /object to Mock objects."""

    def __init__(self):
        self.common = mock.Mock()
        self.object = mock.Mock()

    def __call__(self, uri, **kwargs):
        return self.common if uri.endswith('/common') else self.object


class UrlValidationTests(SimpleTestCase):
    def test_https_url_accepted_and_normalized(self):
        connector = make_connector(url='https://example.odoo.com/web/login?x=1')
        self.assertEqual(connector._base_url, 'https://example.odoo.com')

    def test_scheme_added_when_missing(self):
        connector = make_connector(url='example.odoo.com')
        self.assertEqual(connector._base_url, 'https://example.odoo.com')

    def test_http_rejected_outside_debug(self):
        with self.assertRaises(ConnectorError):
            make_connector(url='http://example.odoo.com')

    @override_settings(DEBUG=True)
    def test_http_allowed_for_private_host_in_debug(self):
        with mock.patch(GETADDRINFO, return_value=PRIVATE_ADDRINFO):
            connector = OdooXmlRpcConnector(
                'http://odoo.local:8069', 'db', 'login', 'key')
        self.assertEqual(connector._base_url, 'http://odoo.local:8069')

    @override_settings(DEBUG=True)
    def test_http_rejected_for_public_host_even_in_debug(self):
        with mock.patch(GETADDRINFO, return_value=PUBLIC_ADDRINFO):
            with self.assertRaises(ConnectorError):
                OdooXmlRpcConnector('http://example.odoo.com', 'db', 'login', 'key')

    def test_garbage_url_rejected(self):
        for url in ('', 'ftp://example.com', 'https://'):
            with self.assertRaises(ConnectorError):
                make_connector(url=url)

    def test_missing_credentials_rejected(self):
        for field in ('db', 'login', 'api_key'):
            with self.assertRaises(ConnectorError):
                make_connector(**{field: ''})


class SsrfTests(SimpleTestCase):
    def test_private_ip_rejected(self):
        with mock.patch(GETADDRINFO, return_value=PRIVATE_ADDRINFO):
            with self.assertRaises(ConnectorError) as ctx:
                OdooXmlRpcConnector('https://internal.bidatia.xyz', 'db', 'login', 'key')
        self.assertNotIn('192.168', str(ctx.exception))

    def test_loopback_rejected(self):
        loopback = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('127.0.0.1', 0))]
        with mock.patch(GETADDRINFO, return_value=loopback):
            with self.assertRaises(ConnectorError):
                OdooXmlRpcConnector('https://localhost', 'db', 'login', 'key')

    def test_unresolvable_hostname_rejected(self):
        with mock.patch(GETADDRINFO, side_effect=socket.gaierror):
            with self.assertRaises(ConnectorError) as ctx:
                OdooXmlRpcConnector('https://nope.invalid', 'db', 'login', 'key')
        self.assertIn('resolve', str(ctx.exception))


@NO_SLEEP
class ConnectorBehaviourTests(SimpleTestCase):
    def setUp(self):
        self.proxies = FakeProxies()
        patcher = mock.patch(SERVER_PROXY, side_effect=self.proxies)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.connector = make_connector()

    def test_write_methods_refused(self):
        self.proxies.common.authenticate.return_value = 7
        for method in ('write', 'create', 'unlink', 'execute'):
            with self.assertRaises(ConnectorError):
                self.connector._execute('res.partner', method, [[]])
        self.proxies.object.execute_kw.assert_not_called()

    def test_auth_failure_friendly_message(self):
        self.proxies.common.authenticate.return_value = False
        with self.assertRaises(ConnectorError) as ctx:
            self.connector.search_count('res.partner', [])
        self.assertIn('Authentication failed', str(ctx.exception))

    def test_search_read_caps_limit(self):
        self.proxies.common.authenticate.return_value = 7
        self.proxies.object.execute_kw.return_value = []
        self.connector.search_read('res.partner', [], ['name'], limit=999999)
        kwargs = self.proxies.object.execute_kw.call_args[0][6]
        self.assertEqual(kwargs['limit'], 2000)

    def test_search_read_default_limit(self):
        self.proxies.common.authenticate.return_value = 7
        self.proxies.object.execute_kw.return_value = []
        self.connector.search_read('res.partner', [], ['name'])
        kwargs = self.proxies.object.execute_kw.call_args[0][6]
        self.assertEqual(kwargs['limit'], 2000)

    def test_call_budget_enforced(self):
        self.proxies.common.authenticate.return_value = 7
        self.proxies.object.execute_kw.return_value = 0
        for _ in range(MAX_CALLS_PER_RUN):
            self.connector.search_count('res.partner', [])
        with self.assertRaises(ConnectorError) as ctx:
            self.connector.search_count('res.partner', [])
        self.assertIn('too many requests', str(ctx.exception))

    def test_fault_messages_sanitized(self):
        self.proxies.common.authenticate.return_value = 7
        self.proxies.object.execute_kw.side_effect = xmlrpc_client.Fault(
            1, 'Traceback ... secret-api-key audit@example.com example.odoo.com boom')
        with self.assertRaises(ConnectorError) as ctx:
            self.connector.search_count('res.partner', [])
        message = str(ctx.exception)
        self.assertNotIn('secret-api-key', message)
        self.assertNotIn('audit@example.com', message)
        self.assertNotIn('example.odoo.com', message)

    def test_database_fault_mapped(self):
        self.proxies.common.authenticate.side_effect = xmlrpc_client.Fault(
            1, 'FATAL: database "example" does not exist')
        with self.assertRaises(ConnectorError) as ctx:
            self.connector.search_count('res.partner', [])
        self.assertIn('Database name not found', str(ctx.exception))

    def test_timeout_mapped(self):
        self.proxies.common.authenticate.return_value = 7
        self.proxies.object.execute_kw.side_effect = TimeoutError()
        with self.assertRaises(ConnectorError) as ctx:
            self.connector.search_count('res.partner', [])
        self.assertIn('did not respond', str(ctx.exception))

    def test_protocol_error_mapped(self):
        self.proxies.common.authenticate.side_effect = xmlrpc_client.ProtocolError(
            'example.odoo.com/xmlrpc/2/common', 404, 'Not Found', {})
        with self.assertRaises(ConnectorError) as ctx:
            self.connector.search_count('res.partner', [])
        self.assertIn('HTTP 404', str(ctx.exception))

    def test_test_connection_enterprise_via_version_suffix(self):
        self.proxies.common.version.return_value = {'server_version': '17.0+e'}
        self.proxies.common.authenticate.return_value = 7
        self.proxies.object.execute_kw.return_value = [{'id': 7, 'name': 'Audit User'}]
        info = self.connector.test_connection()
        self.assertEqual(info.server_version, '17.0')
        self.assertEqual(info.edition, 'enterprise')
        self.assertEqual(info.user_name, 'Audit User')
        self.assertEqual(info.db_name, 'example')

    def test_test_connection_community_via_module_check(self):
        self.proxies.common.version.return_value = {'server_version': '16.0'}
        self.proxies.common.authenticate.return_value = 7

        def execute_kw(db, uid, key, model, method, args, kwargs):
            if method == 'search_read':
                return [{'id': 7, 'name': 'Audit User'}]
            return 0  # search_count: no web_enterprise/web_studio installed

        self.proxies.object.execute_kw.side_effect = execute_kw
        info = self.connector.test_connection()
        self.assertEqual(info.edition, 'community')


@unittest.skipUnless(os.environ.get('ODOO_TEST_URL'), 'set ODOO_TEST_URL/DB/LOGIN/KEY to run')
class LiveIntegrationTest(SimpleTestCase):
    """End-to-end check against a real Odoo — opt-in via env vars."""

    def test_live_connection(self):
        connector = OdooXmlRpcConnector(
            os.environ['ODOO_TEST_URL'],
            os.environ['ODOO_TEST_DB'],
            os.environ['ODOO_TEST_LOGIN'],
            os.environ['ODOO_TEST_KEY'],
        )
        info = connector.test_connection()
        self.assertTrue(info.server_version)
        self.assertIn(info.edition, ('enterprise', 'community', ''))
