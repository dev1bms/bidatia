"""ERP Rescue Check — pure Python questions catalog and scoring.

No Django imports: fully unit-testable, mirroring the analyzer/scoring
philosophy of the other tools. Codes only — all human wording (and its
translation) lives at the view layer.

The score is a RISK score: 0 = healthy, 100 = rescue needed urgently.
Killer questions (weight 5) are the patterns that, in real rescue
engagements, predict a failing system on their own: parallel spreadsheets,
untested backups, single-person dependency, unknown customizations,
upgrade fear and reports that disagree.
"""

SECTIONS = ['ownership', 'people', 'trust', 'upgrade', 'operations', 'continuity']

ANSWERS = ('yes', 'partial', 'no')

# (code, section, weight, reverse)
# reverse=False → "yes" is the healthy answer; reverse=True → "yes" is the risk.
QUESTIONS = [
    ('owner_defined', 'ownership', 3, False),
    ('customizations_documented', 'ownership', 3, False),
    ('process_map', 'ownership', 2, False),
    ('shared_knowledge', 'ownership', 3, False),

    ('single_developer', 'people', 5, True),
    ('single_operator', 'people', 4, True),
    ('absence_risk', 'people', 4, True),
    ('written_knowledge', 'people', 3, False),

    ('parallel_excel', 'trust', 5, True),
    ('reports_match', 'trust', 5, False),
    ('manual_corrections', 'trust', 3, True),
    ('management_trust', 'trust', 4, False),

    ('upgrade_fear', 'upgrade', 5, True),
    ('unknown_customizations', 'upgrade', 5, True),
    ('recent_upgrade', 'upgrade', 3, False),
    ('customization_inventory', 'upgrade', 3, False),

    ('workarounds', 'operations', 4, True),
    ('manual_steps', 'operations', 3, True),
    ('outside_processes', 'operations', 3, True),
    ('system_slows', 'operations', 3, True),

    ('support_contract', 'continuity', 3, False),
    ('test_environment', 'continuity', 3, False),
    ('tested_backup', 'continuity', 5, False),
    ('emergency_plan', 'continuity', 3, False),
]

QUESTION_CODES = [q[0] for q in QUESTIONS]

# Risk factor contributed by an answer to a NORMAL (yes-is-healthy) question.
_RISK_FACTOR = {'yes': 0.0, 'partial': 0.5, 'no': 1.0}

LEVEL_STABLE = 'stable'
LEVEL_MONITORING = 'needs_monitoring'
LEVEL_AT_RISK = 'at_risk'
LEVEL_RESCUE = 'rescue_urgent'

# (inclusive lower bound, level) — checked from the top down.
_LEVEL_BANDS = (
    (70, LEVEL_RESCUE),
    (45, LEVEL_AT_RISK),
    (20, LEVEL_MONITORING),
    (0, LEVEL_STABLE),
)

TOP_RISKS = 3


def risk_factor(answer, reverse):
    """0.0 (healthy) … 1.0 (full risk) for one answer."""
    factor = _RISK_FACTOR.get(answer, 0.5)  # unknown answers count as partial
    return 1.0 - factor if reverse else factor


def level_for(score):
    for bound, level in _LEVEL_BANDS:
        if score >= bound:
            return level
    return LEVEL_STABLE


def compute_result(answers):
    """answers: {question_code: 'yes'|'partial'|'no'}.

    Returns scores (overall + per section, 0-100, higher = more risk),
    the risk level code and the TOP_RISKS highest-contributing question
    codes — everything the result page and the email need.
    """
    section_points = {section: 0.0 for section in SECTIONS}
    section_max = {section: 0 for section in SECTIONS}
    contributions = []

    for code, section, weight, reverse in QUESTIONS:
        factor = risk_factor(answers.get(code), reverse)
        section_points[section] += weight * factor
        section_max[section] += weight
        if factor > 0:
            contributions.append((weight * factor, code))

    total_points = sum(section_points.values())
    total_max = sum(section_max.values())
    score = round(total_points * 100 / total_max) if total_max else 0

    contributions.sort(key=lambda item: (-item[0], QUESTION_CODES.index(item[1])))

    return {
        'score': score,
        'level': level_for(score),
        'sections': {
            section: round(section_points[section] * 100 / section_max[section])
            for section in SECTIONS
        },
        'top_risks': [code for _, code in contributions[:TOP_RISKS]],
        'answers': {code: answers.get(code) for code, *_ in QUESTIONS
                    if answers.get(code) in ANSWERS},
    }
