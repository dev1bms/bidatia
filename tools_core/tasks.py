"""Shared Celery tasks for the free-tools infrastructure.

Logging rule for every task in this project: NEVER log task arguments.
Tool-run tasks receive Odoo credentials as arguments; log record ids,
counts and statuses only.
"""
import logging

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger('bidatia.tools')


@shared_task
def ping():
    """Demo task to verify the worker pipeline end-to-end.

    Trigger from a shell:  from tools_core.tasks import ping; ping.delay()
    Then look for the log line in the worker output.
    """
    logger.info('tools_core ping task executed on a worker')
    return 'pong'


@shared_task
def wipe_expired_tool_results():
    """Daily beat task: remove report payloads of expired tool runs.

    Privacy promise on the site is "results auto-delete after 72 hours":
    the result_json payload is wiped; the row itself (status, timestamps,
    odoo_url, version) is kept for analytics.
    """
    from tools_core.models import ReportQuestion, ToolRun

    now = timezone.now()
    wiped = (
        ToolRun.objects
        .filter(expires_at__lte=now, result_json__isnull=False)
        .update(result_json=None)
    )
    # Chat content follows the same privacy promise as the report payload:
    # text wiped, rows kept for counts.
    wiped_questions = (
        ReportQuestion.objects
        .filter(run__expires_at__lte=now)
        .exclude(question='', answer='')
        .update(question='', answer='')
    )
    logger.info('wipe_expired_tool_results: wiped %d payload(s), %d chat message(s)',
                wiped, wiped_questions)
    return wiped


def _expiry_reminder_tools():
    """Per-tool reminder configuration. X-Ray wording is UNCHANGED; the
    registry only adds tools. `skip_events`: a visitor who already moved
    toward booking doesn't need the nudge."""
    from django.utils.translation import gettext_lazy

    return (
        {
            'tool_slug': 'studio_xray',
            'url_name': 'tool_studio_xray:report',
            'subject': gettext_lazy('Your Studio X-Ray report is deleted tomorrow — %(site)s'),
            'paragraph': gettext_lazy('As promised, your Studio X-Ray results are deleted automatically 72 hours after the scan — that window closes in about a day.'),
            'skip_events': ('booking_started_from_tool',),
            'sent_event': '',
        },
        {
            'tool_slug': 'data_risk',
            'url_name': 'tool_data_risk:report',
            'subject': gettext_lazy('Your Data Risk report expires tomorrow — %(site)s'),
            'paragraph': gettext_lazy('As promised, your Data Risk Profiler results are deleted automatically 72 hours after the scan — that window closes in about a day.'),
            'skip_events': ('data_risk_booking_clicked', 'booking_started_from_tool'),
            'sent_event': 'data_risk_expiry_reminder_sent',
        },
    )


def _run_language(run):
    """Best-known report language: X-Ray stores it on ai_insights, the
    Data Risk Profiler on meta — fall back to English."""
    result = run.result_json or {}
    return ((result.get('ai_insights') or {}).get('language')
            or (result.get('meta') or {}).get('language')
            or 'en')


@shared_task
def send_expiry_reminders():
    """Hourly beat: ONE reminder per report expiring within 24 hours.

    Covers every tool registered in _expiry_reminder_tools(). Skips anyone
    who already moved toward booking (ToolEvent), demo runs, and anything
    already reminded (deduped via the EmailLog archive — no extra schema
    needed). Privacy framing on purpose: the deletion IS the promise; the
    reminder just makes it useful.
    """
    from datetime import timedelta

    from django.conf import settings
    from django.urls import reverse
    from django.utils import translation
    from django.utils.translation import gettext as _

    from core.email_service import send_email
    from core.models import EmailLog
    from tools_core.models import ToolEvent, ToolRun
    from tools_core.services.analytics import track

    now = timezone.now()
    sent = 0
    for config in _expiry_reminder_tools():
        candidates = (
            ToolRun.objects
            .filter(tool_slug=config['tool_slug'], status='done',
                    result_json__isnull=False, lead__isnull=False,
                    expires_at__gt=now,
                    expires_at__lte=now + timedelta(hours=24))
            .select_related('lead')
        )
        for run in candidates:
            if not run.lead.email:
                continue
            if ((run.result_json or {}).get('meta') or {}).get('demo'):
                continue
            if EmailLog.objects.filter(category='report_expiry_reminder',
                                       related_id=str(run.pk)).exists():
                continue
            if ToolEvent.objects.filter(run=run,
                                        event__in=config['skip_events']).exists():
                continue

            language = _run_language(run)
            with translation.override(language):
                report_url = settings.SITE_BASE_URL.rstrip('/') + reverse(
                    config['url_name'], args=[run.pk])
                log = send_email(
                    to=run.lead.email,
                    recipient_name=run.lead.full_name,
                    subject=str(config['subject']) % {'site': settings.SITE_NAME},
                    category='report_expiry_reminder',
                    heading=_('Your report disappears tomorrow'),
                    paragraphs=[str(config['paragraph'])],
                    cta_label=_('Review my report'),
                    cta_url=report_url,
                    footnotes=[
                        _('Want to walk through it with an expert before it goes? Reply to this email to book your free 30-minute review.'),
                    ],
                    language=language,
                    related=run,
                    metadata={'tool_slug': config['tool_slug']},
                )
            if log.status == 'sent':
                sent += 1
                if config['sent_event']:
                    track(None, config['tool_slug'], config['sent_event'],
                          run=run, email=run.lead.email)
    logger.info('expiry reminders: %d sent', sent)
    return sent


def _send_founder_report(report, category, force=False):
    """Shared sender for the daily/monthly founder reports.

    Dedup contract: one SENT email per period_key per category. A failed
    attempt does not block a retry; `force=True` bypasses the check for
    manual re-sends.
    """
    from django.conf import settings

    from core.email_service import send_email
    from core.models import EmailLog

    if not force and EmailLog.objects.filter(
            category=category, status='sent',
            metadata__period=report['period_key']).exists():
        logger.info('%s: already sent for %s — skipped',
                    category, report['period_key'])
        return 'skipped'

    recipients = (getattr(settings, 'FOUNDER_REPORT_RECIPIENTS', None)
                  or [settings.CONTACT_NOTIFICATION_EMAIL])
    log = send_email(
        to=recipients[0],
        cc=recipients[1:],
        subject=report['subject'],
        category=category,
        heading=report['heading'],
        paragraphs=report['paragraphs'],
        rows=report['rows'],
        panel=report.get('panel'),
        footnotes=report.get('footnotes') or (),
        cta_label='Open the events admin',
        cta_url=settings.SITE_BASE_URL.rstrip('/') + '/admin/tools_core/toolevent/',
        language='en',
        metadata={'kind': category, 'period': report['period_key']},
    )
    return log.status


@shared_task
def send_founder_daily_report(force=False):
    """06:30 UTC beat: the last 24 hours, built for quick action."""
    from tools_core.services.founder_reports import build_daily_report

    return _send_founder_report(build_daily_report(), 'founder_daily',
                                force=force)


@shared_task
def send_founder_monthly_report(force=False):
    """First-of-month beat: the previous calendar month, analytical."""
    from tools_core.services.founder_reports import build_monthly_report

    return _send_founder_report(build_monthly_report(), 'founder_monthly',
                                force=force)


@shared_task
def send_founder_weekly_summary():
    """Monday beat: the launch funnel of the past 7 days, in one email."""
    from datetime import timedelta

    from django.conf import settings
    from django.db.models import Count

    from core.email_service import send_email
    from tools_core.models import Lead, ReportQuestion, ToolEvent, ToolRun

    since = timezone.now() - timedelta(days=7)

    counts = dict(
        ToolEvent.objects.filter(created_at__gte=since)
        .values_list('event')
        .annotate(n=Count('id'))
        .values_list('event', 'n')
    )
    rows = [(event, str(counts.get(event, 0))) for event in (
        'tool_page_view', 'rescue_started', 'rescue_completed',
        'rescue_pain_text_provided', 'rescue_booking_clicked',
        'rescue_xray_clicked', 'xray_started', 'xray_completed',
        'xray_report_opened', 'xray_chat_question_asked',
        'booking_started_from_tool', 'demo_report_opened',
    )]

    pains = [((r.result_json or {}).get('meta') or {}).get('pain_text', '')
             for r in ToolRun.objects.filter(tool_slug='erp_rescue',
                                             created_at__gte=since)]
    pains = [p for p in pains if p][:5]
    questions = list(
        ReportQuestion.objects.filter(created_at__gte=since)
        .exclude(question='')
        .values_list('question', flat=True)[:5]
    )
    waitlist = Lead.objects.filter(created_at__gte=since,
                                   source_tool__startswith='waitlist_').count()
    top_leads = [
        f"{lead.email} ({lead.company or '—'}) · {lead.source_tool}"
        for lead in Lead.objects.filter(created_at__gte=since)
        .exclude(source_tool__startswith='waitlist_')
        .order_by('-created_at')[:5]
    ]

    paragraphs = []
    if top_leads:
        paragraphs.append('Newest leads: ' + ' | '.join(top_leads))
    if questions:
        paragraphs.append('Report-chat questions: ' + ' | '.join(questions))
    panel = ({'label': 'Pain texts this week', 'text': ' • '.join(pains)}
             if pains else None)

    log = send_email(
        to=settings.CONTACT_NOTIFICATION_EMAIL,
        subject='BidERP Tools — weekly funnel summary',
        category='founder_weekly',
        heading='Your tools funnel, last 7 days',
        paragraphs=paragraphs or ['A quiet week — the counts are below.'],
        rows=rows + [('waitlist signups', str(waitlist))],
        panel=panel,
        cta_label='Open the events admin',
        cta_url=settings.SITE_BASE_URL.rstrip('/') + '/admin/tools_core/toolevent/',
        language='en',
        metadata={'kind': 'founder_weekly'},
    )
    return log.status
