"""Studio X-Ray scoring — pure Python, no Django/ORM imports.

Turns the analyzer's totals into a 0–100 Customization Complexity Score and
an indicative cleanup-effort range. All tunable constants live here, in one
place. The output is always an effort RANGE, never a price.
"""

# Weight per counted item (plan §6.3). A computed/related field counts at its
# own (higher) weight INSTEAD of the plain-field weight, not in addition.
WEIGHTS = {
    'plain_studio_fields': 1,
    'computed_studio_fields': 3,
    'studio_views': 2,
    'automated_actions': 3,
    'code_server_actions': 5,
    'custom_models': 8,
}

# Raw weighted points at which the 0–100 score saturates. 250 points ≈ a
# database where Studio cleanup is a multi-week project in its own right.
SCORE_SATURATION_POINTS = 250

# Score bands → indicative effort ranges (inclusive bounds).
EFFORT_BANDS = (
    (0, 15, '1–3 days'),
    (16, 40, '4–8 days'),
    (41, 70, '2–3 weeks'),
    (71, 100, '4+ weeks'),
)

EFFORT_NOTE = 'Indicative estimate — an exact quote requires a code review.'


def compute_score(totals, usage=None):
    """totals: the analyzer's totals dict (or any dict with WEIGHTS keys).

    `usage` (optional, Report v3): the analyzer's usage summary. Empty custom
    models are deleted rather than migrated, so they are discounted from the
    EFFORT estimate. The 0-100 risk score itself stays usage-independent so
    scores remain comparable across reports.
    """
    inputs = {key: int(totals.get(key, 0) or 0) for key in WEIGHTS}
    raw_points = sum(WEIGHTS[key] * count for key, count in inputs.items())
    score = min(100, round(raw_points * 100 / SCORE_SATURATION_POINTS))

    dead_models = int((usage or {}).get('dead_count') or 0)
    dead_models = min(dead_models, inputs['custom_models'])
    effort_points = raw_points - WEIGHTS['custom_models'] * dead_models
    effort_score = min(100, round(effort_points * 100 / SCORE_SATURATION_POINTS))

    return {
        'score': score,
        'raw_points': raw_points,
        'effort_estimate': _effort_for(effort_score),
        'effort_note': EFFORT_NOTE,
        'dead_models_discounted': dead_models,
        'inputs': inputs,
        'weights': dict(WEIGHTS),
    }


def _effort_for(score):
    for low, high, label in EFFORT_BANDS:
        if low <= score <= high:
            return label
    return EFFORT_BANDS[-1][2]
