"""Data Risk Profiler collector — read-only, count-first, privacy-safe.

Emits the normalized dict the analyzer consumes:

    {
      "meta": {...},
      "sections": {
        "<name>": {...metrics...}          # success
        "<name>": {"error": "<safe msg>"}  # failure (scan continues)
        "<name>": {"skipped": True}        # model/app not installed
      }
    }

Strategy (docs/data_risk_profiler/HEURISTICS.md):
- search_count with explicit domains for almost everything, including
  dotted domains for functional-orphan checks;
- read_group only where cardinality is bounded (attachments per model);
- duplicate clustering on bounded search_read samples, normalized and
  MASKED in this module — raw values never leave this process;
- a missing/unreadable model marks its section skipped/errored, never
  sinks the run. Stays well inside the connector's 200-call budget.
"""
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from tools_core.connectors.base import ConnectorError

from .masking import mask_code, mask_email, mask_text, mask_vat

SCHEMA_VERSION = 1
SAMPLE_LIMIT = 2000
MAX_EXAMPLES = 3
MAX_CUSTOM_MODELS = 15
OLD_DOCUMENT_DAYS = 365
OLD_DRAFT_MOVE_DAYS = 180

# Placeholder-looking names: each pattern costs one search_count.
PLACEHOLDER_PATTERNS = ('test%', 'unknown', 'n/a', 'xxx%')

# Master-data models whose External-ID coverage we measure.
XID_MODELS = ('res.partner', 'product.template', 'product.product',
              'product.category', 'account.tax')

# Applied AFTER punctuation stripping, so dotted forms arrive spaced
# ("S.L." → "s l") — the patterns allow the inner space.
_LEGAL_SUFFIXES = re.compile(
    r'\b(s ?l ?u?|s ?a ?u?|ltd|llc|gmbh|srl|bv|inc|co)$', re.I)


def collect(connector, connection_info=None):
    meta = {
        'schema_version': SCHEMA_VERSION,
        'tool': 'data_risk',
        'collected_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'server_version': getattr(connection_info, 'server_version', '') or '',
        'edition': getattr(connection_info, 'edition', '') or '',
        'db_name': getattr(connection_info, 'db_name', '') or '',
    }

    available = _available_models(connector)
    sections = {}
    for name, builder, required_model in SECTION_BUILDERS:
        if required_model and required_model not in available:
            sections[name] = {'skipped': True}
            continue
        try:
            sections[name] = builder(connector, available)
        except ConnectorError as exc:
            sections[name] = {'error': str(exc)}  # pre-sanitized
        except Exception:  # noqa: BLE001 — a section must never sink the run
            sections[name] = {'error': 'Unexpected error while collecting this section.'}

    return {'meta': meta, 'sections': sections}


def _available_models(connector):
    """One query resolving which optional models exist in this database."""
    candidates = ['res.partner', 'product.template', 'product.product',
                  'product.category', 'sale.order', 'sale.order.line',
                  'purchase.order', 'crm.lead', 'account.move', 'account.tax',
                  'account.fiscal.position', 'ir.attachment', 'ir.model.data',
                  'res.users', 'res.currency', 'res.company', 'ir.model']
    try:
        rows = connector.search_read(
            'ir.model', [('model', 'in', candidates)], ['model'],
            limit=len(candidates))
        return {r['model'] for r in rows if r.get('model')}
    except Exception:  # noqa: BLE001 — assume the core trio at minimum
        return {'res.partner', 'ir.model.data', 'res.users'}


# ── normalization (in-memory only) ───────────────────────────────────────────

def _norm_email(value):
    return str(value or '').strip().lower()


def _norm_name(value):
    text = re.sub(r'[^\w\s]', ' ', str(value or '').lower(), flags=re.UNICODE)
    text = ' '.join(text.split())
    return _LEGAL_SUFFIXES.sub('', text).strip()


def _norm_vat(value):
    return re.sub(r'[^A-Za-z0-9]', '', str(value or '')).upper()


def _norm_phone(value):
    digits = re.sub(r'\D', '', str(value or ''))
    return digits[-9:] if len(digits) >= 7 else ''


def _clusters(rows, key_fn, mask_fn, value_field):
    """Group sample rows by normalized key; return cluster metrics with
    MASKED examples only."""
    groups = defaultdict(list)
    for row in rows:
        key = key_fn(row.get(value_field))
        if key:
            groups[key].append(row)
    dup_groups = [members for members in groups.values() if len(members) > 1]
    affected = sum(len(m) for m in dup_groups)
    examples = [mask_fn(members[0].get(value_field))
                for members in sorted(dup_groups, key=len, reverse=True)[:MAX_EXAMPLES]]
    return {'clusters': len(dup_groups), 'affected': affected,
            'examples': examples}


def _cutoff(days):
    return (datetime.now(timezone.utc) - timedelta(days=days)).strftime('%Y-%m-%d')


def _stratified_sample(connector, model, domain, fields, total):
    """Duplicate-detection sample within the same budget, drawn from THREE
    id ranges (oldest / middle / newest) instead of newest-only, so old
    legacy duplicates are represented too. Returns (rows, full_coverage).

    When the table fits inside the cap entirely, one query covers 100% and
    the report can say "full coverage" honestly.
    """
    if total <= SAMPLE_LIMIT:
        rows = connector.search_read(model, domain, fields,
                                     limit=SAMPLE_LIMIT, order='id')
        return rows, True

    third = SAMPLE_LIMIT // 3
    oldest = connector.search_read(model, domain, fields,
                                   limit=third, order='id')
    newest = connector.search_read(model, domain, fields,
                                   limit=third, order='id desc')
    rows = {r.get('id'): r for r in oldest}
    rows.update({r.get('id'): r for r in newest})

    low = max((r.get('id') or 0 for r in oldest), default=0)
    high = min((r.get('id') or 0 for r in newest), default=0)
    if high > low + 1:
        middle = connector.search_read(
            model, domain + [('id', '>', low), ('id', '<', high)],
            fields, limit=SAMPLE_LIMIT - 2 * third, order='id')
        rows.update({r.get('id'): r for r in middle})
    return list(rows.values()), False


# ── sections ─────────────────────────────────────────────────────────────────

def _partners(connector, _available):
    total_active = connector.search_count('res.partner', [('active', '=', True)])
    sample, full = _stratified_sample(
        connector, 'res.partner', [('active', '=', True)],
        ['name', 'email', 'vat', 'phone', 'is_company'], total_active)

    companies = [r for r in sample if r.get('is_company')]
    section = {
        'total_active': total_active,
        'sample_full': full,
        'sample_coverage_pct': (100 if full or not total_active
                                else round(len(sample) * 100 / total_active)),
        'archived': connector.search_count('res.partner', [('active', '=', False)]),
        'companies': connector.search_count(
            'res.partner', [('active', '=', True), ('is_company', '=', True)]),
        'sample_size': len(sample),
        'dup_email': _clusters(sample, _norm_email, mask_email, 'email'),
        'dup_vat': _clusters(companies, _norm_vat, mask_vat, 'vat'),
        'dup_name': _clusters(companies, _norm_name, mask_text, 'name'),
        'dup_phone': _clusters(sample, _norm_phone, mask_text, 'phone'),
        'missing_contact': connector.search_count('res.partner', [
            ('active', '=', True), ('email', '=', False),
            ('phone', '=', False), ('mobile', '=', False)]),
        'missing_country': connector.search_count('res.partner', [
            ('active', '=', True), ('is_company', '=', True),
            ('country_id', '=', False)]),
        'companies_missing_vat': connector.search_count('res.partner', [
            ('active', '=', True), ('is_company', '=', True),
            ('vat', '=', False)]),
    }
    placeholders = 0
    for pattern in PLACEHOLDER_PATTERNS:
        placeholders += connector.search_count(
            'res.partner', [('active', '=', True), ('name', '=ilike', pattern)])
    section['placeholder_names'] = placeholders
    # phone examples would mask the NAME not the phone — drop them entirely
    section['dup_phone']['examples'] = []
    return section


def _products(connector, available):
    if 'product.product' not in available:
        return {'skipped': True}
    total_templates = connector.search_count(
        'product.template', [('active', '=', True)])
    total_variants = connector.search_count(
        'product.product', [('active', '=', True)])
    sample, full = _stratified_sample(
        connector, 'product.product', [('active', '=', True)],
        ['default_code', 'barcode'], total_variants)
    return {
        'total_templates': total_templates,
        'total_variants': total_variants,
        'sample_full': full,
        'sample_coverage_pct': (100 if full or not total_variants
                                else round(len(sample) * 100 / total_variants)),
        'archived_templates': connector.search_count(
            'product.template', [('active', '=', False)]),
        'sample_size': len(sample),
        'dup_default_code': _clusters(
            sample, lambda v: str(v or '').strip(), mask_code, 'default_code'),
        'dup_barcode': _clusters(
            sample, lambda v: str(v or '').strip(), mask_code, 'barcode'),
        'missing_default_code': connector.search_count(
            'product.product', [('active', '=', True), ('default_code', '=', False)]),
        'missing_barcode': connector.search_count(
            'product.product', [('active', '=', True), ('barcode', '=', False)]),
        'zero_priced': connector.search_count(
            'product.template', [('active', '=', True), ('list_price', '=', 0)]),
        'categories': (connector.search_count('product.category', [])
                       if 'product.category' in available else None),
    }


def _orphans(connector, available):
    section = {}
    if 'sale.order' in available:
        open_states = [('state', 'in', ['draft', 'sent', 'sale'])]
        section['open_sales'] = connector.search_count('sale.order', open_states)
        section['sales_archived_partner'] = connector.search_count(
            'sale.order', open_states + [('partner_id.active', '=', False)])
        section['old_quotations'] = connector.search_count('sale.order', [
            ('state', 'in', ['draft', 'sent']),
            ('create_date', '<', _cutoff(OLD_DOCUMENT_DAYS))])
        if 'sale.order.line' in available:
            section['so_lines_archived_product'] = connector.search_count(
                'sale.order.line', [
                    ('order_id.state', 'in', ['draft', 'sent', 'sale']),
                    ('product_id.active', '=', False)])
    if 'purchase.order' in available:
        section['open_purchases'] = connector.search_count(
            'purchase.order', [('state', 'in', ['draft', 'sent', 'purchase'])])
        section['purchases_archived_vendor'] = connector.search_count(
            'purchase.order', [
                ('state', 'in', ['draft', 'sent', 'purchase']),
                ('partner_id.active', '=', False)])
    if 'crm.lead' in available:
        section['open_leads'] = connector.search_count(
            'crm.lead', [('active', '=', True)])
        section['leads_no_partner_no_email'] = connector.search_count(
            'crm.lead', [('active', '=', True), ('partner_id', '=', False),
                         ('email_from', '=', False)])
    return section if section else {'skipped': True}


def _import_ids(connector, _available):
    coverage = {}
    for model in XID_MODELS:
        try:
            total = connector.search_count(model, [])
        except Exception:  # noqa: BLE001 — model unreadable for this user
            continue
        if total <= 0:
            continue
        xids, approximate = _xid_count(connector, model)
        coverage[model] = {'records': total, 'xids': xids,
                           'coverage_pct': round(min(xids / total, 1.0) * 100),
                           'approximate': approximate}
    return {'models': coverage} if coverage else {'skipped': True}


def _xid_count(connector, model):
    """Distinct records carrying at least one External ID.

    Preferred: read_group with a count_distinct aggregate on res_id — one
    record with several XML IDs counts once. Falls back to the v1 row count
    (flagged approximate) on older versions/permission quirks; the metric
    must never sink the section.
    """
    try:
        groups = connector.read_group(
            'ir.model.data', [('model', '=', model)],
            ['res_id:count_distinct'], ['model'])
        if groups:
            distinct = groups[0].get('res_id')
            if isinstance(distinct, int) and distinct >= 0:
                return distinct, False
    except Exception:  # noqa: BLE001 — aggregate unsupported: use fallback
        pass
    return connector.search_count('ir.model.data',
                                  [('model', '=', model)]), True


def _attachments(connector, _available):
    total = connector.search_count('ir.attachment', [])
    section = {'total': total, 'total_bytes': 0, 'top_models': []}
    if not total:
        return section
    groups = connector.read_group('ir.attachment', [], ['file_size'], ['res_model'])
    rows = []
    for group in groups or []:
        count = group.get('__count') or group.get('res_model_count') or 0
        rows.append({'model': str(group.get('res_model') or '(none)'),
                     'count': int(count),
                     'bytes': int(group.get('file_size') or 0)})
    rows.sort(key=lambda r: -r['count'])
    section['total_bytes'] = sum(r['bytes'] for r in rows)
    section['top_models'] = rows[:5]
    return section


def _accounting(connector, available):
    if 'account.move' not in available:
        return {'skipped': True}
    section = {
        'old_draft_moves': connector.search_count('account.move', [
            ('state', '=', 'draft'),
            ('create_date', '<', _cutoff(OLD_DRAFT_MOVE_DAYS))]),
        'companies': (connector.search_count('res.company', [])
                      if 'res.company' in available else None),
        'active_currencies': (connector.search_count(
            'res.currency', [('active', '=', True)])
            if 'res.currency' in available else None),
    }
    if 'account.fiscal.position' in available:
        section['fiscal_positions'] = connector.search_count(
            'account.fiscal.position', [])
    return section


def _ownership(connector, available):
    section = {
        'inactive_users': connector.search_count(
            'res.users', [('active', '=', False)]),
        'active_users': connector.search_count(
            'res.users', [('active', '=', True)]),
    }
    if 'sale.order' in available:
        section['sales_inactive_owner'] = connector.search_count('sale.order', [
            ('state', 'in', ['draft', 'sent', 'sale']),
            ('user_id', '!=', False), ('user_id.active', '=', False)])
    if 'crm.lead' in available:
        section['leads_inactive_owner'] = connector.search_count('crm.lead', [
            ('active', '=', True), ('user_id', '!=', False),
            ('user_id.active', '=', False)])
    section['partners_inactive_salesperson'] = connector.search_count(
        'res.partner', [('active', '=', True), ('user_id', '!=', False),
                        ('user_id.active', '=', False)])
    return section


def _custom_data(connector, _available):
    models = connector.search_read(
        'ir.model', [('state', '=', 'manual')], ['model', 'name'],
        limit=200, order='model')
    rows = []
    for record in models[:MAX_CUSTOM_MODELS]:
        model = record.get('model') or ''
        if not model:
            continue
        try:
            count = connector.search_count(model, [])
        except Exception:  # noqa: BLE001 — restricted custom model
            continue
        xids = connector.search_count('ir.model.data', [('model', '=', model)])
        rows.append({'model': model, 'records': count, 'xids': xids})
    return {'total_custom_models': len(models), 'models': rows}


SECTION_BUILDERS = (
    ('partners', _partners, 'res.partner'),
    ('products', _products, None),           # checks availability itself
    ('orphans', _orphans, None),
    ('import_ids', _import_ids, 'ir.model.data'),
    ('attachments', _attachments, 'ir.attachment'),
    ('accounting', _accounting, None),
    ('ownership', _ownership, 'res.users'),
    ('custom_data', _custom_data, 'ir.model'),
)
