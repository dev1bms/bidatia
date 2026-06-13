import uuid
from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone

from core.models import EmailLog
from tools_core.models import ToolEvent, ToolRun
from tools_core.services.lead_service import capture_lead
from tools_core.tasks import send_expiry_reminders

XRAY_RESULT = {'meta': {}, 'analysis': {'findings': [], 'totals': {},
                                        'model_breakdown': []},
               'scoring': {'score': 10}, 'ai_insights': {'language': 'es'}}
DRP_RESULT = {'meta': {'language': 'ar'}, 'risk': {'score': 20, 'level': 'low',
                                                   'categories': [], 'blockers': []}}


def make_run(tool_slug, result_json, email='lead@acme.com', hours_left=12):
    lead = capture_lead(email, source_tool=tool_slug) if email else None
    return ToolRun.objects.create(
        id=uuid.uuid4(), tool_slug=tool_slug, status='done', lead=lead,
        odoo_url='https://x.example.com', odoo_db='x',
        result_json=result_json,
        expires_at=timezone.now() + timedelta(hours=hours_left))


@override_settings(ALLOWED_HOSTS=['testserver'])
class ExpiryReminderTests(TestCase):
    def test_xray_reminder_still_works_in_report_language(self):
        run = make_run('studio_xray', XRAY_RESULT)
        self.assertEqual(send_expiry_reminders(), 1)
        log = EmailLog.objects.get(category='report_expiry_reminder')
        self.assertEqual(log.recipient_email, 'lead@acme.com')
        self.assertEqual(log.metadata['tool_slug'], 'studio_xray')
        self.assertIn(str(run.pk), log.related_id)

    def test_data_risk_reminder_sends_and_tracks(self):
        run = make_run('data_risk', DRP_RESULT)
        self.assertEqual(send_expiry_reminders(), 1)
        log = EmailLog.objects.get(category='report_expiry_reminder')
        self.assertEqual(log.metadata['tool_slug'], 'data_risk')
        self.assertIn('/ar/', log.text_body)  # report link in stored language
        self.assertTrue(ToolEvent.objects.filter(
            tool='data_risk', event='data_risk_expiry_reminder_sent',
            run=run).exists())

    def test_both_tools_in_one_pass(self):
        make_run('studio_xray', XRAY_RESULT, email='a@acme.com')
        make_run('data_risk', DRP_RESULT, email='b@acme.com')
        self.assertEqual(send_expiry_reminders(), 2)

    def test_no_duplicate_reminders(self):
        make_run('data_risk', DRP_RESULT)
        self.assertEqual(send_expiry_reminders(), 1)
        self.assertEqual(send_expiry_reminders(), 0)
        self.assertEqual(
            EmailLog.objects.filter(category='report_expiry_reminder').count(), 1)

    def test_expired_wiped_and_far_future_runs_skipped(self):
        make_run('data_risk', DRP_RESULT, hours_left=-1)      # already expired
        make_run('data_risk', None, email='c@x.com')          # payload wiped
        make_run('data_risk', DRP_RESULT, email='d@x.com',
                 hours_left=60)                               # not yet in window
        self.assertEqual(send_expiry_reminders(), 0)

    def test_demo_and_leadless_runs_skipped(self):
        demo = dict(DRP_RESULT, meta={'demo': True, 'language': 'en'})
        make_run('data_risk', demo)
        make_run('data_risk', DRP_RESULT, email=None)
        self.assertEqual(send_expiry_reminders(), 0)

    def test_booking_intent_skips_reminder(self):
        run = make_run('data_risk', DRP_RESULT)
        ToolEvent.objects.create(tool='data_risk',
                                 event='data_risk_booking_clicked', run=run)
        self.assertEqual(send_expiry_reminders(), 0)
