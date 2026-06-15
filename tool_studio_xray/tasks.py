"""Celery task driving a Studio X-Ray run.

Credentials are accepted as task ARGUMENTS, used in memory, and go out of
scope when the task ends. The project-wide Celery config guarantees they are
never persisted (no result backend) — and nothing in this module may log them.
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
from tools_core.services.report_service import send_report_email
from tools_core.utils import clear_run_note, scrub_secrets, set_run_note

from .analyzer import analyze
from .collector import collect
from .insights import generate_insights
from .scoring import compute_score

logger = logging.getLogger('bidatia.tools')

# Keep the stored payload bounded: the report shows at most this many rows.
MAX_BREAKDOWN_ROWS = 15

# A complexity score at/above this is a hot lead on its own.
HOT_XRAY_SCORE = 70

TIMEOUT_MESSAGE = (
    'The scan took too long — the server may be slow or the database too '
    'large for the online tool. Please try again, or contact us for an '
    'assisted scan.'
)
UNEXPECTED_MESSAGE = 'Unexpected error while processing the diagnostic. Please try again.'


@shared_task
def run_studio_xray(toolrun_id, odoo_url, odoo_db, login, api_key, language='en',
                    scope='studio'):
    run = ToolRun.objects.filter(pk=toolrun_id).first()
    if run is None:
        logger.warning('studio_xray: run %s not found', toolrun_id)
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
            run.lead.save(update_fields=['odoo_version_detected', 'odoo_edition_detected', 'updated_at'])

        _set_status(run, 'collecting')
        inventory = collect(connector, info, scope=scope)

        _set_status(run, 'analyzing')
        analysis = analyze(inventory)
        scoring = compute_score(analysis['totals'], usage=analysis.get('usage_summary'))

        # Optional local-AI interpretation. Strictly best-effort: only the
        # analyzer OUTPUT is sent (never credentials), and any failure means
        # the report simply ships without the AI section.
        ai_insights = None
        if settings.TOOLS_AI_MODEL:
            _set_status(run, 'ai_insights')
            try:
                ai_insights = generate_insights(
                    analysis, scoring, inventory.get('meta', {}), language,
                    on_thinking=_thinking_note_writer(run.pk))
            except SoftTimeLimitExceeded:
                # The deterministic report is DONE at this point — a slow
                # model must never sink it. Ship without the AI card.
                logger.warning('studio_xray: run %s — soft time limit during '
                               'AI phase, shipping report without insights', run.pk)
            finally:
                clear_run_note(run.pk)

        # Store only what the report needs — never the raw record inventory.
        # 'modules' is the v2 classified summary (None on restricted access);
        # old reports without it stay fully renderable.
        run.result_json = {
            'meta': inventory.get('meta', {}),
            'module_context': (inventory.get('sections') or {}).get('module_context', {}),
            'analysis': {
                'findings': analysis['findings'],
                'totals': analysis['totals'],
                'model_breakdown': analysis['model_breakdown'][:MAX_BREAKDOWN_ROWS],
                'sections_with_errors': analysis['sections_with_errors'],
            },
            'scoring': scoring,
            'modules': analysis.get('module_summary'),
            'ai_insights': ai_insights,
            # Report v3 — optional blocks; old reports simply lack the keys.
            'identity': analysis.get('identity'),
            'pulse': analysis.get('pulse'),
            'usage': analysis.get('usage_summary'),
            'code': analysis.get('code_summary'),
        }
        run.status = 'done'
        run.finished_at = timezone.now()
        run.save(update_fields=['result_json', 'status', 'finished_at'])
        logger.info('studio_xray: run %s done (score %s)', run.pk, scoring['score'])
        track(None, 'studio_xray', 'xray_completed', run=run,
              email=(run.lead.email if run.lead else ''),
              score=scoring['score'], scope=scope)
        if scoring['score'] >= HOT_XRAY_SCORE:
            alert_hot_lead(run, 'xray_score_high', score=scoring['score'],
                           signals=[f['title'] for f in analysis['findings'][:3]])

        # Email links are built in the default language; best-effort delivery.
        with language_override('en'):
            report_path = reverse('tool_studio_xray:report', args=[run.pk])
        send_report_email(run, report_path, 'Studio X-Ray',
                          ai_summary=(ai_insights or {}).get('board_summary'),
                          language=language)

    except SoftTimeLimitExceeded:
        _fail(run, TIMEOUT_MESSAGE,
              diagnostic='SoftTimeLimitExceeded: the scan exceeded its time budget.')
    except ConnectorError as exc:
        # Connector messages are pre-sanitized; safe as both the user message
        # and the diagnostic.
        _fail(run, str(exc), diagnostic=str(exc))
    except Exception as exc:  # noqa: BLE001
        # The user sees a safe generic message; the diagnostic keeps the
        # exception class + message with the known credentials scrubbed out, so
        # the owner can tell WHAT went wrong without leaking secrets.
        logger.error('studio_xray: run %s failed with %s', run.pk, type(exc).__name__)
        detail = scrub_secrets(f'{type(exc).__name__}: {exc}', api_key, login)
        _fail(run, UNEXPECTED_MESSAGE, diagnostic=detail)


def _set_status(run, status):
    run.status = status
    run.save(update_fields=['status'])


def _thinking_note_writer(run_id):
    """Live note for the progress page: the tail of the model's reasoning
    trace, whitespace-collapsed. Goes through the shared cache (best-effort)."""
    def write(thinking_so_far):
        snippet = ' '.join(str(thinking_so_far).split())
        set_run_note(run_id, snippet[-220:])
    return write


def _fail(run, message, diagnostic=''):
    run.status = 'failed'
    run.error_message = message
    if diagnostic:
        run.diagnostic = str(diagnostic)[:500]
    run.finished_at = timezone.now()
    run.save(update_fields=['status', 'error_message', 'diagnostic', 'finished_at'])
    logger.info('studio_xray: run %s failed (sanitized message stored)', run.pk)


@shared_task
def answer_report_question(question_id):
    """Answer one report-chat question. Grounded in the STORED report only;
    any failure marks the question failed (the widget shows a friendly
    fallback and the visitor can rephrase)."""
    from tools_core.models import ReportQuestion

    from .chat import generate_answer

    question = ReportQuestion.objects.filter(pk=question_id).select_related('run').first()
    if question is None:
        return
    run = question.run

    question.status = 'answering'
    question.save(update_fields=['status'])

    result = run.result_json if not run.is_expired else None
    if not result:
        question.status = 'failed'
        question.save(update_fields=['status'])
        return

    history = list(
        run.questions.filter(status='done')
        .exclude(pk=question.pk)
        .order_by('-created_at')
        .values_list('question', 'answer')[:3]
    )[::-1]

    answer = generate_answer(result, question.question, question.language, history)
    if answer:
        question.answer = answer
        question.status = 'done'
        question.save(update_fields=['answer', 'status'])
        logger.info('xray chat: question %s answered', question.pk)
    else:
        question.status = 'failed'
        question.save(update_fields=['status'])
        logger.info('xray chat: question %s failed (see ai_service warnings)', question.pk)
