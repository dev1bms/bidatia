"""Celery task driving a Data Risk Profiler run.

Credentials arrive as task ARGUMENTS, are used in memory, and go out of
scope when the task ends (project-wide: no Celery result backend, INFO
logging only). Nothing in this module may log them.
"""
import logging

from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded
from django.conf import settings
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import override as language_override

from tools_core.connectors import ConnectorError, OdooXmlRpcConnector
from tools_core.models import ToolRun
from tools_core.services.analytics import track
from tools_core.services.hot_leads import alert_hot_lead
from tools_core.utils import scrub_secrets
from tools_core.services.report_service import send_report_email

from .analyzer import analyze
from .collector import collect

logger = logging.getLogger('bidatia.tools')

TOOL_SLUG = 'data_risk'

# A risk score at/above this is a hot lead on its own.
HOT_RISK_SCORE = 70

TIMEOUT_MESSAGE = (
    'The scan took too long — the server may be slow or the database too '
    'large for the online tool. Please try again, or contact us for an '
    'assisted scan.'
)
UNEXPECTED_MESSAGE = 'Unexpected error while processing the diagnostic. Please try again.'


@shared_task
def run_data_risk_scan(toolrun_id, odoo_url, odoo_db, login, api_key,
                       language='en', save_snapshot=False):
    run = ToolRun.objects.filter(pk=toolrun_id).first()
    if run is None:
        logger.warning('data_risk: run %s not found', toolrun_id)
        return

    try:
        _set_status(run, 'connecting')
        connector = OdooXmlRpcConnector(odoo_url, odoo_db, login, api_key)
        info = connector.test_connection()

        run.odoo_version = info.server_version
        run.save(update_fields=['odoo_version'])
        if run.lead_id:
            run.lead.odoo_version_detected = info.server_version
            run.lead.odoo_edition_detected = info.edition
            run.lead.save(update_fields=['odoo_version_detected',
                                         'odoo_edition_detected', 'updated_at'])

        _set_status(run, 'collecting')
        collected = collect(connector, info)

        _set_status(run, 'analyzing')
        risk = analyze(collected)

        delta = _delta_against_previous(odoo_url, odoo_db, risk)
        advisor = _advisor_card(run, risk, collected, language)

        # Stored payload = analyzer output only: counts, scores, codes and
        # MASKED examples. The raw collected sections are never persisted.
        # The UI language rides along for expiry reminders and shares.
        meta = dict(collected.get('meta', {}), language=language)
        run.result_json = {'meta': meta, 'risk': risk, 'delta': delta,
                           'advisor': advisor}
        if save_snapshot:
            _save_snapshot(odoo_url, odoo_db, risk, collected)
        run.status = 'done'
        run.finished_at = timezone.now()
        run.save(update_fields=['result_json', 'status', 'finished_at'])
        logger.info('data_risk: run %s done (score %s)', run.pk, risk['score'])

        track(None, TOOL_SLUG, 'data_risk_completed', run=run,
              email=(run.lead.email if run.lead else ''),
              score=risk['score'], level=risk['level'])
        if risk['score'] >= HOT_RISK_SCORE:
            alert_hot_lead(run, 'data_risk_high', score=risk['score'],
                           level=risk['level'],
                           signals=['%s: %s' % (b['category'], b['code'])
                                    for b in risk['blockers'][:3]])

        with language_override('en'):
            report_path = reverse('tool_data_risk:report', args=[run.pk])
        send_report_email(run, report_path, 'Data Risk Profiler',
                          language=language)

    except SoftTimeLimitExceeded:
        _fail(run, TIMEOUT_MESSAGE,
              diagnostic='SoftTimeLimitExceeded: the scan exceeded its time budget.')
    except ConnectorError as exc:
        _fail(run, str(exc), diagnostic=str(exc))  # pre-sanitized
    except Exception as exc:  # noqa: BLE001
        logger.error('data_risk: run %s failed with %s', run.pk, type(exc).__name__)
        detail = scrub_secrets(f'{type(exc).__name__}: {exc}', api_key, login)
        _fail(run, UNEXPECTED_MESSAGE, diagnostic=detail)


def _delta_against_previous(odoo_url, odoo_db, risk):
    """Aggregate-only comparison data when an earlier OPT-IN snapshot of the
    same (hashed) database exists. Reading the previous snapshot needs no
    new consent — it only ever contained scores and counts."""
    from .models import DataRiskSnapshot, db_fingerprint

    previous = (DataRiskSnapshot.objects
                .filter(fingerprint=db_fingerprint(odoo_url, odoo_db))
                .order_by('-created_at').first())
    if previous is None:
        return None
    return {
        'prev_score': previous.score,
        'prev_level': previous.level,
        'prev_date': previous.created_at.date().isoformat(),
        'categories': previous.category_scores or {},
    }


def _save_snapshot(odoo_url, odoo_db, risk, collected):
    """Persist the opt-in aggregated snapshot: scores and counts ONLY."""
    from .models import DataRiskSnapshot, db_fingerprint

    sections = (collected or {}).get('sections') or {}
    DataRiskSnapshot.objects.create(
        fingerprint=db_fingerprint(odoo_url, odoo_db),
        score=risk.get('score') or 0,
        level=risk.get('level') or 'low',
        category_scores={c['code']: c['score']
                         for c in risk.get('categories') or []
                         if c.get('score') is not None},
        key_counts={
            'partners': (sections.get('partners') or {}).get('total_active') or 0,
            'products': (sections.get('products') or {}).get('total_variants') or 0,
            'attachments': (sections.get('attachments') or {}).get('total') or 0,
        },
    )


def _advisor_card(run, risk, collected, language):
    """Optional sanitized-AI explanation. Best-effort by contract: any
    failure ships the report without the card and tracks the failure."""
    if not settings.TOOLS_AI_MODEL:
        return None
    from .insights import generate_advice

    _set_status(run, 'ai_insights')
    advisor = None
    try:
        advisor = generate_advice(risk, collected.get('meta') or {}, language)
    except SoftTimeLimitExceeded:
        logger.warning('data_risk: run %s — soft time limit during AI phase, '
                       'shipping report without the advisor card', run.pk)
    except Exception as exc:  # noqa: BLE001 — the card is optional, the report is not
        logger.warning('data_risk: run %s advisor failed with %s',
                       run.pk, type(exc).__name__)
    track(None, TOOL_SLUG,
          'data_risk_ai_advisor_completed' if advisor
          else 'data_risk_ai_advisor_failed', run=run)
    return advisor


def _set_status(run, status):
    run.status = status
    run.save(update_fields=['status'])


def _fail(run, message, diagnostic=''):
    run.status = 'failed'
    run.error_message = message
    if diagnostic:
        run.diagnostic = str(diagnostic)[:500]
    run.finished_at = timezone.now()
    run.save(update_fields=['status', 'error_message', 'diagnostic', 'finished_at'])
    track(None, TOOL_SLUG, 'data_risk_failed', run=run)
    logger.info('data_risk: run %s failed (sanitized message stored)', run.pk)
