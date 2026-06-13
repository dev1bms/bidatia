from datetime import timedelta

from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from tools_core.models import ToolRun
from tools_core.tasks import ping, wipe_expired_tool_results


def make_run(expired, payload):
    run = ToolRun.objects.create(
        tool_slug='studio_xray',
        odoo_url='https://example.odoo.com',
        odoo_db='example',
        status='done',
        result_json=payload,
        error_message='kept',
        odoo_version='17.0',
    )
    if expired:
        # expires_at has a default; push it into the past explicitly.
        ToolRun.objects.filter(pk=run.pk).update(
            expires_at=timezone.now() - timedelta(hours=1))
        run.refresh_from_db()
    return run


class WipeExpiredToolResultsTests(TestCase):
    def test_wipes_only_expired_runs_with_payloads(self):
        expired_with_payload = make_run(expired=True, payload={'score': 42})
        expired_without_payload = make_run(expired=True, payload=None)
        fresh_with_payload = make_run(expired=False, payload={'score': 7})

        wiped = wipe_expired_tool_results()

        self.assertEqual(wiped, 1)
        expired_with_payload.refresh_from_db()
        fresh_with_payload.refresh_from_db()
        self.assertIsNone(expired_with_payload.result_json)
        self.assertEqual(fresh_with_payload.result_json, {'score': 7})
        # Row + metadata survive the wipe — only the payload goes.
        self.assertEqual(expired_with_payload.status, 'done')
        self.assertEqual(expired_with_payload.odoo_version, '17.0')
        self.assertEqual(expired_with_payload.error_message, 'kept')
        self.assertEqual(ToolRun.objects.count(), 3)
        self.assertIsNotNone(expired_without_payload.pk)

    def test_noop_when_nothing_expired(self):
        make_run(expired=False, payload={'score': 7})
        self.assertEqual(wipe_expired_tool_results(), 0)


class CeleryWiringTests(SimpleTestCase):
    def test_celery_app_imports_and_discovers_tasks(self):
        from bidatia import celery_app

        self.assertEqual(ping.name, 'tools_core.tasks.ping')
        self.assertEqual(
            wipe_expired_tool_results.name, 'tools_core.tasks.wipe_expired_tool_results')
        self.assertEqual(celery_app.main, 'bidatia')

    def test_safety_settings_active(self):
        from bidatia import celery_app

        # No result backend usage: args/kwargs/results never persisted.
        self.assertTrue(celery_app.conf.task_ignore_result)
        self.assertFalse(celery_app.conf.result_extended)
        self.assertEqual(celery_app.conf.task_time_limit, 420)
        self.assertEqual(celery_app.conf.task_soft_time_limit, 360)

    def test_beat_schedule_contains_cleanup(self):
        from bidatia import celery_app

        entry = celery_app.conf.beat_schedule['wipe-expired-tool-results']
        self.assertEqual(entry['task'], 'tools_core.tasks.wipe_expired_tool_results')

    def test_ping_returns_pong(self):
        self.assertEqual(ping(), 'pong')
