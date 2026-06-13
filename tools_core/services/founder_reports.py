"""Founder daily/monthly report builders — pure aggregation, no sending.

The Celery tasks in tools_core.tasks call these builders and pass the
result to the unified email service. Keeping the aggregation here makes
the period math and the content deterministic and unit-testable.

The weekly summary (send_founder_weekly_summary) is intentionally NOT
refactored through this module — it keeps its existing behavior.
"""
from datetime import date, datetime, time, timedelta, timezone as dt_timezone

from django.conf import settings
from django.db.models import Count
from django.utils import timezone

# ── event taxonomy (one place to extend when a new tool ships) ───────────────

PAGE_VIEW_EVENTS = (
    'tool_page_view', 'odoo_detector_page_view', 'chaos_calculator_page_view',
    'data_risk_page_view',
)

# tool key → (label, started events, completed events)
TOOL_FUNNELS = {
    'erp_rescue': ('ERP Rescue Check', ('rescue_started',), ('rescue_completed',)),
    'studio_xray': ('Studio X-Ray', ('xray_started',), ('xray_completed',)),
    'odoo_detector': ('Odoo Detector', ('odoo_detector_started',),
                      ('odoo_detector_completed',)),
    'chaos_calculator': ('Chaos Calculator', (), ('chaos_calculator_completed',)),
    'data_risk': ('Data Risk Profiler', ('data_risk_started',),
                  ('data_risk_completed',)),
}

REPORT_OPENED_EVENTS = ('xray_report_opened', 'data_risk_report_opened')
BOOKING_EVENTS = ('rescue_booking_clicked', 'booking_started_from_tool',
                  'data_risk_booking_clicked')
CROSS_CTA_EVENTS = (
    'rescue_xray_clicked', 'odoo_detector_xray_clicked',
    'odoo_detector_rescue_clicked', 'chaos_calculator_xray_clicked',
    'chaos_calculator_rescue_clicked', 'data_risk_xray_clicked',
    'data_risk_rescue_clicked', 'odoo_eol_xray_clicked',
    'odoo_eol_rescue_clicked', 'glossary_tool_cta_clicked',
)
DEMO_EVENTS = ('demo_report_opened', 'odoo_detector_demo_clicked',
               'data_risk_demo_opened')

# Deterministic pain-theme buckets (EN + AR keywords, lowercase substrings).
PAIN_THEMES = (
    ('Spreadsheets / parallel Excel', ('excel', 'spreadsheet', 'sheet',
                                       'اكسل', 'إكسل', 'جداول')),
    ('Trust in the numbers', ('trust', 'wrong number', 'reports', 'تقارير',
                              'أرقام', 'لا نثق')),
    ('Manual work / double entry', ('manual', 'double', 'retype', 'يدوي',
                                    'تكرار الادخال', 'إدخال')),
    ('Upgrade / version fear', ('upgrade', 'version', 'migration', 'ترقية',
                                'إصدار', 'ترحيل')),
    ('Key-person dependency', ('developer', 'one person', 'left', 'مطور',
                               'شخص واحد', 'موظف')),
    ('Slow system / performance', ('slow', 'performance', 'بطيء', 'بطء')),
)

MAX_LIST_ITEMS = 5


def _admin_url(path):
    return settings.SITE_BASE_URL.rstrip('/') + path


def admin_links():
    return [
        ('Tool events', _admin_url('/admin/tools_core/toolevent/')),
        ('Tool runs', _admin_url('/admin/tools_core/toolrun/')),
        ('Email logs', _admin_url('/admin/core/emaillog/')),
    ]


def _event_counts(start, end):
    from tools_core.models import ToolEvent
    return dict(
        ToolEvent.objects.filter(created_at__gte=start, created_at__lt=end)
        .values_list('event')
        .annotate(n=Count('id'))
        .values_list('event', 'n')
    )


def _total(counts, events):
    return sum(counts.get(event, 0) for event in events)


def _run_score(run):
    """Best-effort risk/score for a run, across the three scoring tools."""
    result = run.result_json or {}
    if run.tool_slug == 'erp_rescue':
        return ((result.get('rescue') or {}).get('score'))
    if run.tool_slug == 'studio_xray':
        return ((result.get('scoring') or {}).get('score'))
    if run.tool_slug == 'data_risk':
        return ((result.get('risk') or {}).get('score'))
    return None


def _pain_texts(start, end):
    from tools_core.models import ToolRun
    pains = []
    for run in ToolRun.objects.filter(tool_slug='erp_rescue',
                                      created_at__gte=start,
                                      created_at__lt=end):
        text = (((run.result_json or {}).get('meta') or {})
                .get('pain_text') or '').strip()
        if text:
            pains.append(text)
    return pains


# ── daily ─────────────────────────────────────────────────────────────────────

def build_daily_report(now=None):
    """Last-24h action report. Returns the kwargs-ish dict the task emails."""
    from core.models import EmailLog
    from tools_core.models import ReportQuestion, ToolRun
    from tools_core.services.hot_leads import CATEGORY as HOT_LEAD_CATEGORY

    now = now or timezone.now()
    start = now - timedelta(hours=24)
    counts = _event_counts(start, now)

    rows = [('Tool page views (24h)', str(_total(counts, PAGE_VIEW_EVENTS)))]
    for _slug, (label, started, completed) in TOOL_FUNNELS.items():
        started_n = _total(counts, started)
        completed_n = _total(counts, completed)
        if started:
            rows.append((label, f'{started_n} started · {completed_n} completed'))
        else:
            rows.append((label, f'{completed_n} completed'))
    rows += [
        ('Reports opened', str(_total(counts, REPORT_OPENED_EVENTS))),
        ('Booking clicks', str(_total(counts, BOOKING_EVENTS))),
        ('Cross-tool CTA clicks', str(_total(counts, CROSS_CTA_EVENTS))),
        ('Demo opens', str(_total(counts, DEMO_EVENTS))),
        ('Hot-lead alerts', str(
            EmailLog.objects.filter(category=HOT_LEAD_CATEGORY,
                                    created_at__gte=start,
                                    created_at__lt=now).count())),
    ]

    runs = list(ToolRun.objects.filter(created_at__gte=start, created_at__lt=now)
                .select_related('lead').order_by('-created_at'))
    failed = [r for r in runs if r.status == 'failed']
    scored = sorted(
        ((r, _run_score(r)) for r in runs if _run_score(r) is not None),
        key=lambda pair: -pair[1])

    rows.append(('Runs (24h)', f'{len(runs)} total · {len(failed)} failed'))

    paragraphs = []
    if runs:
        latest = [f"{r.tool_slug} · {r.status}"
                  + (f" · {r.lead.email}" if r.lead and r.lead.email else '')
                  for r in runs[:MAX_LIST_ITEMS]]
        paragraphs.append('Latest runs: ' + ' | '.join(latest))
    if scored:
        top = [f"{r.tool_slug} {score}/100" for r, score in scored[:3]]
        paragraphs.append('Highest-risk results: ' + ' | '.join(top))
    questions = list(
        ReportQuestion.objects.filter(created_at__gte=start, created_at__lt=now)
        .exclude(question='').values_list('question', flat=True)[:3])
    if questions:
        paragraphs.append('New chat questions: ' + ' | '.join(questions))
    if failed:
        reasons = [r.error_message[:90] or 'unknown' for r in failed[:3]]
        paragraphs.append('Failed runs: ' + ' | '.join(reasons))

    pains = _pain_texts(start, now)
    panel = ({'label': 'New pain texts', 'text': ' • '.join(pains[:3])}
             if pains else None)

    footnotes = [f'{label}: {url}' for label, url in admin_links()]

    return {
        'period_key': 'founder_daily_summary:%s' % now.date().isoformat(),
        'subject': 'Bidatia Daily Report — %s' % now.date().isoformat(),
        'heading': 'Your tools, last 24 hours',
        'rows': rows,
        'paragraphs': paragraphs or ['A quiet day — the counts are below.'],
        'panel': panel,
        'footnotes': footnotes,
    }


# ── monthly ───────────────────────────────────────────────────────────────────

def previous_month_bounds(today=None):
    """[start, end) datetimes covering the previous calendar month (UTC)."""
    today = today or timezone.now().date()
    first_this = today.replace(day=1)
    last_prev = first_this - timedelta(days=1)
    first_prev = last_prev.replace(day=1)
    tz = dt_timezone.utc
    return (datetime.combine(first_prev, time.min, tzinfo=tz),
            datetime.combine(first_this, time.min, tzinfo=tz),
            first_prev)


def _pct(part, whole):
    return round(part * 100.0 / whole) if whole else 0


def build_monthly_report(today=None):
    from core.models import EmailLog
    from tools_core.models import Lead, ReportQuestion, ToolRun
    from tools_core.services.hot_leads import CATEGORY as HOT_LEAD_CATEGORY

    start, end, first_prev = previous_month_bounds(today)
    counts = _event_counts(start, end)
    month_label = first_prev.strftime('%B %Y')

    page_views_by_tool = {
        'erp_rescue': counts.get('tool_page_view', 0),  # hub+rescue+xray share it
        'odoo_detector': counts.get('odoo_detector_page_view', 0),
        'chaos_calculator': counts.get('chaos_calculator_page_view', 0),
        'data_risk': counts.get('data_risk_page_view', 0),
    }

    funnels, rows = [], []
    for slug, (label, started_ev, completed_ev) in TOOL_FUNNELS.items():
        started = _total(counts, started_ev)
        completed = _total(counts, completed_ev)
        opened = (counts.get('xray_report_opened', 0) if slug == 'studio_xray'
                  else counts.get('data_risk_report_opened', 0)
                  if slug == 'data_risk' else None)
        booking = (counts.get('rescue_booking_clicked', 0) if slug == 'erp_rescue'
                   else counts.get('data_risk_booking_clicked', 0)
                   if slug == 'data_risk' else None)
        views = page_views_by_tool.get(slug)
        funnels.append({'slug': slug, 'label': label, 'views': views,
                        'started': started, 'completed': completed,
                        'opened': opened, 'booking': booking})
        parts = []
        if views is not None:
            parts.append(f'{views} views')
        if started_ev:
            parts.append(f'{started} started')
        parts.append(f'{completed} completed')
        if opened is not None:
            parts.append(f'{opened} opened')
        if booking is not None:
            parts.append(f'{booking} booking')
        rows.append((label, ' · '.join(parts)))

    total_views = _total(counts, PAGE_VIEW_EVENTS)
    total_started = sum(f['started'] for f in funnels)
    total_completed = sum(f['completed'] for f in funnels)
    total_booking = _total(counts, BOOKING_EVENTS)
    rows += [
        ('Total tool page views', str(total_views)),
        ('Conversion · started/views', f'{_pct(total_started, total_views)}%'),
        ('Conversion · completed/started', f'{_pct(total_completed, total_started)}%'),
        ('Conversion · booking/completed', f'{_pct(total_booking, total_completed)}%'),
    ]

    # Leads
    leads_qs = Lead.objects.filter(created_at__gte=start, created_at__lt=end)
    new_leads = leads_qs.exclude(source_tool__startswith='waitlist_').count()
    waitlist = leads_qs.filter(source_tool__startswith='waitlist_').count()
    hot_leads = EmailLog.objects.filter(category=HOT_LEAD_CATEGORY,
                                        created_at__gte=start,
                                        created_at__lt=end).count()
    rows += [('New leads', str(new_leads)), ('Waitlist signups', str(waitlist)),
             ('Hot-lead alerts', str(hot_leads))]

    # Emails by category
    email_counts = (EmailLog.objects
                    .filter(created_at__gte=start, created_at__lt=end)
                    .values_list('category').annotate(n=Count('id'))
                    .order_by('-n'))
    if email_counts:
        rows.append(('Emails sent', ' · '.join(
            f'{cat} {n}' for cat, n in list(email_counts)[:6])))

    # Failed runs and their reasons
    runs = list(ToolRun.objects.filter(created_at__gte=start, created_at__lt=end)
                .select_related('lead'))
    failed = [r for r in runs if r.status == 'failed']
    reason_counts = {}
    for run in failed:
        key = (run.error_message or 'unknown')[:70]
        reason_counts[key] = reason_counts.get(key, 0) + 1
    rows.append(('Runs', f'{len(runs)} total · {len(failed)} failed'))

    paragraphs = []

    if funnels:
        most_visited = max((f for f in funnels if f['views'] is not None),
                           key=lambda f: f['views'], default=None)
        converters = [f for f in funnels if f['started']]
        best_converter = max(
            converters, key=lambda f: f['completed'] / f['started'],
            default=None)
        if most_visited and most_visited['views']:
            paragraphs.append('Most visited tool: %s (%d views).'
                              % (most_visited['label'], most_visited['views']))
        if best_converter:
            paragraphs.append('Best completion rate: %s (%d%%).' % (
                best_converter['label'],
                _pct(best_converter['completed'], best_converter['started'])))

    # Top leads by the riskiest score across their runs
    best_by_lead = {}
    for run in runs:
        score = _run_score(run)
        if run.lead and run.lead.email and score is not None:
            current = best_by_lead.get(run.lead.email)
            if current is None or score > current[0]:
                best_by_lead[run.lead.email] = (score, run)
    top_leads = sorted(best_by_lead.items(), key=lambda kv: -kv[1][0])[:10]
    if top_leads:
        paragraphs.append('Top leads by risk: ' + ' | '.join(
            f"{email} ({run.lead.company or '—'}) {run.tool_slug} {score}/100"
            for email, (score, run) in top_leads))

    # Pain themes (deterministic keyword buckets)
    pains = _pain_texts(start, end)
    theme_counts = []
    for theme, keywords in PAIN_THEMES:
        hits = sum(1 for p in pains
                   if any(k in p.lower() for k in keywords))
        if hits:
            theme_counts.append((theme, hits))
    theme_counts.sort(key=lambda tc: -tc[1])
    if theme_counts:
        paragraphs.append('Pain themes: ' + ' | '.join(
            f'{theme} ×{hits}' for theme, hits in theme_counts[:4]))

    questions = list(
        ReportQuestion.objects.filter(created_at__gte=start, created_at__lt=end)
        .exclude(question='').values_list('question', flat=True)[:5])
    if questions:
        paragraphs.append('Report-chat questions: ' + ' | '.join(questions))

    if reason_counts:
        top_reasons = sorted(reason_counts.items(), key=lambda kv: -kv[1])[:3]
        paragraphs.append('Failure reasons: ' + ' | '.join(
            f'{reason} ×{n}' for reason, n in top_reasons))

    recommendations = _recommendations(funnels, total_views, total_started,
                                       total_completed, total_booking,
                                       len(failed), waitlist, theme_counts)
    panel = ({'label': 'Recommendations for next month',
              'text': ' • '.join(recommendations)} if recommendations else None)

    footnotes = [f'{label}: {url}' for label, url in admin_links()]

    return {
        'period_key': 'founder_monthly_summary:%s' % first_prev.strftime('%Y-%m'),
        'subject': 'Bidatia Monthly Growth Report — %s' % month_label,
        'heading': 'Your tools funnel — %s' % month_label,
        'rows': rows,
        'paragraphs': paragraphs or ['A quiet month — the counts are below.'],
        'panel': panel,
        'footnotes': footnotes,
    }


def _recommendations(funnels, views, started, completed, booking,
                     failed_count, waitlist, theme_counts):
    """Deterministic, rule-based suggestions. No AI — every rule names the
    number that triggered it."""
    recs = []
    by_slug = {f['slug']: f for f in funnels}

    xray = by_slug.get('studio_xray', {})
    if (xray.get('opened') or 0) >= 10 and booking < (xray.get('opened') or 0) * 0.1:
        recs.append('X-Ray reports are opened (%d) but bookings lag (%d) — '
                    'improve the booking CTA on the report.'
                    % (xray['opened'], booking))
    if views >= 50 and started < views * 0.1:
        recs.append('Visits are healthy (%d) but only %d scans started — '
                    'simplify the landing forms or strengthen the first CTA.'
                    % (views, started))
    for funnel in funnels:
        if funnel['started'] >= 10 and \
                funnel['completed'] < funnel['started'] * 0.5:
            recs.append('%s loses half its starters (%d→%d) — review the '
                        'flow for friction.' % (funnel['label'],
                                                funnel['started'],
                                                funnel['completed']))
    if failed_count >= 5:
        recs.append('%d scans failed this month — investigate the top failure '
                    'reason before it costs leads.' % failed_count)
    if waitlist > 0:
        recs.append('%d waitlist signups are waiting — they are pre-qualified '
                    'first users for the next tool.' % waitlist)
    if theme_counts:
        recs.append('The dominant pain theme is "%s" — publish content or a '
                    'tool feature addressing it.' % theme_counts[0][0])
    return recs[:5]
