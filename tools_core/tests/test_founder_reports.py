import uuid
from datetime import datetime, timedelta, timezone as dt_timezone

from django.conf import settings
from django.test import TestCase, override_settings
from django.utils import timezone

from core.models import EmailLog
from tools_core.models import Lead, ToolEvent, ToolRun
from tools_core.services.founder_reports import (
    build_daily_report,
    build_monthly_report,
    previous_month_bounds,
)
from tools_core.tasks import (
    send_founder_daily_report,
    send_founder_monthly_report,
    send_founder_weekly_summary,
)


def make_event(event, tool='studio_xray', created_at=None):
    row = ToolEvent.objects.create(tool=tool, event=event)
    if created_at:
        ToolEvent.objects.filter(pk=row.pk).update(created_at=created_at)
    return row


def make_run(tool_slug='studio_xray', status='done', result_json=None,
             created_at=None, lead=None, error=''):
    run = ToolRun.objects.create(
        id=uuid.uuid4(), tool_slug=tool_slug, status=status, lead=lead,
        odoo_url='https://x.example.com', odoo_db='x',
        result_json=result_json, error_message=error)
    if created_at:
        ToolRun.objects.filter(pk=run.pk).update(created_at=created_at)
        run.refresh_from_db()
    return run


class DailyReportBuilderTests(TestCase):
    def test_counts_only_last_24_hours(self):
        now = timezone.now()
        make_event('tool_page_view', created_at=now - timedelta(hours=2))
        make_event('tool_page_view', created_at=now - timedelta(hours=30))
        report = build_daily_report(now)
        rows = dict(report['rows'])
        self.assertEqual(rows['Tool page views (24h)'], '1')
        self.assertEqual(report['period_key'],
                         'founder_daily_summary:%s' % now.date().isoformat())

    def test_mixed_tools_and_failed_runs_included(self):
        now = timezone.now()
        make_event('xray_started', created_at=now - timedelta(hours=1))
        make_event('xray_completed', created_at=now - timedelta(hours=1))
        make_event('data_risk_started', tool='data_risk',
                   created_at=now - timedelta(hours=1))
        make_run(status='failed', error='Authentication failed — check the key.',
                 created_at=now - timedelta(hours=3))
        make_run(result_json={'scoring': {'score': 88}},
                 created_at=now - timedelta(hours=2))
        report = build_daily_report(now)
        rows = dict(report['rows'])
        self.assertEqual(rows['Studio X-Ray'], '1 started · 1 completed')
        self.assertEqual(rows['Data Risk Profiler'], '1 started · 0 completed')
        self.assertIn('1 failed', rows['Runs (24h)'])
        text = ' '.join(report['paragraphs'])
        self.assertIn('Authentication failed', text)
        self.assertIn('studio_xray 88/100', text)

    def test_quiet_day_still_builds(self):
        report = build_daily_report(timezone.now())
        self.assertTrue(report['rows'])
        self.assertTrue(report['paragraphs'])
        self.assertIsNone(report['panel'])

    def test_admin_links_in_footnotes(self):
        report = build_daily_report(timezone.now())
        text = ' '.join(report['footnotes'])
        for fragment in ('/admin/tools_core/toolevent/',
                         '/admin/tools_core/toolrun/',
                         '/admin/core/emaillog/'):
            self.assertIn(fragment, text)


class MonthlyReportBuilderTests(TestCase):
    def test_previous_month_bounds(self):
        from datetime import date
        start, end, first_prev = previous_month_bounds(date(2026, 7, 1))
        self.assertEqual(start.date().isoformat(), '2026-06-01')
        self.assertEqual(end.date().isoformat(), '2026-07-01')
        self.assertEqual(first_prev.isoformat(), '2026-06-01')
        # January rolls back across the year boundary
        start, _end, first_prev = previous_month_bounds(date(2026, 1, 15))
        self.assertEqual(first_prev.isoformat(), '2025-12-01')

    def test_counts_previous_month_only(self):
        from datetime import date
        today = date(2026, 6, 13)
        inside = datetime(2026, 5, 31, 23, 0, tzinfo=dt_timezone.utc)
        before = datetime(2026, 4, 30, 12, 0, tzinfo=dt_timezone.utc)
        this_month = datetime(2026, 6, 1, 0, 5, tzinfo=dt_timezone.utc)
        for created in (inside, before, this_month):
            make_event('tool_page_view', created_at=created)
        report = build_monthly_report(today)
        rows = dict(report['rows'])
        self.assertEqual(rows['Total tool page views'], '1')
        self.assertEqual(report['period_key'], 'founder_monthly_summary:2026-05')
        self.assertIn('May 2026', report['subject'])

    def test_funnel_conversions_and_recommendations(self):
        from datetime import date
        when = datetime(2026, 5, 10, tzinfo=dt_timezone.utc)
        for _ in range(60):
            make_event('tool_page_view', created_at=when)
        for _ in range(12):
            make_event('xray_started', created_at=when)
        for _ in range(4):
            make_event('xray_completed', created_at=when)
        for _ in range(12):
            make_event('xray_report_opened', created_at=when)
        report = build_monthly_report(date(2026, 6, 1))
        rows = dict(report['rows'])
        self.assertEqual(rows['Conversion · started/views'], '20%')
        self.assertEqual(rows['Conversion · completed/started'], '33%')
        self.assertIsNotNone(report['panel'])
        panel = report['panel']['text']
        self.assertIn('booking CTA', panel)        # opens high, bookings 0
        self.assertIn('loses half its starters', panel)

    def test_pain_themes_deterministic(self):
        from datetime import date
        when = datetime(2026, 5, 10, tzinfo=dt_timezone.utc)
        for text in ('We keep everything in Excel sheets',
                     'نسجل كل شيء في اكسل خارجي',
                     'Nobody trusts the reports'):
            make_run('erp_rescue', created_at=when, result_json={
                'meta': {'pain_text': text}, 'rescue': {'score': 10}})
        report = build_monthly_report(date(2026, 6, 1))
        text = ' '.join(report['paragraphs'])
        self.assertIn('Spreadsheets / parallel Excel ×2', text)

    def test_top_leads_by_risk(self):
        from datetime import date
        when = datetime(2026, 5, 10, tzinfo=dt_timezone.utc)
        hot = Lead.objects.create(email='hot@acme.com', company='Acme',
                                  source_tool='studio_xray')
        mild = Lead.objects.create(email='mild@beta.com', source_tool='erp_rescue')
        make_run('studio_xray', lead=hot, created_at=when,
                 result_json={'scoring': {'score': 91}})
        make_run('erp_rescue', lead=mild, created_at=when,
                 result_json={'rescue': {'score': 15}})
        report = build_monthly_report(date(2026, 6, 1))
        text = ' '.join(report['paragraphs'])
        self.assertIn('hot@acme.com (Acme) studio_xray 91/100', text)
        self.assertLess(text.index('hot@acme.com'), text.index('mild@beta.com'))

    def test_quiet_month_still_builds(self):
        report = build_monthly_report()
        self.assertTrue(report['rows'])
        self.assertTrue(report['paragraphs'])


@override_settings(ALLOWED_HOSTS=['testserver'])
class FounderReportTaskTests(TestCase):
    def test_daily_task_sends_and_dedups(self):
        self.assertEqual(send_founder_daily_report(), 'sent')
        self.assertEqual(EmailLog.objects.filter(category='founder_daily').count(), 1)
        log = EmailLog.objects.get(category='founder_daily')
        self.assertEqual(log.recipient_email, settings.FOUNDER_REPORT_RECIPIENTS[0])
        self.assertIn('BidERP Daily Report', log.subject)
        self.assertTrue(log.metadata['period'].startswith('founder_daily_summary:'))
        # second run for the same period: skipped, no duplicate row
        self.assertEqual(send_founder_daily_report(), 'skipped')
        self.assertEqual(EmailLog.objects.filter(category='founder_daily').count(), 1)
        # force bypasses the dedup for manual re-sends
        self.assertEqual(send_founder_daily_report(force=True), 'sent')
        self.assertEqual(EmailLog.objects.filter(category='founder_daily').count(), 2)

    def test_monthly_task_sends_and_dedups(self):
        self.assertEqual(send_founder_monthly_report(), 'sent')
        self.assertEqual(send_founder_monthly_report(), 'skipped')
        self.assertEqual(
            EmailLog.objects.filter(category='founder_monthly').count(), 1)
        log = EmailLog.objects.get(category='founder_monthly')
        self.assertIn('Monthly Growth Report', log.subject)

    def test_failed_attempt_does_not_block_retry(self):
        EmailLog.objects.create(
            recipient_email='x@x.com', subject='s', category='founder_daily',
            status='failed',
            metadata={'period': build_daily_report()['period_key']})
        self.assertEqual(send_founder_daily_report(), 'sent')

    @override_settings(FOUNDER_REPORT_RECIPIENTS=['a@bidatia.xyz', 'b@bidatia.xyz'])
    def test_multiple_recipients_to_plus_cc(self):
        send_founder_daily_report()
        log = EmailLog.objects.get(category='founder_daily')
        self.assertEqual(log.recipient_email, 'a@bidatia.xyz')

    def test_weekly_summary_unbroken(self):
        make_event('rescue_completed', tool='erp_rescue')
        status = send_founder_weekly_summary()
        self.assertEqual(status, 'sent')
        log = EmailLog.objects.get(category='founder_weekly')
        self.assertIn('weekly funnel summary', log.subject)

    def test_beat_schedule_contains_all_three(self):
        schedule = settings.CELERY_BEAT_SCHEDULE
        self.assertIn('send-founder-weekly-summary', schedule)
        self.assertIn('send-founder-daily-report', schedule)
        self.assertIn('send-founder-monthly-report', schedule)
        daily = schedule['send-founder-daily-report']['schedule']
        self.assertEqual((daily.hour, daily.minute), ({6}, {30}))
        monthly = schedule['send-founder-monthly-report']['schedule']
        self.assertEqual((monthly.hour, monthly.minute), ({7}, {0}))
        self.assertEqual(monthly.day_of_month, {1})
