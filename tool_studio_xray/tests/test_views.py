from datetime import timedelta
from unittest import mock

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone

from tools_core.models import Lead, ToolRun

LANDING = '/en/tools/studio-xray/'


def _backdate(run, minutes):
    """Push a run's created_at into the past (created_at is auto_now_add, so
    .update() is the only way to set it)."""
    ToolRun.objects.filter(pk=run.pk).update(
        created_at=timezone.now() - timedelta(minutes=minutes))

VALID_POST = {
    'odoo_url': 'https://example.odoo.com',
    'database': 'example',
    'login': 'audit@example.com',
    'api_key': 'secret-key',
    'email': 'cto@example.com',
    'full_name': 'Jane CTO',
    'company': 'Example SL',
    'consent': 'on',
    'website': '',
}

DELAY = 'tool_studio_xray.views.run_studio_xray.delay'


def make_done_run(**overrides):
    payload = {
        'meta': {'server_version': '17.0', 'edition': 'enterprise', 'db_name': 'example'},
        'module_context': {'installed_modules': 80, 'studio_installed': True},
        'analysis': {
            'findings': [
                {'code': 'custom_studio_models', 'severity': 'critical', 'section': 'custom_models',
                 'title': 'Custom models created with Studio', 'detail': 'd', 'count': 2,
                 'examples': ['x_studio_a (5 fields)']},
                {'code': 'computed_studio_fields', 'severity': 'warning', 'section': 'studio_fields',
                 'title': 'Computed or related Studio fields', 'detail': 'd', 'count': 3,
                 'examples': ['sale.order.x_studio_m']},
                {'code': 'automated_actions_present', 'severity': 'info', 'section': 'automated_actions',
                 'title': 'Automated actions configured in the database', 'detail': 'd', 'count': 1,
                 'examples': ['Auto (on_create)']},
            ],
            'totals': {'studio_fields': 12, 'custom_models': 2, 'automated_actions': 1,
                       'studio_views': 4},
            'model_breakdown': [{'model': 'sale.order', 'fields': 5, 'views': 2,
                                 'automations': 1, 'total': 8}],
            'sections_with_errors': [],
        },
        'scoring': {'score': 37, 'raw_points': 92, 'effort_estimate': '4–8 days',
                    'effort_note': 'Indicative estimate — an exact quote requires a code review.',
                    # realistic v1 payload: compute_score always stored these
                    'inputs': {'plain_studio_fields': 20, 'computed_studio_fields': 8,
                               'studio_views': 9, 'automated_actions': 4,
                               'code_server_actions': 2, 'custom_models': 1},
                    'weights': {'plain_studio_fields': 1, 'computed_studio_fields': 3,
                                'studio_views': 2, 'automated_actions': 3,
                                'code_server_actions': 5, 'custom_models': 8}},
    }
    defaults = {
        'tool_slug': 'studio_xray', 'status': 'done',
        'odoo_url': 'https://example.odoo.com', 'odoo_db': 'example',
        'result_json': payload,
    }
    defaults.update(overrides)
    return ToolRun.objects.create(**defaults)


@override_settings(ALLOWED_HOSTS=['testserver'])
class LandingViewTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_landing_renders_form_faq_and_jsonld(self):
        resp = self.client.get(LANDING)
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        self.assertIn('Odoo Studio X-Ray', content)
        self.assertIn('Test Connection', content)
        self.assertIn('application/ld+json', content)
        self.assertIn('FAQPage', content)
        self.assertIn('name="website"', content)  # honeypot

    def test_valid_post_creates_lead_and_run_and_enqueues(self):
        with mock.patch(DELAY) as delay:
            resp = self.client.post(LANDING, VALID_POST)
        run = ToolRun.objects.get()
        lead = Lead.objects.get()
        self.assertRedirects(resp, f'/en/tools/studio-xray/run/{run.pk}/',
                             fetch_redirect_response=False)
        self.assertEqual(lead.email, 'cto@example.com')
        self.assertEqual(lead.source_tool, 'studio_xray')
        self.assertTrue(lead.consent_marketing)
        self.assertIsNotNone(lead.consent_timestamp)
        self.assertEqual(run.lead, lead)
        self.assertEqual(run.odoo_db, 'example')
        self.assertEqual(run.odoo_url, 'https://example.odoo.com')
        # credentials travel as task args only (+ UI language and scan scope)
        delay.assert_called_once_with(
            str(run.pk), 'https://example.odoo.com', 'example',
            'audit@example.com', 'secret-key', 'en', 'studio')

    def test_api_key_never_persisted_anywhere(self):
        with mock.patch(DELAY):
            self.client.post(LANDING, VALID_POST)
        run = ToolRun.objects.get()
        for value in (run.odoo_url, run.odoo_db, run.error_message,
                      str(run.result_json)):
            self.assertNotIn('secret-key', value)

    def test_honeypot_creates_nothing(self):
        with mock.patch(DELAY) as delay:
            resp = self.client.post(LANDING, {**VALID_POST, 'website': 'http://spam'})
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(ToolRun.objects.count(), 0)
        self.assertEqual(Lead.objects.count(), 0)
        delay.assert_not_called()

    def test_missing_consent_rejected(self):
        post = dict(VALID_POST)
        del post['consent']
        with mock.patch(DELAY) as delay:
            resp = self.client.post(LANDING, post)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(ToolRun.objects.count(), 0)
        delay.assert_not_called()

    def test_daily_rate_limit_per_email(self):
        with mock.patch(DELAY):
            for _ in range(3):
                self.client.post(LANDING, VALID_POST)
            resp = self.client.post(LANDING, VALID_POST)
        self.assertEqual(ToolRun.objects.count(), 3)
        self.assertContains(resp, 'daily limit')

    def test_broker_down_marks_run_failed_but_page_survives(self):
        with mock.patch(DELAY, side_effect=OSError('broker down')):
            resp = self.client.post(LANDING, VALID_POST)
        run = ToolRun.objects.get()
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(run.status, 'failed')
        self.assertNotIn('broker', run.error_message)  # internal text not leaked


@override_settings(ALLOWED_HOSTS=['testserver'])
class ProgressAndStatusTests(TestCase):
    def test_progress_page_renders_for_pending_run(self):
        run = ToolRun.objects.create(tool_slug='studio_xray',
                                     odoo_url='https://x.odoo.com', odoo_db='x')
        resp = self.client.get(f'/en/tools/studio-xray/run/{run.pk}/')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Scanning your Odoo')

    def test_progress_redirects_to_report_when_done(self):
        run = make_done_run()
        resp = self.client.get(f'/en/tools/studio-xray/run/{run.pk}/')
        self.assertRedirects(resp, f'/en/tools/studio-xray/report/{run.pk}/',
                             fetch_redirect_response=False)

    def test_status_payload_is_minimal_and_safe(self):
        run = ToolRun.objects.create(tool_slug='studio_xray', status='collecting',
                                     odoo_url='https://x.odoo.com', odoo_db='x')
        data = self.client.get(f'/en/tools/studio-xray/run/{run.pk}/status/').json()
        self.assertEqual(data, {'status': 'collecting', 'step': 1, 'error': ''})

    def test_status_done_includes_report_url(self):
        run = make_done_run()
        data = self.client.get(f'/en/tools/studio-xray/run/{run.pk}/status/').json()
        self.assertEqual(data['status'], 'done')
        self.assertIn(f'/report/{run.pk}/', data['report_url'])

    def test_status_failed_shows_sanitized_error_only(self):
        run = ToolRun.objects.create(
            tool_slug='studio_xray', status='failed',
            odoo_url='https://x.odoo.com', odoo_db='x',
            error_message='Authentication failed — check the database name, login and API key.')
        data = self.client.get(f'/en/tools/studio-xray/run/{run.pk}/status/').json()
        self.assertIn('Authentication failed', data['error'])
        self.assertEqual(set(data), {'status', 'step', 'error'})

    def test_unknown_run_404s(self):
        resp = self.client.get('/en/tools/studio-xray/run/00000000-0000-0000-0000-000000000000/status/')
        self.assertEqual(resp.status_code, 404)

    def test_stale_pending_run_is_marked_failed(self):
        # Never picked up by a worker (queue down) — must fail, not spin forever.
        run = ToolRun.objects.create(tool_slug='studio_xray', status='pending',
                                     odoo_url='https://x.odoo.com', odoo_db='x')
        _backdate(run, 6)  # > STALE_PENDING_AFTER (5 min)
        data = self.client.get(f'/en/tools/studio-xray/run/{run.pk}/status/').json()
        self.assertEqual(data['status'], 'failed')
        self.assertTrue(data['error'])               # a translated, safe message
        self.assertNotIn('Traceback', data['error'])
        run.refresh_from_db()
        self.assertEqual(run.status, 'failed')

    def test_stale_running_run_is_marked_failed(self):
        # Worker died/hung mid-scan: stuck at 'connecting' past the running limit.
        run = ToolRun.objects.create(tool_slug='studio_xray', status='connecting',
                                     odoo_url='https://x.odoo.com', odoo_db='x')
        _backdate(run, 11)  # > STALE_RUNNING_AFTER (10 min)
        data = self.client.get(f'/en/tools/studio-xray/run/{run.pk}/status/').json()
        self.assertEqual(data['status'], 'failed')
        self.assertTrue(data['error'])

    def test_recent_running_run_is_not_failed(self):
        # A genuinely-running scan within the limits must keep going.
        run = ToolRun.objects.create(tool_slug='studio_xray', status='connecting',
                                     odoo_url='https://x.odoo.com', odoo_db='x')
        _backdate(run, 2)
        data = self.client.get(f'/en/tools/studio-xray/run/{run.pk}/status/').json()
        self.assertEqual(data['status'], 'connecting')


@override_settings(ALLOWED_HOSTS=['testserver'])
class DiagnosticVisibilityTests(TestCase):
    """The technical `diagnostic` is shown to staff always, and to everyone only
    when OperationalConfiguration.show_tool_diagnostics is on. Never leaks creds."""

    def _failed_run(self):
        return ToolRun.objects.create(
            tool_slug='studio_xray', status='failed',
            odoo_url='https://x.odoo.com', odoo_db='x',
            error_message='The scan could not finish.',
            diagnostic='ConnectionRefusedError: could not reach host')

    def _set_flag(self, value):
        from django.core.cache import cache
        from site_config.models import OperationalConfiguration
        cfg = OperationalConfiguration.load()
        cfg.show_tool_diagnostics = value
        cfg.save()
        cache.clear()  # config is cached; force a fresh read

    def test_anonymous_does_not_see_diagnostic_by_default(self):
        self._set_flag(False)
        run = self._failed_run()
        data = self.client.get(f'/en/tools/studio-xray/run/{run.pk}/status/').json()
        self.assertNotIn('detail', data)
        # The friendly error is still shown.
        self.assertEqual(data['error'], 'The scan could not finish.')

    def test_flag_on_reveals_diagnostic_to_everyone(self):
        self._set_flag(True)
        run = self._failed_run()
        data = self.client.get(f'/en/tools/studio-xray/run/{run.pk}/status/').json()
        self.assertEqual(data['detail'], 'ConnectionRefusedError: could not reach host')

    def test_staff_always_sees_diagnostic(self):
        from django.contrib.auth import get_user_model
        self._set_flag(False)  # off for the public
        staff = get_user_model().objects.create_user(
            'owner', 'o@x.co', 'pw', is_staff=True)
        self.client.force_login(staff)
        run = self._failed_run()
        data = self.client.get(f'/en/tools/studio-xray/run/{run.pk}/status/').json()
        self.assertEqual(data['detail'], 'ConnectionRefusedError: could not reach host')


class ScrubSecretsTests(TestCase):
    def test_known_credentials_are_redacted(self):
        from tools_core.utils import scrub_secrets
        out = scrub_secrets(
            'OdooError: auth failed for admin@acme with key abc123secretkey',
            'abc123secretkey', 'admin@acme')
        self.assertNotIn('abc123secretkey', out)
        self.assertNotIn('admin@acme', out)
        self.assertIn('OdooError', out)        # the useful type survives
        self.assertIn('***', out)


@override_settings(ALLOWED_HOSTS=['testserver'])
class ReportViewTests(TestCase):
    def test_report_renders_score_findings_and_cta(self):
        run = make_done_run()
        resp = self.client.get(f'/en/tools/studio-xray/report/{run.pk}/')
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        self.assertIn('37', content)                       # score
        self.assertIn('4–8 days', content)                 # effort band
        self.assertIn('Custom models created with Studio', content)
        self.assertIn('Book a free 30-minute review', content)
        self.assertIn('sale.order', content)               # breakdown
        self.assertIn('deleted automatically', content)    # expiry notice

    def test_report_for_unfinished_run_redirects_to_progress(self):
        run = ToolRun.objects.create(tool_slug='studio_xray', status='collecting',
                                     odoo_url='https://x.odoo.com', odoo_db='x')
        resp = self.client.get(f'/en/tools/studio-xray/report/{run.pk}/')
        self.assertRedirects(resp, f'/en/tools/studio-xray/run/{run.pk}/',
                             fetch_redirect_response=False)

    def test_wiped_report_shows_expired_state(self):
        run = make_done_run(result_json=None)
        resp = self.client.get(f'/en/tools/studio-xray/report/{run.pk}/')
        self.assertContains(resp, 'expired')

    @override_settings(TOOLS_BOOKING_URL='https://calendly.com/bidatia/30min')
    def test_external_booking_url_used_when_configured(self):
        run = make_done_run()
        resp = self.client.get(f'/en/tools/studio-xray/report/{run.pk}/')
        self.assertContains(resp, 'https://calendly.com/bidatia/30min')


@override_settings(ALLOWED_HOSTS=['testserver'])
class StalePendingWatchdogTests(TestCase):
    def _pending_run(self, minutes_old):
        from datetime import timedelta
        from django.utils import timezone
        run = ToolRun.objects.create(tool_slug='studio_xray', status='pending',
                                     odoo_url='https://x.odoo.com', odoo_db='x')
        ToolRun.objects.filter(pk=run.pk).update(
            created_at=timezone.now() - timedelta(minutes=minutes_old))
        run.refresh_from_db()
        return run

    def test_stale_pending_run_is_marked_failed_via_status_poll(self):
        run = self._pending_run(minutes_old=6)
        data = self.client.get(f'/en/tools/studio-xray/run/{run.pk}/status/').json()
        self.assertEqual(data['status'], 'failed')
        self.assertIn('queue', data['error'])
        run.refresh_from_db()
        self.assertEqual(run.status, 'failed')
        self.assertIsNotNone(run.finished_at)

    def test_fresh_pending_run_stays_pending(self):
        run = self._pending_run(minutes_old=1)
        data = self.client.get(f'/en/tools/studio-xray/run/{run.pk}/status/').json()
        self.assertEqual(data['status'], 'pending')
        run.refresh_from_db()
        self.assertEqual(run.status, 'pending')

    def test_in_progress_run_within_limit_keeps_running(self):
        # A live scan well under STALE_RUNNING_AFTER must not be touched.
        run = ToolRun.objects.create(tool_slug='studio_xray', status='collecting',
                                     odoo_url='https://x.odoo.com', odoo_db='x')
        ToolRun.objects.filter(pk=run.pk).update(
            created_at=timezone.now() - timedelta(minutes=2))
        data = self.client.get(f'/en/tools/studio-xray/run/{run.pk}/status/').json()
        self.assertEqual(data['status'], 'collecting')

    def test_in_progress_run_stuck_past_limit_is_failed(self):
        # Worker died mid-scan: a run stuck in-progress well past the Celery
        # hard limit must fail, not sit at "Connecting to Odoo" forever.
        run = ToolRun.objects.create(tool_slug='studio_xray', status='collecting',
                                     odoo_url='https://x.odoo.com', odoo_db='x')
        ToolRun.objects.filter(pk=run.pk).update(
            created_at=timezone.now() - timedelta(minutes=30))
        data = self.client.get(f'/en/tools/studio-xray/run/{run.pk}/status/').json()
        self.assertEqual(data['status'], 'failed')
        self.assertTrue(data['error'])


@override_settings(ALLOWED_HOSTS=['testserver'],
                   EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class DemoReportTests(TestCase):
    URL = '/en/tools/studio-xray/demo/'

    def test_demo_creates_once_and_renders_with_badge(self):
        from django.core import mail
        from tool_studio_xray.demo import DEMO_RUN_ID
        from tools_core.models import ToolEvent

        resp = self.client.get(self.URL)
        self.assertRedirects(resp, f'/en/tools/studio-xray/report/{DEMO_RUN_ID}/')
        self.client.get(self.URL)  # idempotent
        self.assertEqual(ToolRun.objects.filter(pk=DEMO_RUN_ID).count(), 1)

        run = ToolRun.objects.get(pk=DEMO_RUN_ID)
        self.assertIsNone(run.lead)                       # never a lead
        self.assertEqual(len(mail.outbox), 0)             # never an email
        self.assertGreater(run.expires_at.year, 2030)     # never expires
        self.assertTrue(ToolEvent.objects.filter(event='demo_report_opened').exists())
        self.assertFalse(ToolEvent.objects.filter(event='xray_report_opened').exists())

        content = self.client.get(
            f'/en/tools/studio-xray/report/{run.pk}/').content.decode()
        self.assertIn('DEMO', content)
        self.assertIn('Aurora Trading', content)          # identity strip
        self.assertIn('System pulse', content)            # v3 blocks render
        self.assertIn('x_air_waybill', content)           # usage tiers
        self.assertIn('Code customizations', content)     # full scope
        self.assertIn('board', content.lower())           # AI card present

    @override_settings(TOOLS_AI_MODEL='gemma4:26b')
    def test_demo_report_has_no_chat(self):
        self.client.get(self.URL)
        from tool_studio_xray.demo import DEMO_RUN_ID
        content = self.client.get(
            f'/en/tools/studio-xray/report/{DEMO_RUN_ID}/').content.decode()
        self.assertNotIn('xrayChat()', content)

    def test_landing_links_to_demo(self):
        content = self.client.get('/en/tools/studio-xray/').content.decode()
        self.assertIn('/en/tools/studio-xray/demo/', content)
