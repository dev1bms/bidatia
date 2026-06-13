"""Internal funnel analytics: track(), the beacon endpoint and the
server-side event call sites across both tools."""
import json
from unittest import mock

from django.core.cache import cache
from django.test import TestCase, override_settings

from tools_core.models import ToolEvent
from tools_core.services.analytics import track


@override_settings(ALLOWED_HOSTS=['testserver'],
                   EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class TrackServiceTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_track_records_event_with_fingerprint(self):
        request = self.client.get('/en/tools/').wsgi_request
        track(request, 'hub', 'tool_page_view', source='test')
        event = ToolEvent.objects.filter(event='tool_page_view', tool='hub').first()
        self.assertIsNotNone(event)
        self.assertEqual(len(event.visitor_key), 16)
        # the GET above also logged its own page view with the SAME key
        keys = set(ToolEvent.objects.values_list('visitor_key', flat=True))
        self.assertEqual(len(keys), 1)

    def test_track_never_raises(self):
        with mock.patch('tools_core.models.ToolEvent.objects.create',
                        side_effect=RuntimeError('db down')):
            track(None, 'hub', 'tool_page_view')  # must not raise

    def test_hub_get_logs_page_view(self):
        self.client.get('/en/tools/')
        self.assertTrue(ToolEvent.objects.filter(
            tool='hub', event='tool_page_view').exists())


@override_settings(ALLOWED_HOSTS=['testserver'])
class BeaconEndpointTests(TestCase):
    URL = '/en/tools/api/track/'

    def setUp(self):
        cache.clear()

    def _post(self, payload):
        return self.client.post(self.URL, json.dumps(payload),
                                content_type='application/json')

    def test_whitelisted_event_recorded(self):
        resp = self._post({'tool': 'erp_rescue', 'event': 'rescue_started'})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(ToolEvent.objects.filter(event='rescue_started').exists())

    def test_unknown_event_rejected(self):
        resp = self._post({'tool': 'erp_rescue', 'event': 'made_up'})
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(ToolEvent.objects.count(), 0)

    def test_rate_limited(self):
        for _ in range(60):
            self._post({'tool': 'erp_rescue', 'event': 'rescue_started'})
        resp = self._post({'tool': 'erp_rescue', 'event': 'rescue_started'})
        self.assertEqual(resp.status_code, 429)


@override_settings(ALLOWED_HOSTS=['testserver'],
                   EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class RescueFunnelEventTests(TestCase):
    def setUp(self):
        cache.clear()

    def _complete(self, **overrides):
        from tool_erp_rescue.tests import ALL_BAD, form_payload
        self.client.post('/en/tools/erp-rescue/',
                         form_payload(ALL_BAD, **overrides))
        from tools_core.models import ToolRun
        return ToolRun.objects.get(tool_slug='erp_rescue')

    def test_completion_and_pain_events(self):
        run = self._complete(pain_text='Manual month-end.')
        completed = ToolEvent.objects.get(event='rescue_completed')
        self.assertEqual(completed.run, run)
        self.assertEqual(completed.email, 'cto@example.com')
        self.assertEqual(completed.metadata['score'], 100)
        self.assertTrue(ToolEvent.objects.filter(
            event='rescue_pain_text_provided', run=run).exists())

    def test_no_pain_event_without_text(self):
        self._complete(pain_text='')
        self.assertFalse(ToolEvent.objects.filter(
            event='rescue_pain_text_provided').exists())

    def test_booking_click_logs_both_events(self):
        run = self._complete()
        self.client.get(f'/en/tools/erp-rescue/result/{run.pk}/book/')
        self.assertTrue(ToolEvent.objects.filter(
            event='rescue_booking_clicked', run=run).exists())
        self.assertTrue(ToolEvent.objects.filter(
            event='booking_started_from_tool', tool='erp_rescue', run=run).exists())

    @override_settings(TOOLS_AI_MODEL='gemma4:26b')
    def test_advisor_completion_event(self):
        from tool_erp_rescue.tasks import generate_advisor_reading
        from tool_erp_rescue.tests import GOOD_ADVICE
        with mock.patch('tool_erp_rescue.views.generate_advisor_reading.delay'):
            run = self._complete()
        with mock.patch('tool_erp_rescue.advisor.ai_service.generate_json',
                        return_value=GOOD_ADVICE):
            generate_advisor_reading(str(run.pk))
        self.assertTrue(ToolEvent.objects.filter(
            event='rescue_advisor_completed', run=run).exists())

    def test_landing_page_view(self):
        self.client.get('/en/tools/erp-rescue/')
        self.assertTrue(ToolEvent.objects.filter(
            tool='erp_rescue', event='tool_page_view').exists())


@override_settings(ALLOWED_HOSTS=['testserver'],
                   EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class XrayFunnelEventTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_started_event_on_run_creation(self):
        with mock.patch('tool_studio_xray.views.run_studio_xray.delay'):
            self.client.post('/en/tools/studio-xray/', {
                'odoo_url': 'https://x.odoo.com', 'database': 'x',
                'login': 'a@x.com', 'api_key': 'k', 'scan_scope': 'full',
                'email': 'lead@example.com', 'consent': 'on',
            })
        event = ToolEvent.objects.get(event='xray_started')
        self.assertEqual(event.metadata['scope'], 'full')
        self.assertEqual(event.email, 'lead@example.com')

    def test_report_open_and_chat_events(self):
        from tool_studio_xray.tests.test_views import make_done_run
        run = make_done_run()
        self.client.get(f'/en/tools/studio-xray/report/{run.pk}/')
        self.assertTrue(ToolEvent.objects.filter(
            event='xray_report_opened', run=run).exists())

        with override_settings(TOOLS_AI_MODEL='gemma4:26b'), \
                mock.patch('tool_studio_xray.views.answer_report_question.delay'):
            self.client.post(
                f'/en/tools/studio-xray/report/{run.pk}/ask/',
                json.dumps({'question': 'What is the most urgent risk?'}),
                content_type='application/json')
        self.assertTrue(ToolEvent.objects.filter(
            event='xray_chat_question_asked', run=run).exists())

    def test_booking_handoff_event(self):
        from tool_studio_xray.tests.test_views import make_done_run
        run = make_done_run()
        self.client.get(f'/en/tools/studio-xray/report/{run.pk}/book/')
        self.assertTrue(ToolEvent.objects.filter(
            event='booking_started_from_tool', tool='studio_xray', run=run).exists())


@override_settings(ALLOWED_HOSTS=['testserver'],
                   EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class ExpiryReminderTests(TestCase):
    def _expiring_run(self, **overrides):
        from datetime import timedelta
        from django.utils import timezone
        from tool_studio_xray.tests.test_views import make_done_run
        from tools_core.models import Lead
        lead = overrides.pop('lead', None) or Lead.objects.create(
            email='cto@example.com', full_name='CTO', source_tool='studio_xray')
        run = make_done_run(lead=lead, **overrides)
        run.expires_at = timezone.now() + timedelta(hours=12)
        run.save(update_fields=['expires_at'])
        return run

    def test_sends_once_per_run(self):
        from core.models import EmailLog
        from tools_core.tasks import send_expiry_reminders
        run = self._expiring_run()
        self.assertEqual(send_expiry_reminders(), 1)
        self.assertEqual(send_expiry_reminders(), 0)   # never repeats
        log = EmailLog.objects.get(category='report_expiry_reminder')
        self.assertEqual(log.related_id, str(run.pk))
        self.assertIn(f'/tools/studio-xray/report/{run.pk}/', log.text_body)

    def test_skips_visitors_who_already_started_booking(self):
        from tools_core.models import ToolEvent
        from tools_core.tasks import send_expiry_reminders
        run = self._expiring_run()
        ToolEvent.objects.create(tool='studio_xray',
                                 event='booking_started_from_tool', run=run)
        self.assertEqual(send_expiry_reminders(), 0)

    def test_skips_far_future_and_demo_runs(self):
        from tools_core.tasks import send_expiry_reminders
        from tool_studio_xray.demo import get_or_create_demo_run
        from datetime import timedelta
        from django.utils import timezone
        far = self._expiring_run()
        far.expires_at = timezone.now() + timedelta(days=2)
        far.save(update_fields=['expires_at'])
        demo = get_or_create_demo_run()
        demo.expires_at = timezone.now() + timedelta(hours=12)
        demo.save(update_fields=['expires_at'])
        self.assertEqual(send_expiry_reminders(), 0)


@override_settings(ALLOWED_HOSTS=['testserver'],
                   EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class FounderWeeklySummaryTests(TestCase):
    def test_summary_email_contains_funnel_counts(self):
        from core.models import EmailLog
        from tools_core.models import Lead, ToolEvent
        from tools_core.tasks import send_founder_weekly_summary
        ToolEvent.objects.create(tool='hub', event='tool_page_view')
        ToolEvent.objects.create(tool='erp_rescue', event='rescue_completed')
        Lead.objects.create(email='w@example.com', source_tool='waitlist_data_risk_profiler')
        Lead.objects.create(email='hot@example.com', company='Acme',
                            source_tool='erp_rescue')

        self.assertEqual(send_founder_weekly_summary(), 'sent')
        log = EmailLog.objects.get(category='founder_weekly')
        self.assertIn('rescue_completed: 1', log.text_body)
        self.assertIn('waitlist signups: 1', log.text_body)
        self.assertIn('hot@example.com (Acme)', log.text_body)


@override_settings(ALLOWED_HOSTS=['testserver'],
                   EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
                   HOT_LEAD_RECIPIENTS=['owner@bidatia.xyz'])
class HotLeadAlertTests(TestCase):
    def setUp(self):
        cache.clear()

    def _rescue(self, **overrides):
        from tool_erp_rescue.tests import ALL_BAD, form_payload
        self.client.post('/en/tools/erp-rescue/',
                         form_payload(ALL_BAD, **overrides))
        from tools_core.models import ToolRun
        return ToolRun.objects.get(tool_slug='erp_rescue')

    def test_high_rescue_score_with_pain_sends_one_alert(self):
        from core.models import EmailLog
        run = self._rescue(pain_text='We cannot close the month.')
        logs = EmailLog.objects.filter(category='hot_lead_alert')
        self.assertEqual(logs.count(), 1)
        body = logs.get().text_body
        self.assertIn('HOT LEAD', logs.get().subject)
        self.assertIn('cto@example.com', body)
        self.assertIn('We cannot close the month.', body)
        self.assertIn(f'/admin/tools_core/toolrun/{run.pk}/change/', body)
        self.assertIn(f'/tools/erp-rescue/result/{run.pk}/', body)
        self.assertEqual(logs.get().recipient_email, 'owner@bidatia.xyz')
        self.assertTrue(ToolEvent.objects.filter(
            event='hot_lead_alert_sent', run=run).exists())

    def test_alert_deduped_per_run_and_reason(self):
        from core.models import EmailLog
        from tools_core.services.hot_leads import alert_hot_lead
        run = self._rescue()
        self.assertEqual(
            EmailLog.objects.filter(category='hot_lead_alert').count(), 1)
        self.assertFalse(alert_hot_lead(run, 'rescue_hot', score=100))
        self.assertEqual(
            EmailLog.objects.filter(category='hot_lead_alert').count(), 1)

    def test_booking_click_is_a_separate_alert(self):
        from core.models import EmailLog
        run = self._rescue()
        self.client.get(f'/en/tools/erp-rescue/result/{run.pk}/book/')
        reasons = set(EmailLog.objects.filter(category='hot_lead_alert')
                      .values_list('metadata__reason', flat=True))
        self.assertEqual(reasons, {'rescue_hot', 'booking_clicked'})

    def test_xray_chat_question_alerts_once(self):
        from core.models import EmailLog
        from tool_studio_xray.tests.test_views import make_done_run
        run = make_done_run()
        with override_settings(TOOLS_AI_MODEL='gemma4:26b'), \
                mock.patch('tool_studio_xray.views.answer_report_question.delay'):
            for q in ('What is the most urgent risk?', 'And the cost side?'):
                self.client.post(
                    f'/en/tools/studio-xray/report/{run.pk}/ask/',
                    json.dumps({'question': q}),
                    content_type='application/json')
        self.assertEqual(EmailLog.objects.filter(
            category='hot_lead_alert', metadata__reason='chat_question').count(), 1)

    def test_demo_then_real_scan_alerts(self):
        from core.models import EmailLog
        self.client.get('/en/tools/studio-xray/demo/')
        with mock.patch('tool_studio_xray.views.run_studio_xray.delay'):
            self.client.post('/en/tools/studio-xray/', {
                'odoo_url': 'https://x.odoo.com', 'database': 'x',
                'login': 'a@x.com', 'api_key': 'k', 'scan_scope': 'studio',
                'email': 'lead@example.com', 'consent': 'on',
            })
        self.assertTrue(EmailLog.objects.filter(
            category='hot_lead_alert', metadata__reason='demo_to_real').exists())

    def test_alert_failure_never_breaks_the_flow(self):
        with mock.patch('core.email_service.EmailMultiAlternatives.send',
                        side_effect=OSError('smtp down')):
            run = self._rescue()           # must not raise
        self.assertEqual(run.status, 'done')


@override_settings(ALLOWED_HOSTS=['testserver'],
                   EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class SendToManagerTests(TestCase):
    def setUp(self):
        cache.clear()

    def _share(self, url, email='boss@example.com'):
        return self.client.post(url, json.dumps({'email': email}),
                                content_type='application/json')

    def test_rescue_share_sends_summary_without_pain_or_internal(self):
        from core.models import EmailLog
        from tool_erp_rescue.tests import ALL_BAD, form_payload
        self.client.post('/en/tools/erp-rescue/', form_payload(
            ALL_BAD, pain_text='SECRET RAW PAIN'))
        from tools_core.models import ToolRun
        run = ToolRun.objects.get(tool_slug='erp_rescue')
        resp = self._share(f'/en/tools/erp-rescue/result/{run.pk}/share/')
        self.assertEqual(resp.json(), {'ok': True})

        log = EmailLog.objects.get(category='report_to_manager')
        self.assertEqual(log.recipient_email, 'boss@example.com')
        self.assertIn('100 / 100', log.text_body)
        self.assertIn(f'/tools/erp-rescue/result/{run.pk}/', log.text_body)
        self.assertIn('Reported pain point', log.text_body)
        self.assertNotIn('SECRET RAW PAIN', log.text_body)   # never the raw text
        self.assertTrue(ToolEvent.objects.filter(
            event='report_sent_to_manager', run=run).exists())

    def test_xray_share_includes_board_summary_and_link(self):
        from core.models import EmailLog
        from tool_studio_xray.tests.test_views import make_done_run
        run = make_done_run()
        run.result_json['ai_insights'] = {
            'board_summary': 'Board view of the findings.',
            'internal_sales_signal': 'NEVER SHOW THIS'}
        run.save(update_fields=['result_json'])
        resp = self._share(f'/en/tools/studio-xray/report/{run.pk}/share/')
        self.assertEqual(resp.json(), {'ok': True})
        body = EmailLog.objects.get(category='report_to_manager').text_body
        self.assertIn('Board view of the findings.', body)
        self.assertIn(f'/tools/studio-xray/report/{run.pk}/', body)
        self.assertNotIn('NEVER SHOW THIS', body)

    def test_invalid_email_and_rate_limit(self):
        from tool_studio_xray.tests.test_views import make_done_run
        run = make_done_run()
        url = f'/en/tools/studio-xray/report/{run.pk}/share/'
        self.assertEqual(self._share(url, 'not-an-email').status_code, 400)
        for _ in range(3):
            self._share(url)
        self.assertEqual(self._share(url).status_code, 429)  # 3 per run per day

    def test_demo_report_cannot_be_shared(self):
        self.client.get('/en/tools/studio-xray/demo/')
        from tool_studio_xray.demo import DEMO_RUN_ID
        resp = self._share(f'/en/tools/studio-xray/report/{DEMO_RUN_ID}/share/')
        self.assertEqual(resp.status_code, 409)

    def test_share_widget_rendered_on_both_pages(self):
        from tool_erp_rescue.tests import ALL_BAD, form_payload
        from tool_studio_xray.tests.test_views import make_done_run
        self.client.post('/en/tools/erp-rescue/', form_payload(ALL_BAD))
        from tools_core.models import ToolRun
        rescue = ToolRun.objects.get(tool_slug='erp_rescue')
        xray = make_done_run()
        for url in (f'/en/tools/erp-rescue/result/{rescue.pk}/',
                    f'/en/tools/studio-xray/report/{xray.pk}/'):
            content = self.client.get(url).content.decode()
            self.assertIn('Send this report to my manager', content)
            self.assertIn('shareReport()', content)
