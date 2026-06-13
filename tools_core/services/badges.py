"""Healthy System Badge — eligibility and creation (shared by both tools).

Eligibility uses the tools' EXISTING score semantics (plan rule: never
invent certification thresholds):
- ERP Rescue Check: level 'stable' (its best band).
- Studio X-Ray: complexity score in the 'low' band (<= 24).
- Data Risk Profiler: risk band 'low' (its best band).
Demo runs and expired/wiped results are never eligible.
"""
from tools_core.models import HealthBadge

LEVEL_STABLE = 'stable'
LEVEL_LOW_COMPLEXITY = 'low_complexity'
LEVEL_LOW_DATA_RISK = 'low_data_risk'

XRAY_LOW_SCORE_MAX = 24  # matches the 'Low complexity' band in the report


def badge_eligibility(run):
    """Return the badge level_code the run currently qualifies for, or None."""
    if run is None or run.status != 'done' or run.is_expired:
        return None
    result = run.result_json or {}
    if ((result.get('meta') or {}).get('demo')):
        return None
    if run.tool_slug == 'erp_rescue':
        level = ((result.get('rescue') or {}).get('level'))
        return LEVEL_STABLE if level == 'stable' else None
    if run.tool_slug == 'studio_xray':
        score = (result.get('scoring') or {}).get('score')
        if isinstance(score, (int, float)) and score <= XRAY_LOW_SCORE_MAX:
            return LEVEL_LOW_COMPLEXITY
        return None
    if run.tool_slug == 'data_risk':
        level = (result.get('risk') or {}).get('level')
        return LEVEL_LOW_DATA_RISK if level == 'low' else None
    return None


def get_active_badge(run):
    return HealthBadge.objects.filter(run=run, is_active=True).first()


def get_or_create_badge(run, company_name=''):
    """Create (or return the existing) badge for an eligible run.
    Returns (badge, created) — (None, False) when not eligible."""
    level = badge_eligibility(run)
    if level is None:
        return None, False
    existing = get_active_badge(run)
    if existing:
        return existing, False
    badge = HealthBadge.objects.create(
        run=run,
        tool_slug=run.tool_slug,
        level_code=level,
        company_name=(company_name or '').strip()[:150],
    )
    return badge, True
