"""AI interpretation layer for Studio X-Ray reports.

The deterministic analyzer/scoring stay the single source of truth; this
module asks a LOCAL model (tools_core.services.ai_service) to interpret the
finished results for business readers. Strictly best-effort: returns None on
any problem, and a report always renders without it.

The payload sent to the model is built ONLY from analyzer output — it can
never contain credentials, URLs or raw business records.
"""
import json
import logging
import re
from pathlib import Path

from tools_core.services import ai_service

logger = logging.getLogger('bidatia.tools')

SKILL_PATH = Path(__file__).parent / 'ai' / 'xray_insights_skill.md'

# Older Ollama versions inline the reasoning of thinking models into the
# content itself — strip it before JSON parsing.
_THINK_TAGS = re.compile(r'<think>.*?</think>', re.DOTALL)
_CODE_FENCES = re.compile(r'```(?:json)?', re.IGNORECASE)

LANGUAGE_NAMES = {'en': 'English', 'es': 'Spanish', 'ar': 'Arabic'}

# Output caps — anything beyond is truncated before storage.
MAX_NARRATIVE_CHARS = 1200
MAX_DOMAINS = 4
MAX_DOMAIN_CHARS = 40
MAX_HINT_CHARS = 300
MAX_BOARD_SUMMARY_CHARS = 700
MAX_QUESTIONS = 4
MAX_QUESTION_CHARS = 220

# Payload caps — keep the prompt small and the context window cheap.
MAX_BREAKDOWN_ROWS = 12
MAX_MODULE_NAMES = 20


def build_payload(analysis, scoring, meta, language):
    findings = [
        {'code': f.get('code'), 'severity': f.get('severity'), 'count': f.get('count')}
        for f in (analysis.get('findings') or [])
    ]
    breakdown = [
        {'model': r.get('model'), 'customizations': r.get('total')}
        for r in (analysis.get('model_breakdown') or [])[:MAX_BREAKDOWN_ROWS]
    ]
    modules = []
    module_summary = analysis.get('module_summary')
    if module_summary:
        examples = module_summary.get('examples') or {}
        modules = (examples.get('custom', []) + examples.get('third_party', [])
                   + examples.get('oca', []))[:MAX_MODULE_NAMES]

    payload = {
        'language': LANGUAGE_NAMES.get(language, 'English'),
        'odoo_version': (meta or {}).get('server_version') or 'unknown',
        'edition': (meta or {}).get('edition') or '',
        'score': (scoring or {}).get('score'),
        'effort_estimate': (scoring or {}).get('effort_estimate'),
        'totals': analysis.get('totals') or {},
        'findings': findings,
        'most_customized_models': breakdown,
        'non_standard_modules': modules,
    }

    # Report v3 — usage grounding makes the narrative concrete ("your
    # x_air_waybill holds 41,902 records") instead of abstract counts.
    usage = analysis.get('usage_summary')
    if usage:
        payload['custom_model_usage'] = {
            'top_models': [
                {'model': r.get('model'), 'records': r.get('records'),
                 'tier': r.get('tier')}
                for r in (usage.get('rows') or [])[:5]
            ],
            'total_records_in_custom_models': usage.get('total_custom_records'),
            'empty_models': usage.get('dead_count'),
        }
    pulse = analysis.get('pulse')
    if pulse:
        payload['operations'] = {
            'internal_users': pulse.get('internal_users'),
            'active_users_30d': pulse.get('active_users_30d'),
        }
    code = analysis.get('code_summary')
    if code:
        payload['code_modules_footprint'] = {
            'module_count': code.get('module_count'),
            'total_shipped_items': code.get('total_items'),
        }
    return payload


def generate_insights(analysis, scoring, meta, language, on_thinking=None):
    """Returns a validated insights dict for result_json, or None.

    `on_thinking` is forwarded to the AI service so callers (the Celery task)
    can surface the model's live reasoning trace on the progress page.
    """
    if not ai_service.is_enabled():
        return None

    system_prompt = SKILL_PATH.read_text(encoding='utf-8')
    payload = build_payload(analysis, scoring, meta, language)
    raw = ai_service.generate_json(
        system_prompt, json.dumps(payload, ensure_ascii=False),
        on_thinking=on_thinking,
        # free-form first answers are only accepted when they parse cleanly;
        # otherwise the service retries in strict JSON mode
        is_acceptable=lambda content: _validated(content) is not None)
    if not raw:
        return None

    insights = _validated(raw)
    if insights:
        insights['language'] = language
    return insights


def _extract_json_object(text):
    start, end = text.find('{'), text.rfind('}')
    if start == -1 or end <= start:
        return None
    try:
        return json.loads(text[start:end + 1])
    except (ValueError, TypeError):
        return None


def _validated(raw):
    """Schema + length enforcement. The model's words go straight into a
    client-facing report, so anything malformed is dropped entirely."""
    raw = _THINK_TAGS.sub('', str(raw))
    raw = _CODE_FENCES.sub('', raw).strip()
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        # Free-form answers may wrap the JSON in prose — try the outermost
        # object before giving up.
        data = _extract_json_object(raw)
        if data is None:
            logger.warning('xray insights rejected: model output was not valid JSON')
            return None
    if not isinstance(data, dict):
        logger.warning('xray insights rejected: JSON root is not an object')
        return None

    narrative = str(data.get('narrative') or '').strip()
    if not narrative:
        logger.warning('xray insights rejected: empty narrative')
        return None

    domains = data.get('business_domains')
    if not isinstance(domains, list):
        domains = []
    domains = [str(d).strip()[:MAX_DOMAIN_CHARS]
               for d in domains if str(d).strip()][:MAX_DOMAINS]

    questions = data.get('questions_for_your_team')
    if not isinstance(questions, list):
        questions = []
    questions = [str(q).strip()[:MAX_QUESTION_CHARS]
                 for q in questions if str(q).strip()][:MAX_QUESTIONS]

    return {
        'narrative': narrative[:MAX_NARRATIVE_CHARS],
        'business_domains': domains,
        'priority_hint': str(data.get('priority_hint') or '').strip()[:MAX_HINT_CHARS],
        # v2 fields — optional in old stored payloads, defaults keep templates simple
        'board_summary': str(data.get('board_summary') or '').strip()[:MAX_BOARD_SUMMARY_CHARS],
        'questions_for_your_team': questions,
    }
