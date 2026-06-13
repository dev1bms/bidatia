"""Celery task for the advisor reading. The deterministic result is already
stored and visible — this only ADDS the AI card; any failure leaves the
result page exactly as it was. Never log task arguments."""
import logging

from celery import shared_task
from django.utils import translation

from tools_core.models import ToolRun
from tools_core.services.analytics import track

from .advisor import generate_advice
from .checklist import QUESTIONS

logger = logging.getLogger('bidatia.tools')


@shared_task
def generate_advisor_reading(toolrun_id):
    run = ToolRun.objects.filter(pk=toolrun_id, tool_slug='erp_rescue').first()
    if run is None:
        return
    result = run.result_json if not run.is_expired else None
    rescue = (result or {}).get('rescue')
    advisor = (result or {}).get('advisor') or {}
    if not rescue or advisor.get('status') != 'pending':
        return

    meta = result.get('meta') or {}
    # English question texts keep the payload unambiguous; the model writes
    # its answer in the visitor's language.
    from .views import QUESTION_LABELS
    with translation.override('en'):
        questions = [{'question': str(QUESTION_LABELS[code]),
                      'answer': rescue.get('answers', {}).get(code) or 'unknown'}
                     for code, *_ in QUESTIONS]

    advice = generate_advice(
        rescue, questions,
        pain_text=meta.get('pain_text', ''),
        erp_type=meta.get('erp_type', 'unknown'),
        language=meta.get('language', 'en'),
    )

    # Re-read to avoid clobbering concurrent changes to result_json.
    run.refresh_from_db()
    result = run.result_json or {}
    if advice:
        result['advisor'] = {'status': 'done', **advice}
        logger.info('rescue advisor: run %s reading generated', run.pk)
        track(None, 'erp_rescue', 'rescue_advisor_completed', run=run,
              email=(run.lead.email if run.lead else ''))
    else:
        result['advisor'] = {'status': 'failed'}
        logger.info('rescue advisor: run %s failed (see ai_service warnings)', run.pk)
    run.result_json = result
    run.save(update_fields=['result_json'])
