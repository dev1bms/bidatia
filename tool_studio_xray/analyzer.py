"""Studio X-Ray analyzer — pure Python, no Django/ORM imports.

Takes the normalized inventory dict produced by collector.collect() (or any
future collector emitting the same schema) and produces findings with
severities, aggregate totals and a per-model customization breakdown.
Fully unit-testable with fixture JSON files.

Report v2 additions (all optional/backward-compatible): installed-module
classification, upgrade-readiness assessment and an executive-summary
structure. These emit CODES and NUMBERS only — human wording (and its
translation) happens at the view layer.
"""
import re
from collections import defaultdict

SEVERITY_INFO = 'info'
SEVERITY_WARNING = 'warning'
SEVERITY_CRITICAL = 'critical'

# Core business models where Studio customizations carry the highest upgrade
# risk: standard upgrade scripts and module updates touch these constantly.
CORE_MODELS = frozenset({
    'res.partner',
    'sale.order', 'sale.order.line',
    'account.move', 'account.move.line',
    'purchase.order', 'purchase.order.line',
    'stock.picking', 'stock.move', 'stock.quant',
    'product.template', 'product.product',
    'crm.lead',
    'mrp.production', 'mrp.bom',
    'hr.employee',
    'project.task', 'project.project',
    'pos.order',
})

MAX_EXAMPLES = 20


def analyze(inventory):
    """Return {'findings', 'totals', 'model_breakdown', 'sections_with_errors'}."""
    sections = inventory.get('sections') or {}
    errors = sorted(
        name for name, sec in sections.items()
        if isinstance(sec, dict) and 'error' in sec
    )

    field_items = _items(sections, 'studio_fields')
    field_total = _total(sections, 'studio_fields', field_items)
    model_items = _items(sections, 'custom_models')
    view_items = _items(sections, 'studio_views')
    view_total = _total(sections, 'studio_views', view_items)
    auto_items = _items(sections, 'automated_actions')
    server_items = _items(sections, 'server_actions')
    menu_items = _items(sections, 'studio_menus')

    computed_fields = [f for f in field_items if f.get('has_compute') or f.get('related')]
    core_fields = [f for f in field_items if f.get('model') in CORE_MODELS]
    # Module-shipped actions (from_module=True) are part of standard Odoo /
    # installed modules — only hand-made ones are customization debt.
    # Old inventories without the flag default to the previous behavior.
    shipped_code_actions = [a for a in server_items
                            if a.get('state') == 'code' and a.get('from_module')]
    code_actions = [a for a in server_items
                    if a.get('state') == 'code' and not a.get('from_module')]
    auto_items = [a for a in auto_items if not a.get('from_module')]
    inheriting_views = [v for v in view_items if v.get('inherits')]

    findings = []

    if core_fields:
        findings.append(_finding(
            'studio_fields_on_core_models', SEVERITY_WARNING, 'studio_fields',
            'Studio fields on core business models',
            'Fields added directly to core models are the most common source of '
            'conflicts and data issues during version upgrades.',
            count=len(core_fields),
            examples=['%s.%s' % (f.get('model'), f.get('name')) for f in core_fields],
        ))

    if computed_fields:
        findings.append(_finding(
            'computed_studio_fields', SEVERITY_WARNING, 'studio_fields',
            'Computed or related Studio fields',
            'These fields carry business logic stored in the database instead of '
            'a module — standard upgrade paths do not migrate that logic.',
            count=len(computed_fields),
            examples=['%s.%s' % (f.get('model'), f.get('name')) for f in computed_fields],
        ))

    if model_items:
        findings.append(_finding(
            'custom_studio_models', SEVERITY_CRITICAL, 'custom_models',
            'Custom models created with Studio',
            'Studio (x_) models exist only in this database. Leaving Enterprise, '
            'or any clean rebuild, requires reimplementing them as a proper module.',
            count=len(model_items),
            examples=['%s (%s fields)' % (m.get('model'), m.get('field_count', 0))
                      for m in model_items],
        ))

    if code_actions:
        findings.append(_finding(
            'code_server_actions', SEVERITY_CRITICAL, 'server_actions',
            'Custom server actions executing Python code from the database',
            'Hand-made code living in database records (module-shipped actions '
            'are excluded): invisible to version control, untested, and a '
            'frequent cause of silent upgrade breakage.',
            count=len(code_actions),
            examples=[a.get('name') or '' for a in code_actions],
        ))

    if inheriting_views:
        findings.append(_finding(
            'studio_view_inheritance', SEVERITY_WARNING, 'studio_views',
            'Studio views inheriting standard views',
            'Inherited view customizations conflict with upstream view changes '
            'on every upgrade.',
            count=len(inheriting_views),
            examples=['%s (%s)' % (v.get('name'), v.get('model') or v.get('type'))
                      for v in inheriting_views],
        ))

    if auto_items:
        findings.append(_finding(
            'automated_actions_present', SEVERITY_INFO, 'automated_actions',
            'Automated actions configured in the database',
            'Worth reviewing one by one: automated actions are easy to create '
            'and easy to forget, and their interactions are rarely documented.',
            count=len(auto_items),
            examples=['%s (%s)' % (a.get('name'), a.get('trigger') or '?')
                      for a in auto_items],
        ))

    usage_summary = summarize_usage(sections)
    if usage_summary and usage_summary['critical_count']:
        findings.append(_finding(
            'business_critical_custom_models', SEVERITY_CRITICAL, 'usage',
            'Core business data lives inside Studio models',
            'These custom models hold thousands of records — they are not '
            'experiments, they ARE the business. A standard upgrade will not '
            'carry them over.',
            count=usage_summary['critical_count'],
            examples=['%s (%s records)' % (r['model'], r['records'])
                      for r in usage_summary['rows'] if r['tier'] == 'critical'],
        ))
    if usage_summary and usage_summary['dead_count']:
        findings.append(_finding(
            'dead_custom_models', SEVERITY_INFO, 'usage',
            'Empty custom models (likely abandoned experiments)',
            'Custom models with zero records can usually be deleted outright — '
            'an easy cleanup win that immediately reduces migration effort.',
            count=usage_summary['dead_count'],
            examples=usage_summary['dead_examples'],
        ))

    module_summary = summarize_modules(sections)
    if module_summary and module_summary['non_standard_total']:
        non_standard = module_summary['non_standard_total']
        severity = (SEVERITY_WARNING if non_standard >= NON_STANDARD_WARNING_THRESHOLD
                    else SEVERITY_INFO)
        examples = (module_summary['examples']['custom']
                    + module_summary['examples']['third_party']
                    + module_summary['examples']['oca'])
        findings.append(_finding(
            'non_standard_modules', severity, 'installed_modules',
            'Modules that are not standard Odoo',
            'Every community, third-party or custom module must be verified — '
            'and often upgraded or replaced — before each Odoo version migration.',
            count=non_standard,
            examples=examples,
        ))

    totals = {
        'studio_fields': field_total,
        'computed_studio_fields': len(computed_fields),
        'plain_studio_fields': max(field_total - len(computed_fields), 0),
        'core_model_fields': len(core_fields),
        'custom_models': len(model_items),
        'server_actions': len(server_items),
        'code_server_actions': len(code_actions),
        'studio_views': view_total,
        'studio_views_inheriting': len(inheriting_views),
        'automated_actions': len(auto_items),
        'studio_menus': len(menu_items),
        'non_standard_modules': module_summary['non_standard_total'] if module_summary else 0,
        # Shipped by modules — standard behavior, shown for transparency only.
        'shipped_code_server_actions': len(shipped_code_actions),
    }

    if usage_summary:
        totals['dead_custom_models'] = usage_summary['dead_count']
        totals['critical_custom_models'] = usage_summary['critical_count']

    return {
        'findings': findings,
        'totals': totals,
        'model_breakdown': _model_breakdown(field_items, view_items, auto_items),
        'sections_with_errors': errors,
        'module_summary': module_summary,  # None when the section is unavailable
        # Report v3 — all optional; None for old inventories.
        'usage_summary': usage_summary,
        'pulse': summarize_pulse(sections),
        'identity': summarize_identity(sections),
        'code_summary': summarize_code(sections, module_summary),
    }


def _items(sections, name):
    sec = sections.get(name)
    if not isinstance(sec, dict) or 'error' in sec:
        return []
    return sec.get('items') or []


def _total(sections, name, items):
    sec = sections.get(name)
    if not isinstance(sec, dict) or 'error' in sec:
        return 0
    return int(sec.get('total', len(items)) or 0)


def _finding(code, severity, section, title, detail, count, examples):
    return {
        'code': code,
        'severity': severity,
        'section': section,
        'title': title,
        'detail': detail,
        'count': count,
        'examples': examples[:MAX_EXAMPLES],
    }


def _model_breakdown(field_items, view_items, auto_items):
    """Which business areas are most customized — sorted heaviest first."""
    agg = defaultdict(lambda: {'fields': 0, 'views': 0, 'automations': 0})
    for f in field_items:
        if f.get('model'):
            agg[f['model']]['fields'] += 1
    for v in view_items:
        if v.get('model'):
            agg[v['model']]['views'] += 1
    for a in auto_items:
        model = a.get('model') or a.get('model_label')
        if model:
            agg[model]['automations'] += 1

    rows = [
        {'model': model, **counts, 'total': sum(counts.values())}
        for model, counts in agg.items()
    ]
    rows.sort(key=lambda r: (-r['total'], r['model']))
    return rows


# ── Report v2: module classification ──────────────────────────────────────────

ORIGIN_OFFICIAL = 'official'
ORIGIN_OCA = 'oca'
ORIGIN_THIRD_PARTY = 'third_party'
ORIGIN_CUSTOM = 'custom'

# A non-standard module count at/above this becomes a warning (below: info).
NON_STANDARD_WARNING_THRESHOLD = 15

# Example module names kept per origin in the stored summary.
MODULE_EXAMPLES_CAP = 6


def classify_module_author(author):
    """Rough origin classification from ir.module.module.author.

    OCA modules usually list "Odoo Community Association (OCA)" alongside the
    original author, so the OCA check must run before the official check.
    """
    text = (author or '').strip().lower()
    if not text:
        return ORIGIN_CUSTOM
    if 'odoo community association' in text or '(oca)' in text or text == 'oca':
        return ORIGIN_OCA
    if text.startswith('odoo s.a') or text in ('odoo', 'odoo sa'):
        return ORIGIN_OFFICIAL
    return ORIGIN_THIRD_PARTY


def summarize_modules(sections):
    """Build the stored module summary from the installed_modules section.

    Returns None when the section is missing or errored (old inventories,
    restricted access) — every consumer treats the summary as optional.
    """
    items = _items(sections, 'installed_modules')
    if not items:
        return None

    by_origin = {ORIGIN_OFFICIAL: 0, ORIGIN_OCA: 0, ORIGIN_THIRD_PARTY: 0, ORIGIN_CUSTOM: 0}
    examples = {ORIGIN_OCA: [], ORIGIN_THIRD_PARTY: [], ORIGIN_CUSTOM: []}
    for module in items:
        origin = classify_module_author(module.get('author'))
        by_origin[origin] += 1
        if origin in examples and len(examples[origin]) < MODULE_EXAMPLES_CAP:
            examples[origin].append(module.get('display_name') or module.get('name') or '')

    context = sections.get('module_context') or {}
    installed_total = _total(sections, 'installed_modules', items)
    if isinstance(context, dict) and 'error' not in context:
        installed_total = int(context.get('installed_modules') or installed_total)
        studio_installed = bool(context.get('studio_installed'))
    else:
        studio_installed = any(m.get('name') == 'web_studio' for m in items)

    return {
        'installed_total': installed_total,
        'studio_installed': studio_installed,
        'by_origin': by_origin,
        'non_standard_total': (by_origin[ORIGIN_OCA] + by_origin[ORIGIN_THIRD_PARTY]
                               + by_origin[ORIGIN_CUSTOM]),
        'examples': examples,
    }


# ── Report v3: usage, pulse, identity, code footprint ─────────────────────────

# A custom model holding at least this many records is business-critical.
USAGE_CRITICAL_RECORDS = 5000
MAX_USAGE_ROWS = 12
MAX_DEAD_EXAMPLES = 8

TIER_CRITICAL = 'critical'
TIER_ACTIVE = 'active'
TIER_DEAD = 'dead'


def summarize_usage(sections):
    """Usage tiers for custom models from COUNT data. None when unavailable."""
    sec = sections.get('usage')
    if not isinstance(sec, dict) or 'error' in sec:
        return None
    counted = sec.get('custom_model_records') or []
    rows = sorted(
        ({'model': r.get('model') or '', 'records': int(r.get('records') or 0)}
         for r in counted),
        key=lambda r: (-r['records'], r['model']))
    for row in rows:
        row['tier'] = (TIER_CRITICAL if row['records'] >= USAGE_CRITICAL_RECORDS
                       else TIER_ACTIVE if row['records'] else TIER_DEAD)
    dead = [r['model'] for r in rows if r['tier'] == TIER_DEAD]
    top = max((r['records'] for r in rows), default=0)
    for row in rows:
        # Pre-computed bar width (%) so the template stays logic-free.
        row['bar'] = round(row['records'] * 100 / top) if top else 0
    return {
        'rows': rows[:MAX_USAGE_ROWS],
        'counted': len(rows),
        'skipped': int(sec.get('skipped_models') or 0),
        'total_custom_records': sum(r['records'] for r in rows),
        'critical_count': sum(1 for r in rows if r['tier'] == TIER_CRITICAL),
        'active_count': sum(1 for r in rows if r['tier'] == TIER_ACTIVE),
        'dead_count': len(dead),
        'dead_examples': dead[:MAX_DEAD_EXAMPLES],
    }


def summarize_pulse(sections):
    """Operational numbers for the report's pulse section. None when nothing
    was collectable (old inventories)."""
    users = sections.get('users_pulse')
    storage = sections.get('storage')
    flags = sections.get('ops_flags')
    usage = sections.get('usage')
    parts = {}
    if isinstance(users, dict) and 'error' not in users:
        parts.update(users)
    if isinstance(storage, dict) and 'error' not in storage:
        parts.update(storage)
    if isinstance(flags, dict) and 'error' not in flags:
        parts.update(flags)
    if isinstance(usage, dict) and 'error' not in usage:
        volumes = usage.get('business_volumes') or {}
        parts['business_volumes'] = [
            {'model': model, 'records': count}
            for model, count in sorted(volumes.items(), key=lambda kv: -kv[1])
        ]
    return parts or None


def summarize_identity(sections):
    """Company/requester identity for the report header. None when missing."""
    sec = sections.get('identity')
    if not isinstance(sec, dict) or 'error' in sec:
        return None
    location = ', '.join(p for p in (sec.get('company_city'),
                                     sec.get('company_country')) if p)
    return {
        'company_name': sec.get('company_name') or '',
        'company_location': location,
        'company_logo': sec.get('company_logo') or '',
        'companies_total': int(sec.get('companies_total') or 0),
        'user_name': sec.get('user_name') or '',
        'user_login': sec.get('user_login') or '',
    }


def summarize_code(sections, module_summary=None):
    """Full-scope code footprint, joined with module origins. None unless the
    scan ran with scope='full' and the section succeeded."""
    sec = sections.get('code_customizations')
    if not isinstance(sec, dict) or 'error' in sec:
        return None
    rows = []
    for row in sec.get('modules') or []:
        counts = row.get('counts') or {}
        rows.append({
            'module': row.get('module') or '',
            'origin': row.get('origin') or 'custom',
            'models': counts.get('ir.model', 0),
            'fields': counts.get('ir.model.fields', 0),
            'views': counts.get('ir.ui.view', 0),
            'server_actions': counts.get('ir.actions.server', 0),
            'automations': counts.get('base.automation', 0),
            'crons': counts.get('ir.cron', 0),
            'reports': counts.get('ir.actions.report', 0),
            'total': int(row.get('total') or 0),
        })
    code_models = sorted(
        ({'model': r.get('model') or '', 'label': r.get('label') or '',
          'records': int(r.get('records') or 0)}
         for r in sec.get('code_model_records') or []),
        key=lambda r: -r['records'])
    for row in code_models:
        row['tier'] = (TIER_CRITICAL if row['records'] >= USAGE_CRITICAL_RECORDS
                       else TIER_ACTIVE if row['records'] else TIER_DEAD)
    return {
        'modules': rows,
        'module_count': len(rows),
        'total_items': int(sec.get('total_items') or 0),
        'code_models': code_models[:MAX_USAGE_ROWS],
        'code_model_count': len(code_models),
    }


# ── Report v2: upgrade readiness ──────────────────────────────────────────────

# Newest major Odoo version this knowledge table is aware of. Review once a
# year (Odoo releases each October). Keep wording around this careful: we talk
# about "version gap" and "expected migration friction", never exact support
# dates.
LATEST_KNOWN_MAJOR = 19

# Odoo's standard policy maintains the three most recent major versions.
SUPPORTED_MAJORS_WINDOW = 3

# friction = TABLE[gap_band][score_band]
#   gap band:   0 -> up to date, 1 -> 1-2 majors behind, 2 -> 3+ behind
#   score band: 0 -> score < 25,  1 -> 25-70,             2 -> > 70
_FRICTION_TABLE = (
    ('minimal', 'moderate', 'high'),
    ('moderate', 'moderate', 'high'),
    ('high', 'high', 'very_high'),
)


def assess_upgrade(server_version, score):
    """Version-gap assessment. Returns None when the version is unparseable —
    the report simply omits the section."""
    match = re.search(r'(\d+)', str(server_version or '').replace('saas~', ''))
    if not match:
        return None
    major = int(match.group(1))
    if major < 8:  # implausible / pre-API-key era
        return None

    gap = max(LATEST_KNOWN_MAJOR - major, 0)
    gap_band = 0 if gap == 0 else (1 if gap <= 2 else 2)
    score_band = 0 if score < 25 else (1 if score <= 70 else 2)
    return {
        'detected_version': str(server_version or ''),
        'detected_major': major,
        'latest_known_major': LATEST_KNOWN_MAJOR,
        'gap': gap,
        'within_support_window': gap < SUPPORTED_MAJORS_WINDOW,
        'friction': _FRICTION_TABLE[gap_band][score_band],
    }


# ── Report v2: executive summary (codes only — wording lives in the view) ─────

# Risk codes in boardroom priority order; the summary surfaces the top 3.
_RISK_PRIORITY = (
    'custom_studio_models',
    'code_server_actions',
    'version_gap',
    'studio_fields_on_core_models',
    'non_standard_modules',
    'computed_studio_fields',
    'studio_view_inheritance',
    'automated_actions_present',
)

NEXT_STEP_REBUILD = 'rebuild'
NEXT_STEP_CLEANUP = 'cleanup_before_upgrade'
NEXT_STEP_REVIEW = 'targeted_review'
NEXT_STEP_HEALTHY = 'healthy'

MAX_SUMMARY_RISKS = 3


def build_executive_summary(findings, score, upgrade=None, module_summary=None):
    """Top risks + recommended next step, derived purely from existing data.

    Works for OLD reports too: findings and score exist in every stored
    result_json; upgrade/module_summary are optional extras.
    """
    by_code = {f.get('code'): f for f in (findings or [])}

    candidates = {}
    for code, finding in by_code.items():
        candidates[code] = int(finding.get('count') or 0)
    if upgrade and upgrade.get('gap', 0) >= 2:
        candidates['version_gap'] = upgrade['gap']
    # Only headline the module risk when it is substantial.
    if 'non_standard_modules' in candidates and candidates['non_standard_modules'] < 10:
        del candidates['non_standard_modules']

    risks = [
        {'code': code, 'count': candidates[code]}
        for code in _RISK_PRIORITY if code in candidates
    ][:MAX_SUMMARY_RISKS]

    if 'custom_studio_models' in by_code or 'code_server_actions' in by_code:
        next_step = NEXT_STEP_REBUILD
    elif score >= 41 or (upgrade and upgrade.get('gap', 0) >= 2):
        next_step = NEXT_STEP_CLEANUP
    elif by_code:
        next_step = NEXT_STEP_REVIEW
    else:
        next_step = NEXT_STEP_HEALTHY

    return {'risks': risks, 'next_step': next_step}
