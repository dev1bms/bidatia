"""Data Risk Profiler — views and ALL human wording (translated).

The analyzer emits codes and numbers only; every sentence a visitor reads
is defined here, mirroring the ERP Rescue pattern. Stored payloads contain
masked examples only (see docs/data_risk_profiler/PRIVACY_MODEL.md).
"""
from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from tools_core.models import ToolRun
from tools_core.services.analytics import track
from tools_core.services.hot_leads import alert_hot_lead
from tools_core.services.lead_service import capture_lead
from tools_core.utils import client_ip, rate_limit_exceeded

from .forms import DataRiskRunForm
from .tasks import run_data_risk_scan

TOOL_SLUG = 'data_risk'
RUNS_PER_EMAIL_PER_DAY = 3
RUNS_PER_IP_PER_DAY = 5
PROGRESS_STEPS = ('connecting', 'collecting', 'analyzing')

from datetime import timedelta  # noqa: E402

STALE_PENDING_AFTER = timedelta(minutes=5)

LEVEL_LABELS = {
    'low': gettext_lazy('Low data migration risk'),
    'moderate': gettext_lazy('Moderate risk'),
    'high': gettext_lazy('High risk'),
    'critical': gettext_lazy('Critical cleanup needed'),
}

LEVEL_BLURBS = {
    'low': gettext_lazy('Your master data looks largely migration-ready. Review the flagged items below and keep the habits that got you here.'),
    'moderate': gettext_lazy('Workable, but several areas will create friction during import and mapping. Cleaning them before the migration starts is much cheaper than during it.'),
    'high': gettext_lazy('Multiple data areas carry real migration risk. Plan a cleanup sprint before committing to a migration timeline.'),
    'critical': gettext_lazy('This profile matches projects where data issues dominate the migration budget. A structured cleanup phase should come before any migration work.'),
}

CATEGORY_LABELS = {
    'duplicates': gettext_lazy('Duplicate risk'),
    'missing_data': gettext_lazy('Missing master data'),
    'orphans': gettext_lazy('Relationship & orphan risk'),
    'import_ids': gettext_lazy('Import identifier coverage'),
    'config': gettext_lazy('Configuration & reference data'),
    'attachments': gettext_lazy('Attachments & database bloat'),
    'ownership': gettext_lazy('Inactive-user ownership'),
    'custom_data': gettext_lazy('Custom / Studio data'),
}

CATEGORY_BLURBS = {
    'duplicates': gettext_lazy('Potential duplicate clusters in partners and products. Ambiguous names also break many2one matching during import.'),
    'missing_data': gettext_lazy('Records missing the fields imports and daily operations rely on: contact details, VAT numbers, countries, internal references.'),
    'orphans': gettext_lazy('Live documents pointing at archived partners, archived products or abandoned pipelines — mapping hazards during migration.'),
    'import_ids': gettext_lazy('External-ID coverage of master data. Missing IDs are normal for UI-created records, but they make repeat imports and update-imports duplicate-prone.'),
    'config': gettext_lazy('Reference-data signals worth a look before migrating: currencies, categories, long-lived draft entries.'),
    'attachments': gettext_lazy('Attachment volume drives database size — and database size drives upgrade, rehearsal and restore times.'),
    'ownership': gettext_lazy('Active records owned by deactivated users lose their workflows quietly and confuse assignment after migration.'),
    'custom_data': gettext_lazy('Custom (Studio) models holding significant data without stable identifiers — they will not map themselves.'),
}

CATEGORY_SHORT = {
    'duplicates': gettext_lazy('Duplicates'),
    'missing_data': gettext_lazy('Missing data'),
    'orphans': gettext_lazy('Orphans'),
    'import_ids': gettext_lazy('Import IDs'),
    'config': gettext_lazy('Config'),
    'attachments': gettext_lazy('Attachments'),
    'ownership': gettext_lazy('Ownership'),
    'custom_data': gettext_lazy('Custom data'),
}

ISSUE_LINES = {
    'dup_email': gettext_lazy('%(n)s sampled contacts share an email with another contact'),
    'dup_name': gettext_lazy('%(n)s sampled companies have near-identical names'),
    'dup_vat': gettext_lazy('%(n)s sampled companies share a VAT number'),
    'dup_phone': gettext_lazy('%(n)s sampled contacts share a phone number'),
    'dup_default_code': gettext_lazy('%(n)s sampled products share an internal reference'),
    'dup_barcode': gettext_lazy('%(n)s sampled products share a barcode'),
    'partners_missing_contact': gettext_lazy('%(n)s contacts have no email and no phone'),
    'companies_missing_vat': gettext_lazy('%(n)s companies have no VAT number'),
    'companies_missing_country': gettext_lazy('%(n)s companies have no country set'),
    'products_missing_code': gettext_lazy('%(n)s products have no internal reference'),
    'products_zero_priced': gettext_lazy('%(n)s active products have a zero sales price'),
    'placeholder_names': gettext_lazy('%(n)s contacts look like test/placeholder entries'),
    'sales_archived_partner': gettext_lazy('%(n)s open sales orders reference an archived customer'),
    'so_lines_archived_product': gettext_lazy('%(n)s open order lines reference an archived product'),
    'purchases_archived_vendor': gettext_lazy('%(n)s open purchase orders reference an archived vendor'),
    'leads_no_partner_no_email': gettext_lazy('%(n)s open opportunities have no customer and no email'),
    'old_quotations': gettext_lazy('%(n)s quotations have been sitting in draft/sent for over a year'),
    'low_xid_coverage': gettext_lazy('%(n)s master-data records lack a stable External ID'),
    'many_currencies_single_company': gettext_lazy('%(n)s currencies are active for a single-company setup'),
    'uncategorized_catalog': gettext_lazy('%(n)s products live in a single (or no) category'),
    'old_draft_moves': gettext_lazy('%(n)s journal entries have been in draft for over six months'),
    'attachment_bloat': gettext_lazy('%(n)s attachments are inflating the database'),
    'sales_inactive_owner': gettext_lazy('%(n)s open sales orders belong to deactivated users'),
    'leads_inactive_owner': gettext_lazy('%(n)s open opportunities belong to deactivated users'),
    'partners_inactive_salesperson': gettext_lazy('%(n)s contacts are assigned to deactivated salespeople'),
    'custom_master_data_no_ids': gettext_lazy('%(n)s records live in custom models without stable identifiers'),
}

# Cleanup plan: issue code → (stage, action). Stages: before / rehearsal / after.
CLEANUP_ACTIONS = {
    'dup_email': ('before', gettext_lazy('Review duplicate-contact clusters with the built-in merge tool — merge or mark the survivors before any export.')),
    'dup_name': ('before', gettext_lazy('Normalize company names (one spelling, one legal suffix) so many2one matching has one candidate per name.')),
    'dup_vat': ('before', gettext_lazy('Resolve shared VAT numbers first — tax identity duplicates poison invoicing after migration.')),
    'dup_default_code': ('before', gettext_lazy('Make internal references unique per product — duplicate codes break update-imports.')),
    'dup_barcode': ('before', gettext_lazy('Deduplicate barcodes; scanners and imports both assume they are unique.')),
    'partners_missing_contact': ('before', gettext_lazy('Complete or archive contacts that have no email and no phone.')),
    'companies_missing_vat': ('before', gettext_lazy('Fill VAT numbers for active companies where invoicing requires them.')),
    'products_missing_code': ('before', gettext_lazy('Assign internal references to active products — they are the natural import key.')),
    'placeholder_names': ('before', gettext_lazy('Delete or archive test/placeholder records so they never reach the new system.')),
    'sales_archived_partner': ('before', gettext_lazy('Close or re-point open orders that reference archived customers/vendors.')),
    'so_lines_archived_product': ('before', gettext_lazy('Replace archived products on open order lines, or close those orders.')),
    'old_quotations': ('before', gettext_lazy('Cancel or archive quotations older than a year — do not migrate a dead pipeline.')),
    'sales_inactive_owner': ('before', gettext_lazy('Reassign open documents owned by deactivated users to active owners.')),
    'partners_inactive_salesperson': ('before', gettext_lazy('Reassign customers of deactivated salespeople to active ones.')),
    'low_xid_coverage': ('rehearsal', gettext_lazy('Use import-compatible exports during the rehearsal so every record gets a stable External ID for later update-imports.')),
    'custom_master_data_no_ids': ('rehearsal', gettext_lazy('Export custom-model data with External IDs and test-import a small batch before trusting the mapping.')),
    'attachment_bloat': ('rehearsal', gettext_lazy('Decide what attachment history must migrate; consider offloading the rest to external storage first.')),
    'old_draft_moves': ('before', gettext_lazy('Post or delete long-lived draft journal entries with your accountant.')),
}

GENERIC_PLAN = {
    'before': gettext_lazy('Freeze new test records and agree on one source of truth per master-data area.'),
    'rehearsal': gettext_lazy('Test-import a small batch (50–100 records) per model and verify relations resolve to the right targets.'),
    'after': gettext_lazy('Reconcile record counts between systems, then re-run this profiler and compare duplicate clusters before and after.'),
}

# v2 action list: issue code → (priority, suggested owner). The stage comes
# from CLEANUP_ACTIONS; why/impact wording is shared per category.
ACTION_META = {
    'dup_email': ('high', 'business'),
    'dup_name': ('medium', 'business'),
    'dup_vat': ('high', 'accounting'),
    'dup_default_code': ('high', 'operations'),
    'dup_barcode': ('medium', 'operations'),
    'partners_missing_contact': ('medium', 'business'),
    'companies_missing_vat': ('high', 'accounting'),
    'companies_missing_country': ('low', 'business'),
    'products_missing_code': ('medium', 'operations'),
    'products_zero_priced': ('low', 'business'),
    'placeholder_names': ('low', 'business'),
    'sales_archived_partner': ('high', 'operations'),
    'so_lines_archived_product': ('high', 'operations'),
    'purchases_archived_vendor': ('medium', 'operations'),
    'leads_no_partner_no_email': ('low', 'business'),
    'old_quotations': ('low', 'business'),
    'old_draft_moves': ('medium', 'accounting'),
    'low_xid_coverage': ('medium', 'consultant'),
    'custom_master_data_no_ids': ('high', 'consultant'),
    'attachment_bloat': ('medium', 'consultant'),
    'many_currencies_single_company': ('low', 'consultant'),
    'uncategorized_catalog': ('low', 'operations'),
    'sales_inactive_owner': ('medium', 'operations'),
    'leads_inactive_owner': ('low', 'business'),
    'partners_inactive_salesperson': ('medium', 'business'),
}

OWNER_LABELS = {
    'business': gettext_lazy('Business / data owner'),
    'consultant': gettext_lazy('Odoo consultant'),
    'accounting': gettext_lazy('Accounting team'),
    'operations': gettext_lazy('Operations team'),
}
PRIORITY_LABELS = {
    'high': gettext_lazy('High'),
    'medium': gettext_lazy('Medium'),
    'low': gettext_lazy('Low'),
}
_PRIORITY_RANK = {'high': 0, 'medium': 1, 'low': 2}

# Per-category why-it-matters / migration-impact (shared by its actions).
CATEGORY_WHY = {
    'duplicates': gettext_lazy('Duplicates split history and make name-based import matching ambiguous.'),
    'missing_data': gettext_lazy('Incomplete master data fails validations and blocks workflows after import.'),
    'orphans': gettext_lazy('References to archived records have no clean target in the new system.'),
    'import_ids': gettext_lazy('Without stable identifiers, re-imports create duplicates instead of updates.'),
    'config': gettext_lazy('Reference-data noise multiplies mapping decisions during migration.'),
    'attachments': gettext_lazy('Every gigabyte migrated is rehearsal and restore time paid repeatedly.'),
    'ownership': gettext_lazy('Documents owned by deactivated users lose followups and assignments silently.'),
    'custom_data': gettext_lazy('Custom-model data maps to nothing unless its identifiers are planned.'),
}
CATEGORY_IMPACT = {
    'duplicates': gettext_lazy('Merged before migration: clean history. After: weeks of reconciliation.'),
    'missing_data': gettext_lazy('Cheap to complete now; expensive to chase record-by-record at go-live.'),
    'orphans': gettext_lazy('Decide close/re-point now, or the import decides for you — badly.'),
    'import_ids': gettext_lazy('One import-compatible export now makes every later update-import safe.'),
    'config': gettext_lazy('A short review now avoids surprise mapping workshops mid-project.'),
    'attachments': gettext_lazy('Trimming bloat shortens every rehearsal cycle from day one.'),
    'ownership': gettext_lazy('Reassigning now keeps pipelines alive through the cutover.'),
    'custom_data': gettext_lazy('Plan the export/import path early — it is the least automatable part.'),
}

MGMT_QUESTIONS = [
    gettext_lazy('Who owns customer master data — by name, not by department?'),
    gettext_lazy('Which system is the source of truth for products and prices today?'),
    gettext_lazy('Which duplicate clusters should be merged before migration, and who decides the surviving record?'),
    gettext_lazy('How much attachment history does the new system actually need on day one?'),
]

CHECKLIST = [
    gettext_lazy('Duplicate clusters reviewed and merged (contacts, products).'),
    gettext_lazy('Master data completed: VAT, countries, internal references.'),
    gettext_lazy('Open documents re-pointed away from archived records.'),
    gettext_lazy('Ownership reassigned from deactivated users.'),
    gettext_lazy('External IDs established through an import-compatible export.'),
    gettext_lazy('Rehearsal import of a small batch verified before the real one.'),
]


def landing(request):
    if request.method == 'POST':
        form = DataRiskRunForm(request.POST)
        if form.is_bot():
            return redirect('tools_core:hub')
        if form.is_valid():
            return _start_run(request, form)
    else:
        form = DataRiskRunForm()
        track(request, TOOL_SLUG, 'data_risk_page_view')

    return render(request, 'tool_data_risk/landing.html', {
        'form': form,
        'meta_description': (
            'Free pre-migration data scan for Odoo: duplicate clusters, '
            'functional orphans, import-identifier coverage and master-data '
            'completeness — read-only, count-based, privacy-safe.'
        ),
    })


def _start_run(request, form):
    data = form.cleaned_data
    email = (data.get('email') or '').strip().lower()

    if rate_limit_exceeded(f'datarisk-ip:{client_ip(request)}',
                           RUNS_PER_IP_PER_DAY, 86400) or (
            email and rate_limit_exceeded(f'datarisk-run:{email}',
                                          RUNS_PER_EMAIL_PER_DAY, 86400)):
        form.add_error(None, _('You have reached the daily limit for this tool — please try again tomorrow.'))
        return render(request, 'tool_data_risk/landing.html', {'form': form})

    lead = None
    if email:
        lead = capture_lead(email, source_tool=TOOL_SLUG,
                            full_name=data.get('full_name', ''),
                            company=data.get('company', ''),
                            consent_marketing=bool(data.get('consent')))
    run = ToolRun.objects.create(
        lead=lead, tool_slug=TOOL_SLUG,
        odoo_url=_safe_url(data['odoo_url']), odoo_db=data['database'],
    )
    track(request, TOOL_SLUG, 'data_risk_started', run=run, email=email)
    try:
        run_data_risk_scan.delay(
            str(run.pk), data['odoo_url'], data['database'],
            data['login'], data['api_key'],
            getattr(request, 'LANGUAGE_CODE', 'en') or 'en',
            bool(data.get('save_snapshot')))
    except Exception:  # noqa: BLE001 — broker down: fail the run, keep the page
        run.status = 'failed'
        run.error_message = _('The diagnostic queue is unavailable right now — please try again in a few minutes.')
        run.save(update_fields=['status', 'error_message'])
    return redirect('tool_data_risk:progress', run_id=run.pk)


def _safe_url(raw):
    raw = (raw or '').strip()
    if '://' not in raw:
        raw = 'https://' + raw
    from urllib.parse import urlsplit
    parts = urlsplit(raw)
    return f'{parts.scheme}://{parts.netloc}'[:200]


def progress(request, run_id):
    run = get_object_or_404(ToolRun, pk=run_id, tool_slug=TOOL_SLUG)
    if run.status == 'done':
        return redirect('tool_data_risk:report', run_id=run.pk)
    steps = [
        {'label': _('Connecting to Odoo'),
         'helper': _('Opening a secure, read-only session')},
        {'label': _('Counting data signals'),
         'helper': _('Totals, duplicate clusters, archived references — counts, not content')},
        {'label': _('Scoring migration risk'),
         'helper': _('Deterministic category scores and cleanup priorities')},
    ]
    return render(request, 'tool_data_risk/progress.html', {
        'run': run,
        'steps': steps,
        'status_url': reverse('tool_data_risk:status', args=[run.pk]),
        'report_url': reverse('tool_data_risk:report', args=[run.pk]),
    })


def status(request, run_id):
    run = get_object_or_404(ToolRun, pk=run_id, tool_slug=TOOL_SLUG)
    if run.status == 'pending' and timezone.now() - run.created_at > STALE_PENDING_AFTER:
        run.status = 'failed'
        run.error_message = _('The scan could not start — the processing '
                              'queue appears to be offline. Please try again later.')
        run.finished_at = timezone.now()
        run.save(update_fields=['status', 'error_message', 'finished_at'])
    payload = {
        'status': run.status,
        'step': PROGRESS_STEPS.index(run.status) if run.status in PROGRESS_STEPS else None,
        'error': run.error_message if run.status == 'failed' else '',
    }
    if run.status == 'done':
        payload['report_url'] = reverse('tool_data_risk:report', args=[run.pk])
    return JsonResponse(payload)


def demo_report(request):
    from .demo import get_or_create_demo_run
    run = get_or_create_demo_run()
    track(request, TOOL_SLUG, 'data_risk_demo_opened')
    return redirect('tool_data_risk:report', run_id=run.pk)


def report(request, run_id):
    run = get_object_or_404(ToolRun, pk=run_id, tool_slug=TOOL_SLUG)
    if run.status != 'done':
        return redirect('tool_data_risk:progress', run_id=run.pk)

    result = run.result_json if not run.is_expired else None
    context = {
        'run': run,
        'expired': run.is_expired or run.result_json is None,
        'booking_url': settings.TOOLS_BOOKING_URL,
        'meta_description': 'Data Risk Profiler report — pre-migration '
                            'master-data quality scan by Bidatia.',
    }
    is_demo = bool(((result or {}).get('meta') or {}).get('demo'))
    if result:
        risk = result.get('risk') or {}
        context.update(_present(risk, run, result.get('meta') or {}))
        context['is_demo'] = is_demo
        context['advisor'] = result.get('advisor')
        context['delta'] = _delta_display(risk, result.get('delta'))
        if context.get('quality_map'):
            track(request, TOOL_SLUG, 'data_risk_quality_map_viewed',
                  run=run, demo=is_demo)
        if not is_demo:
            from tools_core.services.badges import (badge_eligibility,
                                                    get_active_badge)
            badge = get_active_badge(run)
            if badge:
                context['badge_url'] = reverse('tools_core:badge_verify',
                                               args=[badge.pk])
            elif badge_eligibility(run):
                context['badge_offer_url'] = reverse('tools_core:badge_create',
                                                     args=[run.pk])
                track(request, 'health_badge', 'healthy_badge_offered',
                      run=run, source_tool=TOOL_SLUG)
    if run.status == 'done' and not run.is_expired and not is_demo:
        track(request, TOOL_SLUG, 'data_risk_report_opened', run=run,
              email=(run.lead.email if run.lead else ''))
    return render(request, 'tool_data_risk/report.html', context)


def _present(risk, run, meta):
    categories = []
    for category in risk.get('categories') or []:
        code = category.get('code')
        issues = [_issue_display(i) for i in category.get('issues') or []]
        categories.append({
            'code': code,
            'label': CATEGORY_LABELS.get(code, code),
            'blurb': CATEGORY_BLURBS.get(code, ''),
            'state': category.get('state'),
            'score': category.get('score'),
            'severity': category.get('severity'),
            'issues': [i for i in issues if i],
        })

    blockers = [_issue_display(b) for b in risk.get('blockers') or []]
    plan = _cleanup_plan(risk)
    score = risk.get('score') or 0
    level = risk.get('level') or 'low'

    coverage = {}
    for category in risk.get('categories') or []:
        if category.get('code') == 'duplicates':
            for metric in category.get('metrics') or []:
                coverage[metric.get('code')] = metric.get('value')

    from .quality_map import build_quality_map

    return {
        'quality_map': build_quality_map(
            risk, {code: str(label) for code, label in CATEGORY_SHORT.items()}),
        'partners_coverage_pct': coverage.get('partners_coverage_pct'),
        'products_coverage_pct': coverage.get('products_coverage_pct'),
        'score': score,
        'level': level,
        'level_label': LEVEL_LABELS.get(level, level),
        'level_blurb': LEVEL_BLURBS.get(level, ''),
        'categories': categories,
        'blockers': [b for b in blockers if b],
        'plan': plan,
        'plan_stages': [
            (_('Before migration'), plan['before']),
            (_('During the rehearsal'), plan['rehearsal']),
            (_('After the first test import'), plan['after']),
        ],
        'mgmt_questions': MGMT_QUESTIONS,
        'checklist': CHECKLIST,
        'skipped_sections': risk.get('skipped_sections') or [],
        'error_sections': risk.get('error_sections') or [],
        'db_label': meta.get('db_name') or '',
        'server_version': meta.get('server_version') or '',
        'book_url': reverse('tool_data_risk:book_review', args=[run.pk]),
        'share_url': reverse('tool_data_risk:send_to_manager', args=[run.pk]),
        'xray_url': reverse('tool_data_risk:go_xray'),
        'rescue_url': reverse('tool_data_risk:go_rescue'),
    }


def _issue_display(issue):
    code = (issue or {}).get('code')
    line = ISSUE_LINES.get(code)
    if line is None:
        return None
    return {
        'code': code,
        'severity': issue.get('severity'),
        'text': str(line) % {'n': issue.get('count', 0)},
        'pct': issue.get('pct'),
        'examples': issue.get('examples') or [],
    }


def _cleanup_plan(risk):
    """v2 action list: structured, prioritized actions grouped by stage.
    Deterministic — built purely from issue codes and counts."""
    stages = {'before': [], 'rehearsal': [], 'after': []}
    seen = set()
    for category in risk.get('categories') or []:
        for issue in category.get('issues') or []:
            code = issue.get('code')
            action = CLEANUP_ACTIONS.get(code)
            if not action or code in seen or not issue.get('count'):
                continue
            seen.add(code)
            priority, owner = ACTION_META.get(code, ('medium', 'consultant'))
            stages[action[0]].append({
                'code': code,
                'count': issue['count'],
                'title': action[1],
                'priority': priority,
                'priority_label': PRIORITY_LABELS[priority],
                'owner_label': OWNER_LABELS[owner],
                'why': CATEGORY_WHY.get(category.get('code'), ''),
                'impact': CATEGORY_IMPACT.get(category.get('code'), ''),
            })
    for stage in stages:
        stages[stage].sort(key=lambda a: (_PRIORITY_RANK[a['priority']],
                                          -a['count']))
        stages[stage].append({
            'code': '', 'count': 0, 'title': GENERIC_PLAN[stage],
            'priority': 'low', 'priority_label': PRIORITY_LABELS['low'],
            'owner_label': OWNER_LABELS['consultant'], 'why': '', 'impact': '',
        })
    return stages


def _delta_display(risk, delta):
    """Before/after rows when an earlier opt-in snapshot exists."""
    if not delta:
        return None
    prev_categories = delta.get('categories') or {}
    rows = []
    for category in risk.get('categories') or []:
        code, current = category.get('code'), category.get('score')
        if current is None or code not in prev_categories:
            continue
        prev = prev_categories[code]
        diff = current - prev
        direction = ('same' if abs(diff) < 3
                     else 'improved' if diff < 0 else 'worse')
        rows.append({'label': CATEGORY_LABELS.get(code, code),
                     'prev': prev, 'current': current,
                     'diff': diff, 'direction': direction})
    score_diff = (risk.get('score') or 0) - (delta.get('prev_score') or 0)
    return {
        'prev_score': delta.get('prev_score'),
        'prev_date': delta.get('prev_date'),
        'current_score': risk.get('score'),
        'direction': ('same' if abs(score_diff) < 3
                      else 'improved' if score_diff < 0 else 'worse'),
        'rows': rows,
    }


def send_to_manager(request, run_id):
    """Forward a short executive summary to a decision-maker. CSRF-protected
    POST, rate-limited, archived in EmailLog. Includes the level, the top
    blockers and the report link — never masked examples or internal notes."""
    import json as json_mod

    from django.core.exceptions import ValidationError
    from django.core.validators import validate_email
    from django.utils import translation

    from core.email_service import send_email

    if request.method != 'POST':
        return JsonResponse({'ok': False}, status=405)
    run = get_object_or_404(ToolRun, pk=run_id, tool_slug=TOOL_SLUG)
    result = (run.result_json or {}) if not run.is_expired else {}
    risk = result.get('risk') or {}
    if not risk or ((result.get('meta') or {}).get('demo')):
        return JsonResponse({'ok': False, 'code': 'unavailable'}, status=409)
    if (rate_limit_exceeded(f'drp-mgr-run:{run.pk}', 3, 86400)
            or rate_limit_exceeded(f'drp-mgr-ip:{client_ip(request)}', 5, 600)):
        return JsonResponse({'ok': False, 'code': 'rate'}, status=429)

    try:
        body = json_mod.loads(request.body.decode() or '{}')
    except (ValueError, UnicodeDecodeError):
        body = {}
    manager_email = str(body.get('email') or '').strip().lower()
    try:
        validate_email(manager_email)
    except ValidationError:
        return JsonResponse({'ok': False, 'code': 'invalid'}, status=400)

    language = getattr(request, 'LANGUAGE_CODE', 'en') or 'en'
    report_url = settings.SITE_BASE_URL.rstrip('/') + reverse(
        'tool_data_risk:report', args=[run.pk])
    with translation.override(language):
        rows = [(_('Data risk score'), '%s / 100' % risk.get('score', 0)),
                (_('Risk level'),
                 str(LEVEL_LABELS.get(risk.get('level'), risk.get('level', ''))))]
        for i, blocker in enumerate(
                filter(None, (_issue_display(b)
                              for b in (risk.get('blockers') or [])[:5])), 1):
            # text only — masked examples stay inside the report itself
            rows.append((_('Blocker %(n)s') % {'n': i}, blocker['text']))
        log = send_email(
            to=manager_email,
            subject=_('A Data Risk Profiler report was shared with you — %(site)s') % {
                'site': settings.SITE_NAME},
            category='report_to_manager',
            heading=_('A colleague shared their pre-migration data profile with you'),
            paragraphs=[str(LEVEL_BLURBS.get(risk.get('level'), ''))],
            rows=rows,
            cta_label=_('Open the full report'),
            cta_url=report_url,
            footnotes=[_('Reply to this email to book a free 30-minute migration data review with a consultant.')],
            language=language,
            related=run,
            metadata={'tool_slug': TOOL_SLUG, 'kind': 'manager_share'},
        )
    if log.status != 'sent':
        return JsonResponse({'ok': False, 'code': 'send_failed'}, status=502)
    track(request, TOOL_SLUG, 'data_risk_report_sent_to_manager', run=run)
    return JsonResponse({'ok': True})


def book_review(request, run_id):
    """Hand off to the booking flow with the risk findings as the agenda."""
    run = get_object_or_404(ToolRun, pk=run_id, tool_slug=TOOL_SLUG)
    result = (run.result_json or {}) if not run.is_expired else {}
    risk = result.get('risk') or {}

    lines = [_('Booking the free migration data review of my Data Risk Profiler results.')]
    if risk:
        lines += ['', _('Data risk score: %(score)s/100 — %(level)s') % {
            'score': risk.get('score', 0),
            'level': LEVEL_LABELS.get(risk.get('level'), risk.get('level', ''))}]
        blockers = [_issue_display(b) for b in (risk.get('blockers') or [])[:3]]
        if any(blockers):
            lines += ['', _('Top blockers:')]
            lines += ['%d. %s' % (i, b['text'])
                      for i, b in enumerate(filter(None, blockers), 1)]
        lines += ['', _('Report link: %(url)s') % {
            'url': settings.SITE_BASE_URL.rstrip('/')
                   + reverse('tool_data_risk:report', args=[run.pk])}]
    prefill = {'problem_summary': '\n'.join(str(line) for line in lines),
               'consultation_type': 'intro_call'}
    if run.lead:
        if run.lead.full_name:
            prefill['full_name'] = run.lead.full_name
        if run.lead.company:
            prefill['company_name'] = run.lead.company
        if run.lead.email:
            prefill['email'] = run.lead.email

    track(request, TOOL_SLUG, 'data_risk_booking_clicked', run=run,
          email=(run.lead.email if run.lead else ''))
    alert_hot_lead(run, 'booking_clicked', score=risk.get('score'),
                   level=str(LEVEL_LABELS.get(risk.get('level'), '')) if risk else '')

    request.session['booking_prefill'] = prefill
    if settings.TOOLS_BOOKING_URL:
        return redirect(settings.TOOLS_BOOKING_URL)
    return redirect('booking:book_consultation')


def go_xray(request):
    track(request, TOOL_SLUG, 'data_risk_xray_clicked')
    return redirect('tool_studio_xray:landing')


def go_rescue(request):
    track(request, TOOL_SLUG, 'data_risk_rescue_clicked')
    return redirect('tool_erp_rescue:landing')
