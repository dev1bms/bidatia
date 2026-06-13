"""Advisor reading for a finished ERP Rescue Check — AI interprets, never decides.

Same philosophy as the X-Ray insights: the deterministic result (score,
level, risks) is final; the model only connects the patterns and writes the
consultant's reading. The visitor's pain_text is untrusted input. Output is
schema-validated and length-capped before storage.
"""
import json
import logging
from pathlib import Path

from tools_core.services import ai_service

logger = logging.getLogger('bidatia.tools')

SKILL_PATH = Path(__file__).parent / 'ai' / 'rescue_advisor_skill.md'

MAX_PAIN_CHARS = 400
MAX_READING_CHARS = 1200
MAX_LINE_CHARS = 220
MAX_SIGNAL_CHARS = 600
MAX_LIST_ITEMS = 3

LANGUAGE_NAMES = {'en': 'English', 'es': 'Spanish', 'ar': 'Arabic'}


def build_payload(rescue, questions, pain_text, erp_type, language):
    """`questions`: [{'question': <english text>, 'answer': 'yes|partial|no'}]."""
    return {
        'language': LANGUAGE_NAMES.get(language, 'English'),
        'erp_type': erp_type or 'unknown',
        'score': rescue.get('score'),
        'level': rescue.get('level'),
        'section_scores': rescue.get('sections') or {},
        'top_risks': rescue.get('top_risks') or [],
        'questions': questions,
        'pain_text': str(pain_text or '')[:MAX_PAIN_CHARS],
    }


def generate_advice(rescue, questions, pain_text, erp_type, language):
    """Returns the validated advisor dict, or None on any failure."""
    if not ai_service.is_enabled():
        return None
    payload = build_payload(rescue, questions, pain_text, erp_type, language)
    raw = ai_service.generate_json(
        SKILL_PATH.read_text(encoding='utf-8'),
        json.dumps(payload, ensure_ascii=False),
        allow_thinking=False,
        is_acceptable=lambda content: validate_advice(content) is not None)
    return validate_advice(raw) if raw else None


def validate_advice(raw):
    """Schema + length caps; unknown keys dropped. None when unusable."""
    try:
        data = json.loads(str(raw).strip())
    except (ValueError, TypeError):
        logger.warning('rescue advisor rejected: not valid JSON')
        return None
    if not isinstance(data, dict):
        return None
    reading = str(data.get('advisor_reading') or '').strip()
    if not reading:
        logger.warning('rescue advisor rejected: empty reading')
        return None

    def _lines(key):
        items = data.get(key)
        if not isinstance(items, list):
            return []
        return [str(item).strip()[:MAX_LINE_CHARS]
                for item in items if str(item).strip()][:MAX_LIST_ITEMS]

    return {
        'advisor_reading': reading[:MAX_READING_CHARS],
        'next_3_steps': _lines('next_3_steps'),
        'management_questions': _lines('management_questions'),
        'internal_sales_signal': str(data.get('internal_sales_signal') or '').strip()[:MAX_SIGNAL_CHARS],
    }
