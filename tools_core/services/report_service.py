"""Report delivery shared by all tool apps. Phase 1: email with a tokenized
report link (PDF deliberately skipped — link-first per the plan).

All sending and archiving goes through core.email_service — this module only
assembles the report-specific content pieces, localized to the language the
visitor ran the tool in.
"""
import logging

from django.conf import settings
from django.utils import formats, translation
from django.utils.translation import gettext as _

from core.email_service import send_email

logger = logging.getLogger('bidatia.tools')


def send_report_email(run, report_path, tool_name, ai_summary=None, language=None):
    """Email the report link for a finished run to its lead. Best-effort:
    returns True/False, never raises (a failed email must not fail the run).

    `report_path` is an absolute path (e.g. /en/tools/studio-xray/report/<uuid>/)
    produced by the calling tool app via reverse(). `ai_summary` — when the
    AI insights produced a board-level summary — personalizes the email with
    the lead's own results instead of a generic teaser.
    """
    lead = run.lead
    if lead is None or not lead.email:
        return False

    report_url = settings.SITE_BASE_URL.rstrip('/') + report_path
    language = language or translation.get_language() or 'en'

    with translation.override(language):
        log = send_email(
            to=lead.email,
            recipient_name=lead.full_name,
            subject=_('Your %(tool)s report — %(site)s') % {
                'tool': tool_name, 'site': settings.SITE_NAME},
            category='tool_report',
            heading=_('Your %(tool)s report is ready') % {'tool': tool_name},
            paragraphs=[
                _('The diagnostic has finished. Open your report below — no login needed.'),
            ],
            panel=({'label': _('What your scan found'),
                    'text': (ai_summary or '').strip()}
                   if (ai_summary or '').strip() else None),
            cta_label=_('View my report'),
            cta_url=report_url,
            footnotes=[
                _('For your privacy, the report is automatically deleted on %(date)s (UTC).') % {
                    'date': formats.date_format(run.expires_at, 'j F Y, H:i')},
                _('Want an expert walkthrough of the results? Reply to this email to book a free 30-minute review of your report.'),
            ],
            language=language,
            related=run,
            metadata={'tool_slug': run.tool_slug},
        )

    if log.status != 'sent':
        # Log the run id only — no recipient, no link, no payload.
        logger.warning('report email failed for run %s', run.pk)
        return False
    return True
