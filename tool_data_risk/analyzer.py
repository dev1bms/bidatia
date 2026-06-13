"""Data Risk Profiler analyzer — pure Python, no Django imports.

Consumes the collector's normalized dict and produces deterministic
categories, issues, scores and the overall risk band. Codes and numbers
only — every human sentence (and its translation) lives in the view layer.

Scoring contract: docs/data_risk_profiler/HEURISTICS.md. Higher score =
higher risk (same direction as the ERP Rescue score).
"""

CATEGORY_WEIGHTS = {
    'duplicates': 0.20,
    'missing_data': 0.15,
    'orphans': 0.20,
    'import_ids': 0.10,
    'config': 0.10,
    'attachments': 0.05,
    'ownership': 0.10,
    'custom_data': 0.10,
}

LEVEL_LOW = 'low'
LEVEL_MODERATE = 'moderate'
LEVEL_HIGH = 'high'
LEVEL_CRITICAL = 'critical'

SEVERITY_OK = 'ok'
SEVERITY_INFO = 'info'
SEVERITY_WARNING = 'warning'
SEVERITY_CRITICAL = 'critical'

_SEVERITY_RANK = {SEVERITY_OK: 0, SEVERITY_INFO: 1,
                  SEVERITY_WARNING: 2, SEVERITY_CRITICAL: 3}

MAX_BLOCKERS = 5

# Attachment thresholds (count, bytes) under which bloat scores zero.
ATTACH_BASE_COUNT = 5000
ATTACH_BASE_BYTES = 2 * 1024 ** 3

# A manual model holding at least this many records is "heavy" master data.
CUSTOM_HEAVY_RECORDS = 1000


def analyze(collected):
    """Returns {'categories': [...], 'score', 'level', 'blockers',
    'skipped_sections', 'error_sections'}."""
    sections = (collected or {}).get('sections') or {}

    categories = []
    for code, builder in _CATEGORY_BUILDERS:
        section_state = _section_state(sections, _CATEGORY_SECTIONS[code])
        if section_state != 'ok':
            categories.append({'code': code, 'state': section_state,
                               'score': None, 'severity': SEVERITY_OK,
                               'metrics': [], 'issues': []})
            continue
        category = builder(sections)
        category['code'] = code
        category['state'] = 'ok'
        category['score'] = _clamp(category['score'])
        category['severity'] = _severity(category['score'])
        categories.append(category)

    score = _overall(categories)
    return {
        'categories': categories,
        'score': score,
        'level': _level(score),
        'blockers': _blockers(categories),
        'skipped_sections': sorted(
            name for name, sec in sections.items()
            if isinstance(sec, dict) and sec.get('skipped')),
        'error_sections': sorted(
            name for name, sec in sections.items()
            if isinstance(sec, dict) and 'error' in sec),
    }


def _section_state(sections, names):
    """'ok' if every backing section is usable, else skipped/error."""
    for name in names:
        sec = sections.get(name)
        if not isinstance(sec, dict) or 'error' in sec:
            return 'error'
        if sec.get('skipped'):
            return 'skipped'
    return 'ok'


def _clamp(value):
    return max(0, min(100, round(value)))


def _severity(score):
    if score >= 70:
        return SEVERITY_CRITICAL
    if score >= 40:
        return SEVERITY_WARNING
    if score >= 20:
        return SEVERITY_INFO
    return SEVERITY_OK


def _level(score):
    if score >= 85:
        return LEVEL_CRITICAL
    if score >= 70:
        return LEVEL_HIGH
    if score >= 40:
        return LEVEL_MODERATE
    return LEVEL_LOW


def _overall(categories):
    total = weight_sum = 0.0
    for category in categories:
        if category['score'] is None:
            continue
        weight = CATEGORY_WEIGHTS[category['code']]
        total += category['score'] * weight
        weight_sum += weight
    return _clamp(total / weight_sum) if weight_sum else 0


def _pct(part, whole):
    return round(part * 100.0 / whole, 1) if whole else 0.0


def _issue(code, count, severity, pct=None, examples=None):
    issue = {'code': code, 'count': int(count or 0), 'severity': severity}
    if pct is not None:
        issue['pct'] = pct
    if examples:
        issue['examples'] = list(examples)[:3]
    return issue


def _blockers(categories):
    issues = []
    for category in categories:
        for issue in category['issues']:
            if issue['count'] > 0 and issue['severity'] != SEVERITY_OK:
                issues.append({**issue, 'category': category['code']})
    issues.sort(key=lambda i: (-_SEVERITY_RANK[i['severity']], -i['count']))
    return issues[:MAX_BLOCKERS]


# ── category builders ────────────────────────────────────────────────────────

def _duplicates(sections):
    partners = sections['partners']
    products = sections.get('products') or {}
    sample = partners.get('sample_size') or 0
    psample = products.get('sample_size') or 0

    signals, issues = [], []
    for key, source, total, examples_ok in (
            ('dup_email', partners, sample, True),
            ('dup_name', partners, sample, True),
            ('dup_vat', partners, sample, True),
            ('dup_phone', partners, sample, False),
            ('dup_default_code', products, psample, True),
            ('dup_barcode', products, psample, True)):
        cluster = source.get(key)
        if not cluster or not total:
            continue
        pct = _pct(cluster['affected'], total)
        signals.append(min(100.0, pct * 4))
        if cluster['clusters']:
            severity = SEVERITY_WARNING if pct >= 2 else SEVERITY_INFO
            issues.append(_issue(key, cluster['affected'], severity, pct=pct,
                                 examples=cluster.get('examples') if examples_ok else None))

    score = (sum(signals) / len(signals)) if signals else 0
    if (partners.get('dup_vat') or {}).get('clusters'):
        score += 10  # duplicated tax identity is a stronger signal

    return {
        'score': score,
        'issues': issues,
        'metrics': [
            {'code': 'partners_sampled', 'value': sample},
            {'code': 'partners_coverage_pct',
             'value': partners.get('sample_coverage_pct')},
            {'code': 'products_sampled', 'value': psample},
            {'code': 'products_coverage_pct',
             'value': products.get('sample_coverage_pct')},
        ],
    }


def _missing_data(sections):
    partners = sections['partners']
    products = sections.get('products') or {}
    total = partners.get('total_active') or 0
    companies = partners.get('companies') or 0
    variants = products.get('total_variants') or 0

    checks = [
        ('partners_missing_contact', partners.get('missing_contact', 0), total),
        ('companies_missing_vat', partners.get('companies_missing_vat', 0), companies),
        ('companies_missing_country', partners.get('missing_country', 0), companies),
        ('products_missing_code', products.get('missing_default_code', 0), variants),
        ('products_zero_priced', products.get('zero_priced', 0),
         products.get('total_templates') or 0),
    ]
    issues, pcts = [], []
    for code, count, whole in checks:
        if not whole:
            continue
        pct = _pct(count, whole)
        pcts.append(min(100.0, pct * 2))
        if count:
            severity = SEVERITY_WARNING if pct >= 20 else SEVERITY_INFO
            issues.append(_issue(code, count, severity, pct=pct))

    placeholders = partners.get('placeholder_names') or 0
    score = (sum(pcts) / len(pcts) if pcts else 0) + min(15, placeholders)
    if placeholders:
        issues.append(_issue('placeholder_names', placeholders, SEVERITY_INFO))

    return {'score': score, 'issues': issues, 'metrics': [
        {'code': 'partners_total', 'value': total},
        {'code': 'companies_total', 'value': companies},
    ]}


def _orphans(sections):
    data = sections['orphans']
    open_sales = data.get('open_sales') or 0
    open_purchases = data.get('open_purchases') or 0
    open_leads = data.get('open_leads') or 0

    checks = [
        ('sales_archived_partner', data.get('sales_archived_partner', 0),
         open_sales, SEVERITY_WARNING),
        ('so_lines_archived_product', data.get('so_lines_archived_product', 0),
         open_sales, SEVERITY_WARNING),
        ('purchases_archived_vendor', data.get('purchases_archived_vendor', 0),
         open_purchases, SEVERITY_WARNING),
        ('leads_no_partner_no_email', data.get('leads_no_partner_no_email', 0),
         open_leads, SEVERITY_INFO),
        ('old_quotations', data.get('old_quotations', 0), open_sales,
         SEVERITY_INFO),
    ]
    issues, pct_sum = [], 0.0
    for code, count, whole, severity in checks:
        if count is None:
            continue
        pct = _pct(count, whole) if whole else 0.0
        pct_sum += pct
        if count:
            issues.append(_issue(code, count, severity, pct=pct))

    return {'score': min(100.0, pct_sum * 3), 'issues': issues, 'metrics': [
        {'code': 'open_sales', 'value': open_sales},
        {'code': 'open_purchases', 'value': open_purchases},
    ]}


def _import_ids(sections):
    models = sections['import_ids'].get('models') or {}
    issues, coverages, metrics = [], [], []
    for model, row in sorted(models.items()):
        coverage = row.get('coverage_pct') or 0
        coverages.append(coverage)
        metrics.append({'code': 'xid_coverage', 'model': model,
                        'value': coverage, 'records': row.get('records', 0)})
        if coverage < 20 and row.get('records', 0) >= 100:
            issues.append(_issue(
                'low_xid_coverage', row['records'] - row.get('xids', 0),
                SEVERITY_INFO, pct=100 - coverage))

    mean_coverage = (sum(coverages) / len(coverages)) if coverages else 100
    # Capped under 50 on purpose: missing XIDs are normal for UI-created
    # data — this measures re-import/update-mapping friction, not defects.
    return {'score': (100 - mean_coverage) * 0.45,
            'issues': issues, 'metrics': metrics}


def _config(sections):
    accounting = sections.get('accounting') or {}
    products = sections.get('products') or {}
    issues = []
    triggers = 0

    companies = accounting.get('companies')
    currencies = accounting.get('active_currencies')
    if companies == 1 and (currencies or 0) > 3:
        triggers += 1
        issues.append(_issue('many_currencies_single_company',
                             currencies, SEVERITY_INFO))
    categories = products.get('categories')
    if categories is not None and categories <= 1 and \
            (products.get('total_templates') or 0) > 100:
        triggers += 1
        issues.append(_issue('uncategorized_catalog',
                             products.get('total_templates') or 0,
                             SEVERITY_INFO))
    old_drafts = accounting.get('old_draft_moves') or 0
    if old_drafts:
        triggers += 1
        issues.append(_issue('old_draft_moves', old_drafts, SEVERITY_INFO))

    return {'score': triggers * 15, 'issues': issues, 'metrics': [
        {'code': 'companies', 'value': companies},
        {'code': 'active_currencies', 'value': currencies},
        {'code': 'fiscal_positions', 'value': accounting.get('fiscal_positions')},
    ]}


def _attachments(sections):
    data = sections['attachments']
    total = data.get('total') or 0
    total_bytes = data.get('total_bytes') or 0

    score = 0
    over = max(total / ATTACH_BASE_COUNT if ATTACH_BASE_COUNT else 0,
               total_bytes / ATTACH_BASE_BYTES if ATTACH_BASE_BYTES else 0)
    while over >= 1 and score < 80:
        score += 20
        over /= 2

    issues = []
    if score >= 20:
        issues.append(_issue('attachment_bloat', total,
                             SEVERITY_INFO if score < 60 else SEVERITY_WARNING))
    return {'score': score, 'issues': issues, 'metrics': [
        {'code': 'attachments_total', 'value': total},
        {'code': 'attachments_bytes', 'value': total_bytes},
        {'code': 'attachments_top_models', 'value': data.get('top_models') or []},
    ]}


def _ownership(sections):
    data = sections['ownership']
    checks = [
        ('sales_inactive_owner', data.get('sales_inactive_owner'),
         (sections.get('orphans') or {}).get('open_sales') or 0),
        ('leads_inactive_owner', data.get('leads_inactive_owner'),
         (sections.get('orphans') or {}).get('open_leads') or 0),
        ('partners_inactive_salesperson',
         data.get('partners_inactive_salesperson'),
         (sections.get('partners') or {}).get('total_active') or 0),
    ]
    issues, pct_sum = [], 0.0
    for code, count, whole in checks:
        if count is None:
            continue
        pct = _pct(count, whole) if whole else 0.0
        pct_sum += pct
        if count:
            issues.append(_issue(code, count,
                                 SEVERITY_WARNING if pct >= 10 else SEVERITY_INFO,
                                 pct=pct))
    return {'score': min(100.0, pct_sum * 5), 'issues': issues, 'metrics': [
        {'code': 'inactive_users', 'value': data.get('inactive_users') or 0},
        {'code': 'active_users', 'value': data.get('active_users') or 0},
    ]}


def _custom_data(sections):
    data = sections['custom_data']
    rows = data.get('models') or []
    heavy_without_ids = [
        r for r in rows
        if r.get('records', 0) >= CUSTOM_HEAVY_RECORDS
        and r.get('xids', 0) < r.get('records', 0) * 0.2
    ]
    issues = []
    if heavy_without_ids:
        issues.append(_issue(
            'custom_master_data_no_ids',
            sum(r['records'] for r in heavy_without_ids),
            SEVERITY_WARNING))
    return {'score': min(80, len(heavy_without_ids) * 20), 'issues': issues,
            'metrics': [
                {'code': 'custom_models', 'value': data.get('total_custom_models') or 0},
                {'code': 'custom_heavy_models',
                 'value': [{'model': r['model'], 'records': r['records']}
                           for r in heavy_without_ids[:5]]},
            ]}


_CATEGORY_BUILDERS = (
    ('duplicates', _duplicates),
    ('missing_data', _missing_data),
    ('orphans', _orphans),
    ('import_ids', _import_ids),
    ('config', _config),
    ('attachments', _attachments),
    ('ownership', _ownership),
    ('custom_data', _custom_data),
)

_CATEGORY_SECTIONS = {
    'duplicates': ('partners',),
    'missing_data': ('partners',),
    'orphans': ('orphans',),
    'import_ids': ('import_ids',),
    'config': (),               # built from optional pieces, always renders
    'attachments': ('attachments',),
    'ownership': ('ownership',),
    'custom_data': ('custom_data',),
}
