import json
from pathlib import Path
from unittest import mock

from django.core import mail
from django.test import TestCase, override_settings

from tool_studio_xray.tasks import run_studio_xray
from tools_core.connectors import ConnectionInfo, ConnectorError
from tools_core.models import Lead, ToolRun

FIXTURES = Path(__file__).parent / 'fixtures'

CONNECTOR = 'tool_studio_xray.tasks.OdooXmlRpcConnector'
COLLECT = 'tool_studio_xray.tasks.collect'

INFO = ConnectionInfo(server_version='17.0', edition='enterprise',
                      user_name='Audit', db_name='example')

API_KEY = 'super-secret-key'


def heavy_inventory():
    with open(FIXTURES / 'heavy_studio.json', encoding='utf-8') as f:
        return json.load(f)


def make_run():
    lead = Lead.objects.create(email='cto@example.com', source_tool='studio_xray')
    return ToolRun.objects.create(
        lead=lead, tool_slug='studio_xray',
        odoo_url='https://example.odoo.com', odoo_db='example')


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class RunStudioXrayTaskTests(TestCase):
    def _run(self, run):
        run_studio_xray(str(run.pk), 'https://example.odoo.com', 'example',
                        'audit@example.com', API_KEY)
        run.refresh_from_db()
        return run

    def test_success_path(self):
        run = make_run()
        with mock.patch(CONNECTOR) as connector_cls, \
                mock.patch(COLLECT, return_value=heavy_inventory()):
            connector_cls.return_value.test_connection.return_value = INFO
            run = self._run(run)

        self.assertEqual(run.status, 'done')
        self.assertIsNotNone(run.finished_at)
        self.assertEqual(run.odoo_version, '17.0')

        result = run.result_json
        self.assertEqual(result['scoring']['score'], 100)
        self.assertEqual(result['scoring']['effort_estimate'], '4+ weeks')
        self.assertTrue(result['analysis']['findings'])
        # raw inventory is NOT stored — only analysis/scoring/meta/context
        self.assertNotIn('sections', result)
        self.assertNotIn('inventory', result)
        self.assertLessEqual(len(result['analysis']['model_breakdown']), 15)

        run.lead.refresh_from_db()
        self.assertEqual(run.lead.odoo_version_detected, '17.0')
        self.assertEqual(run.lead.odoo_edition_detected, 'enterprise')

    def test_report_email_sent_with_tokenized_link(self):
        run = make_run()
        with mock.patch(CONNECTOR) as connector_cls, \
                mock.patch(COLLECT, return_value=heavy_inventory()):
            connector_cls.return_value.test_connection.return_value = INFO
            run = self._run(run)

        message = next(m for m in mail.outbox if m.to == ['cto@example.com'])
        self.assertIn('Studio X-Ray', message.subject)
        self.assertIn(f'/tools/studio-xray/report/{run.pk}/', message.body)
        self.assertNotIn(API_KEY, message.body)

    def test_connector_error_marks_failed_with_sanitized_message(self):
        run = make_run()
        with mock.patch(CONNECTOR,
                        side_effect=ConnectorError('Authentication failed — check the database name, login and API key.')):
            run = self._run(run)
        self.assertEqual(run.status, 'failed')
        self.assertIn('Authentication failed', run.error_message)
        self.assertEqual(len(mail.outbox), 0)

    def test_unexpected_error_never_leaks_internals(self):
        run = make_run()
        with mock.patch(CONNECTOR,
                        side_effect=RuntimeError(f'boom with {API_KEY} inside')):
            run = self._run(run)
        self.assertEqual(run.status, 'failed')
        self.assertNotIn(API_KEY, run.error_message)
        self.assertNotIn('boom', run.error_message)

    def test_api_key_never_in_db_after_any_outcome(self):
        run = make_run()
        with mock.patch(CONNECTOR) as connector_cls, \
                mock.patch(COLLECT, return_value=heavy_inventory()):
            connector_cls.return_value.test_connection.return_value = INFO
            run = self._run(run)
        blob = json.dumps(run.result_json) + run.error_message + run.odoo_url + run.odoo_db
        self.assertNotIn(API_KEY, blob)

    def test_missing_run_is_a_noop(self):
        run_studio_xray('00000000-0000-0000-0000-000000000000',
                        'https://x.odoo.com', 'db', 'login', 'key')
        self.assertEqual(ToolRun.objects.count(), 0)

    def test_failed_email_does_not_fail_the_run(self):
        run = make_run()
        with mock.patch(CONNECTOR) as connector_cls, \
                mock.patch(COLLECT, return_value=heavy_inventory()), \
                mock.patch('core.email_service.EmailMultiAlternatives',
                           side_effect=OSError('smtp down')):
            connector_cls.return_value.test_connection.return_value = INFO
            run = self._run(run)
        self.assertEqual(run.status, 'done')
        # The failure is archived instead of disappearing silently.
        from core.models import EmailLog
        self.assertEqual(
            EmailLog.objects.get(category='tool_report').status, 'failed')
