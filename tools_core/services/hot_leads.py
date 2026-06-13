"""Instant internal alerts when a tool surfaces a HOT lead.

One short, actionable email the moment it happens — a strong prospect must
never wait for the weekly summary. Strictly best-effort (never breaks a
user-facing flow), deduplicated per (run, reason) via the EmailLog archive,
internal English only. internal_sales_signal-style content stays here and in
the admin — it never reaches a visitor.
"""
import logging

from django.conf import settings
from django.urls import reverse
from django.utils import translation

logger = logging.getLogger('bidatia.tools')

CATEGORY = 'hot_lead_alert'

REASON_LABELS = {
    'rescue_hot': 'Rescue check: high risk score / pain reported',
    'xray_score_high': 'Studio X-Ray: high complexity score',
    'booking_clicked': 'Clicked the booking CTA',
    'chat_question': 'Asked the report analyst a question',
    'demo_to_real': 'Viewed the demo, then started a REAL scan',
}

RESULT_URL_NAMES = {
    'studio_xray': 'tool_studio_xray:report',
    'erp_rescue': 'tool_erp_rescue:result',
}


def alert_hot_lead(run, reason, *, score=None, level='', signals=(),
                   pain_text='', question=''):
    """Send one internal hot-lead email. Returns True when a NEW alert went
    out; False on duplicates, demo runs or any failure (never raises)."""
    try:
        return _alert(run, reason, score, level, signals, pain_text, question)
    except Exception:  # noqa: BLE001 — alerts must never break a flow
        logger.warning('hot lead alert failed (reason=%s)', reason)
        return False


def _alert(run, reason, score, level, signals, pain_text, question):
    from core.email_service import send_email
    from core.models import EmailLog
    from tools_core.services.analytics import track

    if (((run.result_json or {}).get('meta') or {}).get('demo')):
        return False
    if EmailLog.objects.filter(category=CATEGORY, related_id=str(run.pk),
                               metadata__reason=reason).exists():
        return False  # one alert per (run, reason)

    lead = run.lead
    base = settings.SITE_BASE_URL.rstrip('/')
    with translation.override('en'):
        result_url = ''
        if run.tool_slug in RESULT_URL_NAMES:
            result_url = base + reverse(RESULT_URL_NAMES[run.tool_slug],
                                        args=[run.pk])
        admin_url = base + f'/admin/tools_core/toolrun/{run.pk}/change/'

        rows = [('Tool', run.tool_slug),
                ('Why now', REASON_LABELS.get(reason, reason))]
        if score is not None:
            rows.append(('Score', f'{score} / 100' + (f' — {level}' if level else '')))
        if lead:
            rows.append(('Lead', lead.email or '—'))
            if lead.full_name:
                rows.append(('Name', lead.full_name))
            if lead.company:
                rows.append(('Company', lead.company))
        for i, signal in enumerate(list(signals)[:3], 1):
            rows.append((f'Signal {i}', str(signal)))
        if question:
            rows.append(('Chat question', question[:300]))
        rows.append(('Admin', admin_url))
        if result_url:
            rows.append(('Result', result_url))

        recipients = settings.HOT_LEAD_RECIPIENTS
        log = send_email(
            to=recipients[0],
            cc=recipients[1:],
            subject=f'HOT LEAD — {run.tool_slug}: {REASON_LABELS.get(reason, reason)}',
            category=CATEGORY,
            heading='A hot lead, right now',
            paragraphs=['Strike while it is warm — this signal is minutes old.'],
            rows=rows,
            panel=({'label': 'Their pain, in their words', 'text': pain_text[:400]}
                   if pain_text else None),
            cta_label='Contact this lead now',
            cta_url=(f'mailto:{lead.email}' if lead and lead.email else admin_url),
            language='en',
            related=run,
            metadata={'reason': reason},
        )

    if log.status != 'sent':
        return False
    track(None, run.tool_slug, 'hot_lead_alert_sent', run=run,
          email=(lead.email if lead else ''), reason=reason)
    return True
