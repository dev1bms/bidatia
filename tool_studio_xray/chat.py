"""Report Q&A: a grounded chat about ONE finished Studio X-Ray report.

Same philosophy as insights.py — the deterministic report is the single
source of truth; the model only explains it. The visitor's question is
treated as untrusted data (the skill forbids following instructions in it),
answers are schema-validated and length-capped, and any failure simply
yields a friendly fallback handled by the caller.

Latency matters here, so generation skips the free-form thinking attempt
(allow_thinking=False -> strict JSON mode, ~15-20s on gemma4:26b).
"""
import json
import logging
from pathlib import Path

from tools_core.services import ai_service

from .insights import LANGUAGE_NAMES, MAX_BREAKDOWN_ROWS, MAX_MODULE_NAMES

logger = logging.getLogger('bidatia.tools')

CHAT_SKILL_PATH = Path(__file__).parent / 'ai' / 'xray_chat_skill.md'

MAX_QUESTION_CHARS = 300
MAX_ANSWER_CHARS = 1000
# How many previous Q&A pairs ride along for follow-up questions.
CONTEXT_TURNS = 3


def build_chat_payload(result, question, language, history=None):
    """Compact, credential-free prompt payload from the STORED report."""
    analysis = (result or {}).get('analysis') or {}
    scoring = (result or {}).get('scoring') or {}
    meta = (result or {}).get('meta') or {}
    modules = (result or {}).get('modules')
    usage = (result or {}).get('usage') or {}
    pulse = (result or {}).get('pulse') or {}

    report = {
        'odoo_version': meta.get('server_version') or 'unknown',
        'edition': meta.get('edition') or '',
        'score': scoring.get('score'),
        'effort_estimate': scoring.get('effort_estimate'),
        'totals': analysis.get('totals') or {},
        'findings': [
            {'code': f.get('code'), 'severity': f.get('severity'),
             'count': f.get('count'), 'examples': (f.get('examples') or [])[:5]}
            for f in analysis.get('findings') or []
        ],
        'most_customized_models': [
            {'model': r.get('model'), 'customizations': r.get('total')}
            for r in (analysis.get('model_breakdown') or [])[:MAX_BREAKDOWN_ROWS]
        ],
        'non_standard_modules': (
            ((modules or {}).get('examples') or {}).get('custom', [])
            + ((modules or {}).get('examples') or {}).get('third_party', [])
        )[:MAX_MODULE_NAMES],
    }
    # Report v3 — record counts let the chat answer "how big is x_air_waybill".
    if usage:
        report['custom_model_record_counts'] = [
            {'model': r.get('model'), 'records': r.get('records'), 'tier': r.get('tier')}
            for r in (usage.get('rows') or [])[:MAX_BREAKDOWN_ROWS]
        ]
        report['empty_custom_models'] = usage.get('dead_count')
        report['total_records_in_custom_models'] = usage.get('total_custom_records')
    if pulse:
        report['operations'] = {
            'internal_users': pulse.get('internal_users'),
            'active_users_30d': pulse.get('active_users_30d'),
        }

    payload = {
        'language': LANGUAGE_NAMES.get(language, 'English'),
        'report': report,
        'recent_conversation': [
            {'question': q[:MAX_QUESTION_CHARS], 'answer': a[:MAX_ANSWER_CHARS]}
            for q, a in (history or [])[-CONTEXT_TURNS:]
        ],
        'question': str(question)[:MAX_QUESTION_CHARS],
    }
    return payload


def generate_answer(result, question, language, history=None):
    """Returns the validated answer string, or None on any failure."""
    if not ai_service.is_enabled():
        return None

    system_prompt = CHAT_SKILL_PATH.read_text(encoding='utf-8')
    payload = build_chat_payload(result, question, language, history)
    raw = ai_service.generate_json(
        system_prompt, json.dumps(payload, ensure_ascii=False),
        allow_thinking=False,
        is_acceptable=lambda content: _validated_answer(content) is not None)
    if not raw:
        return None
    return _validated_answer(raw)


def _validated_answer(raw):
    try:
        data = json.loads(str(raw).strip())
    except (ValueError, TypeError):
        logger.warning('xray chat rejected: not valid JSON')
        return None
    if not isinstance(data, dict):
        return None
    answer = str(data.get('answer') or '').strip()
    if not answer:
        logger.warning('xray chat rejected: empty answer')
        return None
    return answer[:MAX_ANSWER_CHARS]
