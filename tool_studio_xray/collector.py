"""Studio X-Ray collector: read-only inventory of Odoo Studio customizations.

Produces the NORMALIZED JSON format that the analyzer consumes. This format
is a stable contract — future collectors (local script upload, direct
PostgreSQL) must emit the same shape:

    {
      "meta": {
        "schema_version": 1, "tool": "studio_xray", "collected_at": iso8601,
        "server_version": "...", "edition": "...", "db_name": "..."
      },
      "sections": {
        "<name>": {"items": [...], "total": int, ...}   # on success
        "<name>": {"error": "<safe message>"}           # on failure
      }
    }

Every query is read-only with explicit fields and limits. A failing section
records its error and collection continues — a partial report is better
than a failed run. View arch XML and compute code bodies are NOT downloaded
(only an 80-char compute preview, per the Phase 1 plan).
"""
from datetime import datetime, timedelta, timezone

from tools_core.connectors.base import ConnectorError

from .analyzer import classify_module_author

SCHEMA_VERSION = 1

# Per-call record cap; the connector enforces its own hard cap of 2000 too.
SECTION_LIMIT = 2000

COMPUTE_PREVIEW_CHARS = 80

STUDIO_FIELD_DOMAIN = ['|', ('name', 'like', 'x_studio_%'), ('state', '=', 'manual')]
STUDIO_VIEW_DOMAIN = ['|', ('name', 'like', '%studio%'), ('key', 'like', 'studio_customization%')]
SERVER_ACTION_STATES = ('code', 'object_create', 'object_write', 'multi')


def collect(connector, connection_info=None, scope='studio'):
    """Run all sections against the connector and return the normalized dict.

    `scope` — 'studio' (default, Studio/manual customizations only) or
    'full' (additionally inventories what custom Python modules ship,
    aggregated per module; source code itself is never readable over RPC).
    """
    scope = scope if scope in ('studio', 'full') else 'studio'
    meta = {
        'schema_version': SCHEMA_VERSION,
        'tool': 'studio_xray',
        'collected_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'server_version': getattr(connection_info, 'server_version', '') or '',
        'edition': getattr(connection_info, 'edition', '') or '',
        'db_name': getattr(connection_info, 'db_name', '') or '',
        'scan_scope': scope,
    }

    builders = list(SECTION_BUILDERS)
    if scope == 'full':
        builders.append(('code_customizations', _code_customizations))

    sections = {}
    for name, builder in builders:
        try:
            sections[name] = builder(connector, sections)
        except ConnectorError as exc:
            # Connector errors are already sanitized (no credentials/URLs).
            sections[name] = {'error': str(exc)}
        except Exception:  # noqa: BLE001 — a section must never sink the run
            sections[name] = {'error': 'Unexpected error while collecting this section.'}

    return {'meta': meta, 'sections': sections}


# -- sections -----------------------------------------------------------------

def _m2o_label(value):
    """Normalize an XML-RPC many2one value ([id, label] or False) to its label."""
    if isinstance(value, (list, tuple)) and len(value) == 2:
        return str(value[1])
    return ''


def _studio_fields(connector, _sections):
    records = connector.search_read(
        'ir.model.fields', STUDIO_FIELD_DOMAIN,
        ['name', 'model', 'field_description', 'ttype', 'relation',
         'required', 'store', 'related', 'compute'],
        limit=SECTION_LIMIT, order='model',
    )
    total = connector.search_count('ir.model.fields', STUDIO_FIELD_DOMAIN)
    items = [{
        'name': r.get('name') or '',
        'model': r.get('model') or '',
        'label': r.get('field_description') or '',
        'ttype': r.get('ttype') or '',
        'relation': r.get('relation') or '',
        'required': bool(r.get('required')),
        'store': bool(r.get('store')),
        'related': r.get('related') or '',
        'has_compute': bool(r.get('compute')),
        'compute_preview': str(r.get('compute') or '')[:COMPUTE_PREVIEW_CHARS],
    } for r in records]
    return {'items': items, 'total': total, 'truncated': total > len(items)}


def _custom_models(connector, _sections):
    records = connector.search_read(
        'ir.model', [('state', '=', 'manual')], ['model', 'name'],
        limit=SECTION_LIMIT, order='model',
    )
    model_names = [r['model'] for r in records if r.get('model')]
    counts = {}
    if model_names:
        groups = connector.read_group(
            'ir.model.fields', [('model', 'in', model_names)], ['model'], ['model'])
        for group in groups or []:
            # Count key differs across Odoo versions: '__count' or 'model_count'.
            counts[group.get('model')] = group.get('__count') or group.get('model_count') or 0
    items = [{
        'model': r.get('model') or '',
        'name': r.get('name') or '',
        'field_count': counts.get(r.get('model'), 0),
    } for r in records]
    return {'items': items, 'total': len(items)}


def _studio_views(connector, _sections):
    records = connector.search_read(
        'ir.ui.view', STUDIO_VIEW_DOMAIN,
        ['name', 'model', 'type', 'inherit_id', 'key'],
        limit=SECTION_LIMIT, order='model',
    )
    total = connector.search_count('ir.ui.view', STUDIO_VIEW_DOMAIN)
    items = [{
        'name': r.get('name') or '',
        'model': r.get('model') or '',
        'type': r.get('type') or '',
        'inherits': bool(r.get('inherit_id')),
        'inherit_of': _m2o_label(r.get('inherit_id')),
        'key': r.get('key') or '',
    } for r in records]
    return {'items': items, 'total': total, 'truncated': total > len(items)}


def _module_shipped_ids(connector, model, record_ids):
    """ids of records that were installed BY A MODULE (they own an XML ID in
    ir.model.data). Everything else was created by hand / Studio in this
    database. Standard Odoo ships dozens of code server actions — without
    this distinction they would all show up as false-positive findings.

    Returns None when the lookup is not possible (restricted access); the
    caller then keeps the previous behavior.
    """
    if not record_ids:
        return set()
    try:
        rows = connector.search_read(
            'ir.model.data',
            [('model', '=', model), ('res_id', 'in', list(record_ids))],
            ['res_id', 'module'], limit=SECTION_LIMIT)
    except ConnectorError:
        return None
    # '__export__' XML IDs are auto-generated on export — not module-shipped.
    return {r['res_id'] for r in rows
            if r.get('module') and r['module'] != '__export__'}


def _automated_actions(connector, _sections):
    # 'model_name' (technical name) exists on most supported versions; retry
    # without it for servers where it doesn't.
    fields = ['name', 'model_id', 'trigger', 'active', 'model_name']
    try:
        records = connector.search_read('base.automation', [], fields, limit=SECTION_LIMIT)
    except ConnectorError:
        records = connector.search_read(
            'base.automation', [], ['name', 'model_id', 'trigger', 'active'],
            limit=SECTION_LIMIT)
    shipped = _module_shipped_ids(connector, 'base.automation',
                                  [r['id'] for r in records if r.get('id')])
    items = [{
        'name': r.get('name') or '',
        'model': r.get('model_name') or '',
        'model_label': _m2o_label(r.get('model_id')),
        'trigger': r.get('trigger') or '',
        'active': bool(r.get('active')),
        'from_module': (r.get('id') in shipped) if shipped is not None else False,
    } for r in records]
    return {'items': items, 'total': len(items)}


def _server_actions(connector, _sections):
    domain = [('state', 'in', list(SERVER_ACTION_STATES))]
    try:
        records = connector.search_read(
            'ir.actions.server', domain, ['name', 'model_id', 'state', 'usage'],
            limit=SECTION_LIMIT)
    except ConnectorError:
        records = connector.search_read(
            'ir.actions.server', domain, ['name', 'model_id', 'state'],
            limit=SECTION_LIMIT)
    shipped = _module_shipped_ids(connector, 'ir.actions.server',
                                  [r['id'] for r in records if r.get('id')])
    items = [{
        'name': r.get('name') or '',
        'model_label': _m2o_label(r.get('model_id')),
        'state': r.get('state') or '',
        'usage': r.get('usage') or '',
        'from_module': (r.get('id') in shipped) if shipped is not None else False,
    } for r in records]
    return {'items': items, 'total': len(items)}


def _studio_menus(connector, sections):
    """Menus pointing at window actions on custom (x_) models — the way
    Studio exposes new apps/models in the UI."""
    custom = sections.get('custom_models') or {}
    model_names = [m['model'] for m in custom.get('items', []) if m.get('model')]
    if not model_names:
        return {'items': [], 'total': 0}

    actions = connector.search_read(
        'ir.actions.act_window', [('res_model', 'in', model_names)],
        ['id', 'name'], limit=SECTION_LIMIT)
    refs = ['ir.actions.act_window,%s' % a['id'] for a in actions if a.get('id')]
    menus = []
    if refs:
        menus = connector.search_read(
            'ir.ui.menu', [('action', 'in', refs)], ['name'], limit=SECTION_LIMIT)
    items = [{'name': m.get('name') or ''} for m in menus]
    return {'items': items, 'total': len(items)}


def _module_context(connector, _sections):
    installed = connector.search_count('ir.module.module', [('state', '=', 'installed')])
    studio = connector.search_count(
        'ir.module.module', [('name', '=', 'web_studio'), ('state', '=', 'installed')])
    return {'installed_modules': installed, 'studio_installed': bool(studio)}


def _installed_modules(connector, _sections):
    """Lightweight metadata of installed modules (Report v2). Names and
    authors only — used to classify official / OCA / third-party / custom.
    No business data is touched."""
    records = connector.search_read(
        'ir.module.module', [('state', '=', 'installed')],
        ['name', 'shortdesc', 'author'],
        limit=SECTION_LIMIT, order='name',
    )
    items = [{
        'name': r.get('name') or '',
        'display_name': r.get('shortdesc') or '',
        'author': r.get('author') or '',
    } for r in records]
    return {'items': items, 'total': len(items)}


# ── Report v3 sections ────────────────────────────────────────────────────────

# Identity: who/where this database belongs to. Counts and names only —
# plus the small web logo so the report header can carry the client's brand.
MAX_LOGO_CHARS = 200_000

# Usage pulse: how many record COUNTS we are willing to run (count queries
# only — record contents are never read; "we count, we don't read").
USAGE_MODEL_CAP = 60

# Core business volumes worth showing on the report (translated at the view).
BUSINESS_VOLUME_MODELS = [
    'res.partner', 'sale.order', 'account.move', 'purchase.order',
    'stock.picking', 'crm.lead', 'project.task', 'mrp.production',
    'mail.message',
]

# What a custom module typically ships, tracked through ir.model.data.
CODE_TRACKED_MODELS = [
    'ir.model', 'ir.model.fields', 'ir.ui.view', 'ir.actions.server',
    'base.automation', 'ir.cron', 'ir.actions.report',
]
CODE_MODULES_CAP = 40
CODE_MODEL_RECORDS_CAP = 30


def _identity(connector, _sections):
    """Connected user + their company (name/place/logo) + company count."""
    uid = getattr(connector, '_uid', None)
    user = {}
    if uid:
        rows = connector.search_read(
            'res.users', [('id', '=', uid)], ['name', 'login', 'company_id'], limit=1)
        user = rows[0] if rows else {}

    company_ref = user.get('company_id')
    company_id = company_ref[0] if isinstance(company_ref, (list, tuple)) else None
    domain = [('id', '=', company_id)] if company_id else []
    company = {}
    rows = connector.search_read(
        'res.company', domain, ['name', 'street', 'city', 'country_id'], limit=1)
    if rows:
        company = rows[0]

    logo = ''
    try:
        logo_rows = connector.search_read(
            'res.company', [('id', '=', company.get('id') or 0)], ['logo_web'], limit=1)
        if logo_rows:
            candidate = logo_rows[0].get('logo_web')
            if isinstance(candidate, str) and 0 < len(candidate) <= MAX_LOGO_CHARS:
                logo = candidate
    except ConnectorError:
        pass  # restricted binary access — the header simply has no logo

    return {
        'user_name': user.get('name') or '',
        'user_login': user.get('login') or '',
        'company_name': company.get('name') or '',
        'company_street': company.get('street') or '',
        'company_city': company.get('city') or '',
        'company_country': _m2o_label(company.get('country_id')),
        'company_logo': logo,
        'companies_total': connector.search_count('res.company', []),
    }


def _usage(connector, sections):
    """Record counts: per custom model (usage tiers) + core business volumes.
    COUNT queries only — no record content ever leaves the database."""
    custom = [m['model'] for m in
              (sections.get('custom_models') or {}).get('items', [])
              if m.get('model')]
    counted, skipped = [], 0
    for model in custom[:USAGE_MODEL_CAP]:
        try:
            counted.append({'model': model,
                            'records': int(connector.search_count(model, []) or 0)})
        except ConnectorError:
            skipped += 1
    skipped += max(len(custom) - USAGE_MODEL_CAP, 0)

    volumes = {}
    for model in BUSINESS_VOLUME_MODELS:
        try:
            volumes[model] = int(connector.search_count(model, []) or 0)
        except ConnectorError:
            continue  # model not installed or not readable — skip silently

    return {'custom_model_records': counted, 'skipped_models': skipped,
            'business_volumes': volumes}


def _users_pulse(connector, _sections):
    """Seats and activity: internal vs portal users, active in 30 days."""
    internal = connector.search_count('res.users', [('share', '=', False)])
    try:
        portal = connector.search_count('res.users', [('share', '=', True)])
    except ConnectorError:
        portal = 0
    cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).strftime('%Y-%m-%d %H:%M:%S')
    try:
        active_30d = connector.search_count(
            'res.users', [('share', '=', False), ('login_date', '>=', cutoff)])
    except ConnectorError:
        active_30d = None  # login_date unreadable on some setups
    return {'internal_users': internal, 'portal_users': portal,
            'active_users_30d': active_30d}


def _storage(connector, _sections):
    """Attachment footprint — a useful database-size proxy."""
    groups = connector.read_group('ir.attachment', [], ['file_size'], [])
    row = (groups or [{}])[0] or {}
    return {'attachments': int(row.get('__count') or 0),
            'attachment_bytes': int(row.get('file_size') or 0)}


def _ops_flags(connector, _sections):
    """Operational red flags: disabled scheduled jobs, stuck outgoing mail."""
    flags = {}
    try:
        flags['crons_active'] = connector.search_count('ir.cron', [])
        flags['crons_disabled'] = connector.search_count('ir.cron', [('active', '=', False)])
    except ConnectorError:
        pass
    try:
        flags['stuck_mails'] = connector.search_count('mail.mail', [('state', '=', 'exception')])
    except ConnectorError:
        pass
    return flags


def _code_customizations(connector, sections):
    """Full-scope only: what NON-OFFICIAL modules ship, aggregated per module
    via ir.model.data (one read_group per tracked model). Python source is
    not readable over RPC — this is a footprint, not a code audit."""
    modules = _items_of(sections, 'installed_modules')
    origin_by_name = {m['name']: classify_module_author(m.get('author'))
                      for m in modules if m.get('name')}
    non_official = {name for name, origin in origin_by_name.items()
                    if origin != 'official'}
    if not non_official:
        return {'modules': [], 'code_model_records': [], 'total_items': 0}

    per_module = {}
    for tracked in CODE_TRACKED_MODELS:
        try:
            groups = connector.read_group(
                'ir.model.data',
                [('model', '=', tracked), ('module', 'in', sorted(non_official))],
                ['module'], ['module'])
        except ConnectorError:
            continue
        for group in groups or []:
            module = group.get('module')
            count = int(group.get('__count') or group.get('module_count') or 0)
            if module and count:
                per_module.setdefault(module, {})[tracked] = count

    rows = [{'module': name,
             'origin': origin_by_name.get(name, 'custom'),
             'counts': counts,
             'total': sum(counts.values())}
            for name, counts in per_module.items()]
    rows.sort(key=lambda r: (-r['total'], r['module']))
    rows = rows[:CODE_MODULES_CAP]

    # Models DEFINED by custom-origin modules, with record counts — the same
    # usage lens the Studio models get.
    code_models = []
    custom_modules = sorted(n for n in per_module
                            if origin_by_name.get(n) == 'custom')
    if custom_modules:
        try:
            refs = connector.search_read(
                'ir.model.data',
                [('model', '=', 'ir.model'), ('module', 'in', custom_modules)],
                ['res_id'], limit=SECTION_LIMIT)
            model_ids = [r['res_id'] for r in refs if r.get('res_id')]
            if model_ids:
                model_rows = connector.search_read(
                    'ir.model', [('id', 'in', model_ids)], ['model', 'name'],
                    limit=CODE_MODEL_RECORDS_CAP)
                for row in model_rows:
                    name = row.get('model') or ''
                    if not name or name.startswith('ir.') or name.startswith('base.'):
                        continue
                    try:
                        code_models.append({
                            'model': name, 'label': row.get('name') or '',
                            'records': int(connector.search_count(name, []) or 0)})
                    except ConnectorError:
                        continue
        except ConnectorError:
            pass

    return {'modules': rows,
            'code_model_records': code_models,
            'total_items': sum(r['total'] for r in rows)}


def _items_of(sections, name):
    sec = sections.get(name)
    if not isinstance(sec, dict) or 'error' in sec:
        return []
    return sec.get('items') or []


SECTION_BUILDERS = [
    ('studio_fields', _studio_fields),
    ('custom_models', _custom_models),
    ('studio_views', _studio_views),
    ('automated_actions', _automated_actions),
    ('server_actions', _server_actions),
    ('studio_menus', _studio_menus),
    ('module_context', _module_context),
    ('installed_modules', _installed_modules),
    ('identity', _identity),
    ('usage', _usage),
    ('users_pulse', _users_pulse),
    ('storage', _storage),
    ('ops_flags', _ops_flags),
]
