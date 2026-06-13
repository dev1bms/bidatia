"""Sanitized AI advisor for the Data Risk report (optional layer).

Contract (docs/data_risk_profiler/HEURISTICS.md): the model explains, it
never scores. It receives ONLY the analyzer's stored output — category
scores, counts, percentages, issue codes and already-masked examples —
and its output is schema-validated and length-capped before storage. Any
failure means the report simply ships without the card.
"""
import json
from pathlib import Path

from tools_core.services import ai_service

SKILL_PATH = Path(__file__).resolve().parent / 'ai' / 'data_risk_advisor_skill.md'

MAX_TEXT_CHARS = 900
MAX_LIST_ITEMS = 4
MAX_ITEM_CHARS = 220


def build_payload(risk, meta, language):
    """The ONLY data the model ever sees. Everything here is already
    sanitized: codes, numbers and masked examples from result_json."""
    categories = []
    for category in (risk.get('categories') or []):
        if category.get('score') is None:
            continue
        categories.append({
            'code': category.get('code'),
            'score': category.get('score'),
            'severity': category.get('severity'),
            'issues': [{
                'code': issue.get('code'),
                'count': issue.get('count'),
                'pct': issue.get('pct'),
                'masked_examples': issue.get('examples') or [],
            } for issue in (category.get('issues') or [])[:4]],
        })
    return {
        'language': language,
        'overall_score': risk.get('score'),
        'risk_band': risk.get('level'),
        'categories': categories,
        'top_blocker_codes': [b.get('code') for b in (risk.get('blockers') or [])],
        'server_version': (meta or {}).get('server_version') or '',
    }


def generate_advice(risk, meta, language, on_thinking=None):
    """Returns the validated advisor dict for result_json, or None."""
    if not ai_service.is_enabled():
        return None
    system_prompt = SKILL_PATH.read_text(encoding='utf-8')
    payload = build_payload(risk, meta, language)
    raw = ai_service.generate_json(
        system_prompt, json.dumps(payload, ensure_ascii=False),
        on_thinking=on_thinking,
        is_acceptable=lambda content: _validated(content) is not None)
    if not raw:
        return None
    advice = _validated(raw)
    if advice:
        advice['language'] = language
    return advice


def _validated(raw):
    """Schema-validate and length-cap the model output; None on anything
    off-contract. The stored advisor card must be as predictable as the
    deterministic report around it."""
    start, end = raw.find('{'), raw.rfind('}')
    if start == -1 or end <= start:
        return None
    try:
        data = json.loads(raw[start:end + 1])
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None

    board = _clean_text(data.get('board_summary'))
    risks = _clean_text(data.get('migration_risks_plain_language'))
    priorities = _clean_list(data.get('cleanup_priorities'))
    questions = _clean_list(data.get('management_questions'), cap=3)
    if not board or not priorities:
        return None
    return {
        'board_summary': board,
        'cleanup_priorities': priorities,
        'management_questions': questions,
        'migration_risks_plain_language': risks,
    }


def _clean_text(value):
    return ' '.join(str(value or '').split())[:MAX_TEXT_CHARS]


def _clean_list(value, cap=MAX_LIST_ITEMS):
    if not isinstance(value, list):
        return []
    items = [' '.join(str(item).split())[:MAX_ITEM_CHARS]
             for item in value if str(item).strip()]
    return items[:cap]
