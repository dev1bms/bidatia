"""Odoo version support timeline data for the EOL countdown pages.

ACCURACY RULE (growth plan §Phase 3): Odoo does not publish hard public
end-of-life dates for every deployment model. Everything here is derived
from Odoo's well-known release rhythm (one major every October) and its
standard policy of maintaining the THREE most recent major versions.
Dates carry an `estimated` flag and a source note — the templates must
always say "estimated" / "planning horizon", never absolute promises.

Review once a year after the October release: bump the newest entry and
shift the window. Keep `LATEST_KNOWN_MAJOR` in tool_studio_xray/analyzer.py
in sync when adding a new major.
"""
from datetime import date

from django.utils.translation import gettext_lazy

# One shared source note keeps the caveat consistent everywhere.
SOURCE_NOTE = gettext_lazy(
    "Estimated from Odoo's standard policy: one major release each October, "
    'with the three most recent major versions maintained. Odoo does not '
    'publish fixed end-of-life dates — treat this as a planning horizon, '
    'not a contractual deadline.'
)

STATUS_SUPPORTED = 'supported'
STATUS_ENDING_SOON = 'ending_soon'   # less than 12 months of window left
STATUS_ENDED = 'ended'

ENDING_SOON_DAYS = 365

# Ordered newest → oldest. All dates use the 1st of the release month —
# deliberately coarse, matching the "planning horizon" framing.
ODOO_VERSIONS = [
    {
        'slug': 'odoo-19', 'major': 19, 'name': 'Odoo 19',
        'release_date': date(2025, 10, 1), 'release_estimated': False,
        'support_end': date(2028, 10, 1), 'support_end_estimated': True,
    },
    {
        'slug': 'odoo-18', 'major': 18, 'name': 'Odoo 18',
        'release_date': date(2024, 10, 1), 'release_estimated': False,
        'support_end': date(2027, 10, 1), 'support_end_estimated': True,
    },
    {
        'slug': 'odoo-17', 'major': 17, 'name': 'Odoo 17',
        'release_date': date(2023, 11, 1), 'release_estimated': False,
        'support_end': date(2026, 10, 1), 'support_end_estimated': True,
    },
    {
        'slug': 'odoo-16', 'major': 16, 'name': 'Odoo 16',
        'release_date': date(2022, 10, 1), 'release_estimated': False,
        'support_end': date(2025, 10, 1), 'support_end_estimated': True,
    },
    {
        'slug': 'odoo-15', 'major': 15, 'name': 'Odoo 15',
        'release_date': date(2021, 10, 1), 'release_estimated': False,
        'support_end': date(2024, 10, 1), 'support_end_estimated': True,
    },
    {
        'slug': 'odoo-14', 'major': 14, 'name': 'Odoo 14',
        'release_date': date(2020, 10, 1), 'release_estimated': False,
        'support_end': date(2023, 11, 1), 'support_end_estimated': True,
    },
]

_BY_SLUG = {v['slug']: v for v in ODOO_VERSIONS}


def get_version(slug):
    return _BY_SLUG.get(slug)


def annotate(version, today=None):
    """Add countdown/status fields. Past dates are a normal state, never an
    error: the page flips from countdown to "ended N days ago"."""
    today = today or date.today()
    delta = (version['support_end'] - today).days
    if delta < 0:
        status = STATUS_ENDED
    elif delta <= ENDING_SOON_DAYS:
        status = STATUS_ENDING_SOON
    else:
        status = STATUS_SUPPORTED
    return {
        **version,
        'status': status,
        'days_left': max(delta, 0),
        'days_since_end': max(-delta, 0),
        'months_left': max(delta, 0) // 30,
        'age_years': max((today - version['release_date']).days // 365, 0),
    }


def annotated_versions(today=None):
    return [annotate(v, today) for v in ODOO_VERSIONS]
