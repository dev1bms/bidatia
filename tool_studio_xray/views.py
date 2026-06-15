import json
from datetime import timedelta

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from django.views.decorators.http import require_POST

from core.email_service import send_email
from tools_core.models import ReportQuestion, ToolRun
from tools_core.services.analytics import track
from tools_core.services.hot_leads import alert_hot_lead
from tools_core.services.lead_service import capture_lead
from tools_core.utils import client_ip, get_run_note, rate_limit_exceeded

from .analyzer import assess_upgrade, build_executive_summary
from .chat import MAX_QUESTION_CHARS
from .forms import StudioXrayRunForm
from .system_map import build_map
from .tasks import answer_report_question, run_studio_xray

TOOL_SLUG = 'studio_xray'
RUNS_PER_EMAIL_PER_DAY = 3

# Report chat limits: per report and per visitor IP (10-minute window).
CHAT_QUESTIONS_PER_RUN = 10
CHAT_QUESTIONS_PER_IP = 5

# Progress steps shown on the polling page, in pipeline order. 'ai_insights'
# only occurs when TOOLS_AI_MODEL is configured.
PROGRESS_STEPS = ('connecting', 'collecting', 'analyzing', 'ai_insights')

# A run still 'pending' after this long was never picked up by a worker
# (queue down / worker offline). Mark it failed instead of spinning forever.
# If the worker comes back later and processes the queued message anyway, the
# task simply overwrites this state — the report still gets delivered.
STALE_PENDING_AFTER = timedelta(minutes=5)

# A run that STARTED (connecting/collecting/…) but never reached done/failed
# within this window means the worker died or hung mid-scan — otherwise the
# progress page sits at "Connecting to Odoo" forever. Comfortably above the
# Celery hard time limit (CELERY_TASK_TIME_LIMIT = 420s) so a slow-but-alive
# scan is never killed early.
STALE_RUNNING_AFTER = timedelta(minutes=10)


def landing(request):
    if request.method == 'POST':
        form = StudioXrayRunForm(request.POST)
        if form.is_bot():
            # Pretend success; create nothing.
            return redirect('tools_core:hub')
        if form.is_valid():
            return _start_run(request, form)
    else:
        form = StudioXrayRunForm()
        track(request, TOOL_SLUG, 'tool_page_view')

    context = {
        'form': form,
        'meta_description': (
            'Free Odoo customization audit: a read-only scan that maps every '
            'Studio field, custom model and automation, ranks them by real '
            'usage, checks upgrade readiness — and lets an AI analyst answer '
            'questions about your report. Results auto-delete in 72 hours.'
        ),
    }
    return render(request, 'tool_studio_xray/landing.html', context)


def _start_run(request, form):
    data = form.cleaned_data
    email = data['email'].strip().lower()

    if rate_limit_exceeded(f'xray-run:{email}', RUNS_PER_EMAIL_PER_DAY, 86400):
        form.add_error(None, _('You have reached the daily limit for this tool — please try again tomorrow.'))
        return render(request, 'tool_studio_xray/landing.html', {'form': form})

    lead = capture_lead(
        email,
        source_tool=TOOL_SLUG,
        full_name=data.get('full_name', ''),
        company=data.get('company', ''),
        consent_marketing=data['consent'],
    )
    run = ToolRun.objects.create(
        lead=lead,
        tool_slug=TOOL_SLUG,
        odoo_url=_safe_url(data['odoo_url']),
        odoo_db=data['database'],
    )

    track(request, TOOL_SLUG, 'xray_started', run=run, email=email,
          scope=data.get('scan_scope') or 'studio')
    # Demo viewers who come back for a REAL scan are the warmest traffic.
    from tools_core.models import ToolEvent
    from tools_core.services.analytics import visitor_fingerprint
    if ToolEvent.objects.filter(event='demo_report_opened',
                                visitor_key=visitor_fingerprint(request)).exists():
        alert_hot_lead(run, 'demo_to_real',
                       signals=['Viewed the demo report before scanning'])
    try:
        # Credentials travel as task arguments only — never stored. The UI
        # language rides along so AI insights are written in it.
        run_studio_xray.delay(
            str(run.pk), data['odoo_url'], data['database'],
            data['login'], data['api_key'],
            getattr(request, 'LANGUAGE_CODE', 'en') or 'en',
            data.get('scan_scope') or 'studio',
        )
    except Exception:  # noqa: BLE001 — broker down: fail the run, keep the page up
        run.status = 'failed'
        run.error_message = _('The diagnostic queue is unavailable right now — please try again in a few minutes.')
        run.save(update_fields=['status', 'error_message'])

    return redirect('tool_studio_xray:progress', run_id=run.pk)


def _safe_url(raw):
    """Store scheme+host only (no paths, no query) on the run record."""
    raw = raw.strip()
    if '://' not in raw:
        raw = 'https://' + raw
    from urllib.parse import urlsplit
    parts = urlsplit(raw)
    return f'{parts.scheme}://{parts.netloc}'[:200]


def progress(request, run_id):
    run = get_object_or_404(ToolRun, pk=run_id, tool_slug=TOOL_SLUG)
    if run.status == 'done':
        return redirect('tool_studio_xray:report', run_id=run.pk)

    ai_enabled = bool(settings.TOOLS_AI_MODEL)
    # Purely presentational step list — the active step is driven client-side
    # from the status endpoint. The AI step only exists when the feature is on.
    steps = [
        {'label': _('Connecting to Odoo'),
         'helper': _('Opening a secure, read-only session'), 'ai': False},
        {'label': _('Collecting Studio data'),
         'helper': _('Reading fields, models, views and automations'), 'ai': False},
        {'label': _('Analyzing customizations'),
         'helper': _('Scoring complexity and spotting upgrade risks'), 'ai': False},
    ]
    if ai_enabled:
        steps.append({'label': _('Consulting the AI analyst'),
                      'helper': _('A local AI model interprets the findings for your business — this can take up to a minute'),
                      'ai': True})
    steps.append({'label': _('Preparing your report'),
                  'helper': _('Building your results and emailing the link'), 'ai': False})

    return render(request, 'tool_studio_xray/progress.html', {
        'run': run,
        'status_url': reverse('tool_studio_xray:status', args=[run.pk]),
        'report_url': reverse('tool_studio_xray:report', args=[run.pk]),
        'steps': steps,
        'ai_enabled': ai_enabled,
        'ai_step_index': 3 if ai_enabled else -1,
    })


def status(request, run_id):
    """Polled by the progress page. Safe JSON only — status, step index and
    the sanitized error message. Nothing else leaves this endpoint."""
    run = get_object_or_404(ToolRun, pk=run_id, tool_slug=TOOL_SLUG)
    _fail_if_stale(run)
    payload = {
        'status': run.status,
        'step': PROGRESS_STEPS.index(run.status) if run.status in PROGRESS_STEPS else None,
        'error': run.error_message if run.status == 'failed' else '',
    }
    if run.status == 'ai_insights':
        # Live tail of the model's reasoning trace (empty when unavailable).
        payload['ai_note'] = get_run_note(run.pk)
    if run.status == 'done':
        payload['report_url'] = reverse('tool_studio_xray:report', args=[run.pk])
    return JsonResponse(payload)


def _fail_if_stale(run):
    """Never let the progress page spin forever: fail a run that was never
    picked up by a worker, OR that started but stalled mid-scan."""
    if run.status in ('done', 'failed'):
        return
    age = timezone.now() - run.created_at
    if run.status == 'pending' and age > STALE_PENDING_AFTER:
        _mark_run_failed(run, _(
            'The scan could not start — the processing queue appears to be '
            'offline. Please try again later.'
        ))
    elif run.status in PROGRESS_STEPS and age > STALE_RUNNING_AFTER:
        _mark_run_failed(run, _(
            'The scan took too long and was stopped. Please try again in a '
            'few minutes.'
        ))


def _mark_run_failed(run, message):
    run.status = 'failed'
    run.error_message = message
    run.finished_at = timezone.now()
    run.save(update_fields=['status', 'error_message', 'finished_at'])


def demo_report(request):
    """Public, never-expiring demo of the v3 report (fictional company).
    No lead, no email, chat disabled — its own analytics event."""
    from .demo import get_or_create_demo_run
    run = get_or_create_demo_run()
    track(request, TOOL_SLUG, 'demo_report_opened')
    return redirect('tool_studio_xray:report', run_id=run.pk)


def report(request, run_id):
    run = get_object_or_404(ToolRun, pk=run_id, tool_slug=TOOL_SLUG)

    if run.status != 'done':
        return redirect('tool_studio_xray:progress', run_id=run.pk)

    result = run.result_json if not run.is_expired else None
    context = {
        'run': run,
        'expired': run.is_expired or run.result_json is None,
        'booking_url': settings.TOOLS_BOOKING_URL,
        'meta_description': 'Studio X-Ray report — Odoo Studio customization audit by Bidatia.',
    }
    if result:
        analysis = result.get('analysis') or {}
        findings = [_localized_finding(f) for f in analysis.get('findings') or []]
        scoring = _localized_scoring(result.get('scoring') or {})
        meta = result.get('meta') or {}
        score = scoring.get('score', 0)

        # Report v2 derivations — all tolerant of old result_json payloads:
        # 'modules' is absent in pre-v2 reports, and assess_upgrade returns
        # None for unparseable versions.
        modules = result.get('modules')
        upgrade = assess_upgrade(meta.get('server_version'), score)
        summary = build_executive_summary(findings, score, upgrade, modules)

        context.update({
            'meta': meta,
            'module_context': result.get('module_context') or {},
            'totals': analysis.get('totals') or {},
            'findings_critical': [f for f in findings if f['severity'] == 'critical'],
            'findings_warning': [f for f in findings if f['severity'] == 'warning'],
            'findings_info': [f for f in findings if f['severity'] == 'info'],
            'model_breakdown': analysis.get('model_breakdown') or [],
            'section_errors': analysis.get('sections_with_errors') or [],
            'scoring': scoring,
            'complexity_band': _complexity_band(score),
            'risk_lines': [_risk_line(r) for r in summary['risks']],
            'next_step_line': NEXT_STEP_LINES.get(summary['next_step'], ''),
            'upgrade': _upgrade_display(upgrade),
            'modules_display': _modules_display(modules),
            'score_breakdown': _score_breakdown(scoring),
            'action_plan': _action_plan(findings, upgrade, modules),
            'ai_insights': result.get('ai_insights'),
            'booking_agenda': _review_agenda(result),
            'book_review_url': reverse('tool_studio_xray:book_review', args=[run.pk]),
            # Report v3 blocks — absent on old stored reports, sections hide.
            'identity': result.get('identity'),
            'pulse': _pulse_display(result.get('pulse')),
            'usage': _usage_display(result.get('usage')),
            'code_summary': _code_display(result.get('code')),
            'system_map': build_map(result),
            'system_map_url': reverse('tool_studio_xray:system_map_svg',
                                      args=[run.pk]),
            'scan_scope': meta.get('scan_scope') or 'studio',
            'chat_enabled': bool(settings.TOOLS_AI_MODEL),
            'chat_ask_url': reverse('tool_studio_xray:ask_question', args=[run.pk]),
            'chat_remaining': max(CHAT_QUESTIONS_PER_RUN - run.questions.count(), 0),
            'chat_starters': _chat_starters(result),
            'share_url': reverse('tool_studio_xray:send_to_manager', args=[run.pk]),
            # Conversation survives page refreshes: it lives in ReportQuestion
            # rows and disappears with the run's normal 72h expiry (the whole
            # chat block is only rendered while the report is valid).
            'chat_history': [
                {'id': str(q.pk), 'question': q.question,
                 'answer': q.answer, 'status': q.status}
                for q in run.questions.exclude(question='')
            ],
        })
    if result:
        from tools_core.services.badges import badge_eligibility, get_active_badge

        badge = get_active_badge(run)
        if badge:
            context['badge_url'] = reverse('tools_core:badge_verify',
                                           args=[badge.pk])
        elif badge_eligibility(run):
            context['badge_offer_url'] = reverse('tools_core:badge_create',
                                                 args=[run.pk])
            track(request, 'health_badge', 'healthy_badge_offered', run=run,
                  source_tool=TOOL_SLUG)

    is_demo = bool(((result or {}).get('meta') or {}).get('demo'))
    if is_demo:
        # The demo is public marketing material: badge on, chat off, and the
        # funnel event was already logged by the demo entry point.
        context.update({'is_demo': True, 'chat_enabled': False})
    elif run.status == 'done' and not run.is_expired:
        track(request, TOOL_SLUG, 'xray_report_opened', run=run,
              email=(run.lead.email if run.lead else ''))
    if context.get('system_map'):
        track(request, TOOL_SLUG, 'xray_system_map_viewed', run=run,
              demo=is_demo)
    return render(request, 'tool_studio_xray/report.html', context)


def system_map_svg(request, run_id):
    """The report's System Map as a standalone SVG — 'open full map' views
    it inline, '?download=1' saves it as a file. Same expiry rules as the
    report; never reveals more than the inline map already shows."""
    from django.http import Http404, HttpResponse

    run = get_object_or_404(ToolRun, pk=run_id, tool_slug=TOOL_SLUG)
    result = run.result_json if (run.status == 'done' and not run.is_expired) else None
    system_map = build_map(result) if result else None
    if system_map is None:
        raise Http404

    download = bool(request.GET.get('download'))
    track(request, TOOL_SLUG,
          'xray_system_map_downloaded' if download else 'xray_system_map_opened',
          run=run, demo=bool(((result or {}).get('meta') or {}).get('demo')))

    from django.template.loader import render_to_string
    svg = render_to_string('tool_studio_xray/_system_map.html',
                           {'map': system_map}, request=request)
    response = HttpResponse(svg, content_type='image/svg+xml')
    # 'private' keeps Cloudflare from edge-caching .svg by extension —
    # without it the map outlives the report's 72h expiry at the edge.
    response['Cache-Control'] = 'private, max-age=300'
    if download:
        response['Content-Disposition'] = (
            'attachment; filename="bidatia-odoo-system-map.svg"')
    return response


def _chat_starters(result):
    """Three deterministic, translated starter questions tailored to the
    report — one click instead of a blank input box."""
    starters = [_('What is the most urgent risk in my system?')]
    analysis = (result or {}).get('analysis') or {}
    totals = analysis.get('totals') or {}
    meta = (result or {}).get('meta') or {}
    if totals.get('custom_models'):
        starters.append(_('What does having %(n)s custom models mean for us?')
                        % {'n': totals['custom_models']})
    elif totals.get('code_server_actions'):
        starters.append(_('How risky are our custom code server actions?'))
    upgrade = assess_upgrade(meta.get('server_version'),
                             ((result or {}).get('scoring') or {}).get('score', 0))
    if upgrade and upgrade.get('gap', 0) >= 1:
        starters.append(_('Is upgrading to Odoo %(latest)s safe for us right now?')
                        % {'latest': upgrade['latest_known_major']})
    else:
        starters.append(_('What should we fix before our next upgrade?'))
    return starters[:3]


# Report v3 — translated labels for the pulse/usage/code sections. Wording
# lives here (the analyzer emits codes and numbers only). These are evaluated
# at module load, so they MUST be lazy — otherwise they freeze to whatever
# language was active at import time (English) on the Arabic/Spanish pages.
VOLUME_LABELS = {
    'res.partner': gettext_lazy('Contacts'),
    'sale.order': gettext_lazy('Sales orders'),
    'account.move': gettext_lazy('Invoices & journal entries'),
    'purchase.order': gettext_lazy('Purchase orders'),
    'stock.picking': gettext_lazy('Stock transfers'),
    'crm.lead': gettext_lazy('CRM leads'),
    'project.task': gettext_lazy('Project tasks'),
    'mrp.production': gettext_lazy('Manufacturing orders'),
    'mail.message': gettext_lazy('Messages & log notes'),
}

TIER_LABELS = {
    'critical': gettext_lazy('Critical'),
    'active': gettext_lazy('In use'),
    'dead': gettext_lazy('Empty'),
}

ORIGIN_LABELS = {
    'custom': gettext_lazy('Custom'),
    'third_party': gettext_lazy('Third-party'),
    'oca': gettext_lazy('OCA community'),
    'official': gettext_lazy('Official'),
}


def _human_bytes(size):
    size = float(size or 0)
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if size < 1024 or unit == 'TB':
            return f'{size:.1f} {unit}' if unit not in ('B', 'KB') else f'{int(size)} {unit}'
        size /= 1024
    return '0 B'


def _pulse_display(pulse):
    if not pulse:
        return None
    display = dict(pulse)
    display['attachment_size'] = _human_bytes(pulse.get('attachment_bytes'))
    display['business_volumes'] = [
        {**row, 'label': VOLUME_LABELS.get(row.get('model'), row.get('model'))}
        for row in pulse.get('business_volumes') or []
    ]
    return display


def _tiered(rows):
    return [{**row, 'tier_label': TIER_LABELS.get(row.get('tier'), row.get('tier'))}
            for row in rows or []]


def _usage_display(usage):
    if not usage:
        return None
    return {**usage, 'rows': _tiered(usage.get('rows'))}


def _code_display(code):
    if not code:
        return None
    return {
        **code,
        'code_models': _tiered(code.get('code_models')),
        'modules': [
            {**row, 'origin_label': ORIGIN_LABELS.get(row.get('origin'), row.get('origin'))}
            for row in code.get('modules') or []
        ],
    }


@require_POST
def ask_question(request, run_id):
    """Create one chat question for a valid, unexpired report and queue the
    answer. Safe JSON in/out; the question text is length-capped here and
    treated as untrusted data everywhere downstream."""
    run = get_object_or_404(ToolRun, pk=run_id, tool_slug=TOOL_SLUG)
    if run.status != 'done' or run.is_expired or run.result_json is None:
        return JsonResponse({'ok': False, 'code': 'unavailable'}, status=409)
    if not settings.TOOLS_AI_MODEL:
        return JsonResponse({'ok': False, 'code': 'unavailable'}, status=409)

    if run.questions.count() >= CHAT_QUESTIONS_PER_RUN:
        return JsonResponse({'ok': False, 'code': 'limit',
                             'error': _('Question limit reached for this report — the rest is exactly what the free 30-minute review is for.')},
                            status=429)
    if rate_limit_exceeded(f'xray-chat:{client_ip(request)}', CHAT_QUESTIONS_PER_IP, 600):
        return JsonResponse({'ok': False, 'code': 'rate',
                             'error': _('A little too fast — give the analyst a moment and try again.')},
                            status=429)

    try:
        body = json.loads(request.body.decode() or '{}')
    except (ValueError, UnicodeDecodeError):
        body = {}
    text = str(body.get('question') or '').strip()
    if not 3 <= len(text) <= MAX_QUESTION_CHARS:
        return JsonResponse({'ok': False, 'code': 'invalid'}, status=400)

    question = ReportQuestion.objects.create(
        run=run, question=text,
        language=getattr(request, 'LANGUAGE_CODE', 'en') or 'en')
    track(request, TOOL_SLUG, 'xray_chat_question_asked', run=run,
          email=(run.lead.email if run.lead else ''))
    # First chat question per run = a hot signal (deduped per run+reason).
    alert_hot_lead(run, 'chat_question',
                   score=((run.result_json or {}).get('scoring') or {}).get('score'),
                   question=text)
    try:
        answer_report_question.delay(str(question.pk))
    except Exception:  # noqa: BLE001 — broker down
        question.status = 'failed'
        question.save(update_fields=['status'])

    return JsonResponse({
        'ok': True,
        'id': str(question.pk),
        'remaining': max(CHAT_QUESTIONS_PER_RUN - run.questions.count(), 0),
    })


def question_status(request, question_id):
    """Polled by the chat widget. Returns status + the validated answer."""
    question = get_object_or_404(
        ReportQuestion, pk=question_id, run__tool_slug=TOOL_SLUG)
    payload = {'status': question.status}
    if question.status == 'done':
        payload['answer'] = question.answer
    return JsonResponse(payload)


def send_to_manager(request, run_id):
    """Forward a short executive summary of the report to a decision-maker.
    CSRF-protected POST, rate-limited, archived in EmailLog. Demo runs and
    internal content are excluded."""
    from django.core.exceptions import ValidationError
    from django.core.validators import validate_email

    if request.method != 'POST':
        return JsonResponse({'ok': False}, status=405)
    run = get_object_or_404(ToolRun, pk=run_id, tool_slug=TOOL_SLUG)
    result = run.result_json if not run.is_expired else None
    if run.status != 'done' or not result:
        return JsonResponse({'ok': False, 'code': 'unavailable'}, status=409)
    if ((result.get('meta') or {}).get('demo')):
        return JsonResponse({'ok': False, 'code': 'unavailable'}, status=409)
    if (rate_limit_exceeded(f'mgr-run:{run.pk}', 3, 86400)
            or rate_limit_exceeded(f'mgr-ip:{client_ip(request)}', 5, 600)):
        return JsonResponse({'ok': False, 'code': 'rate'}, status=429)

    try:
        body = json.loads(request.body.decode() or '{}')
    except (ValueError, UnicodeDecodeError):
        body = {}
    manager_email = str(body.get('email') or '').strip().lower()
    try:
        validate_email(manager_email)
    except ValidationError:
        return JsonResponse({'ok': False, 'code': 'invalid'}, status=400)

    scoring = result.get('scoring') or {}
    findings = (result.get('analysis') or {}).get('findings') or []
    board_summary = ((result.get('ai_insights') or {}).get('board_summary') or '').strip()
    report_url = settings.SITE_BASE_URL.rstrip('/') + reverse(
        'tool_studio_xray:report', args=[run.pk])

    rows = [(_('Complexity score'), '%s / 100' % scoring.get('score')),
            (_('Estimated effort'), scoring.get('effort_estimate') or '—')]
    for i, finding in enumerate(findings[:3], 1):
        rows.append((_('Risk %(n)s') % {'n': i}, finding.get('title') or ''))

    log = send_email(
        to=manager_email,
        subject=_('A Studio X-Ray report was shared with you — %(site)s') % {
            'site': settings.SITE_NAME},
        category='report_to_manager',
        heading=_('A colleague shared their Odoo Studio X-Ray report with you'),
        paragraphs=[_('This read-only scan maps the customizations inside your Odoo and what they mean for the next upgrade.')],
        rows=rows,
        panel=({'label': _('What the scan found'), 'text': board_summary}
               if board_summary else None),
        cta_label=_('Open the full report'),
        cta_url=report_url,
        footnotes=[_('Reply to this email to book a free 30-minute review of this report with a consultant.')],
        language=getattr(request, 'LANGUAGE_CODE', 'en') or 'en',
        related=run,
        metadata={'tool_slug': TOOL_SLUG, 'kind': 'manager_share'},
    )
    if log.status != 'sent':
        return JsonResponse({'ok': False, 'code': 'send_failed'}, status=502)
    track(request, TOOL_SLUG, 'report_sent_to_manager', run=run)
    return JsonResponse({'ok': True})


def book_review(request, run_id):
    """Hand the visitor to the booking flow with everything pre-filled:
    a meeting agenda built from THEIR results, the report link, their
    identity from the lead, and the free intro consultation preselected.
    The visitor only has to pick a time slot."""
    run = get_object_or_404(ToolRun, pk=run_id, tool_slug=TOOL_SLUG)
    result = run.result_json if not run.is_expired else None
    agenda = _review_agenda(result)
    report_url = settings.SITE_BASE_URL.rstrip('/') + reverse(
        'tool_studio_xray:report', args=[run.pk])

    message_lines = [
        _('Booking the free 30-minute review of my Studio X-Ray report.'),
        '',
        _('Suggested agenda:'),
        *['• %s' % line for line in agenda],
        '',
        _('Report link: %(url)s') % {'url': report_url},
    ]
    prefill = {
        'problem_summary': '\n'.join(message_lines),
        'consultation_type': 'intro_call',  # the free review type
    }
    meta = ((result or {}).get('meta') or {})
    version = meta.get('server_version') or run.odoo_version
    if version:
        prefill['odoo_version'] = 'Odoo %s' % version
    if run.lead:
        if run.lead.full_name:
            prefill['full_name'] = run.lead.full_name
        if run.lead.company:
            prefill['company_name'] = run.lead.company
        if run.lead.email:
            prefill['email'] = run.lead.email

    # One-shot, generic handoff key — the booking view consumes it on GET.
    track(request, TOOL_SLUG, 'booking_started_from_tool', run=run,
          email=(run.lead.email if run.lead else ''))
    alert_hot_lead(run, 'booking_clicked',
                   score=((result or {}).get('scoring') or {}).get('score'),
                   signals=agenda[:3])

    request.session['booking_prefill'] = prefill

    if settings.TOOLS_BOOKING_URL:
        return redirect(settings.TOOLS_BOOKING_URL)
    return redirect('booking:book_consultation')


def _review_agenda(result):
    """Deterministic, translated meeting-agenda bullets built from the
    stored scan results (no AI involved — counts must be exact)."""
    if not result:
        return [_('Walk-through of my Studio X-Ray scan results.')]

    analysis = result.get('analysis') or {}
    totals = analysis.get('totals') or {}
    scoring = result.get('scoring') or {}
    meta = result.get('meta') or {}
    score = scoring.get('score', 0)

    items = [
        _('Walk-through of the Studio X-Ray results (score %(score)s/100 — %(band)s).')
        % {'score': score, 'band': _complexity_band(score)},
    ]
    if totals.get('custom_models'):
        items.append(_('A rebuilding plan for the %(n)s Studio-created models.')
                     % {'n': totals['custom_models']})
    if totals.get('code_server_actions'):
        items.append(_('Strategy for the %(n)s custom code server actions.')
                     % {'n': totals['code_server_actions']})
    upgrade = assess_upgrade(meta.get('server_version'), score)
    if upgrade and upgrade.get('gap', 0) >= 1:
        items.append(_('The upgrade path from Odoo %(current)s to Odoo %(latest)s and the cleanup it needs.')
                     % {'current': upgrade['detected_major'],
                        'latest': upgrade['latest_known_major']})
    modules = result.get('modules')
    if modules and modules.get('non_standard_total'):
        items.append(_('Compatibility check for the %(n)s non-standard modules.')
                     % {'n': modules['non_standard_total']})
    if totals.get('core_model_fields') and len(items) < 5:
        items.append(_('Risk review of the %(n)s Studio fields on core business models.')
                     % {'n': totals['core_model_fields']})
    return items[:5]


def _complexity_band(score):
    """Human label for the 0–100 complexity score (presentation only)."""
    if score <= 24:
        return _('Low complexity')
    if score <= 50:
        return _('Moderate complexity')
    if score <= 75:
        return _('High complexity')
    return _('Very high complexity')


# ── Report v2 presentation: wording for analyzer codes ────────────────────────
# The analyzer emits codes and numbers only; every sentence a manager reads is
# defined (and translated) here.

RISK_LINES = {
    'custom_studio_models': gettext_lazy(
        '%(n)s custom Studio models exist only in this database — they tie you to '
        'Studio/Enterprise and must be rebuilt as modules to migrate safely.'),
    'code_server_actions': gettext_lazy(
        '%(n)s server actions run Python code stored in the database — outside '
        'version control and a frequent cause of silent upgrade breakage.'),
    'version_gap': gettext_lazy(
        'You are %(n)s major versions behind the latest Odoo — every skipped '
        'version adds migration effort and risk.'),
    'studio_fields_on_core_models': gettext_lazy(
        '%(n)s Studio fields sit on core business models (sales, invoicing, '
        'contacts…) — the most common source of upgrade conflicts.'),
    'non_standard_modules': gettext_lazy(
        '%(n)s installed modules are not standard Odoo — each one must be '
        'verified or upgraded for your next version.'),
    'computed_studio_fields': gettext_lazy(
        '%(n)s fields carry business logic stored in the database — standard '
        'upgrades do not migrate that logic.'),
    'studio_view_inheritance': gettext_lazy(
        '%(n)s Studio views override standard screens and can conflict on every update.'),
    'automated_actions_present': gettext_lazy(
        '%(n)s automated actions are configured in the database and should be '
        'reviewed and documented.'),
}

NEXT_STEP_LINES = {
    'rebuild': gettext_lazy(
        'Plan a cleanup project: rebuild the Studio models and database code as a '
        'proper, versioned module before your next upgrade. Bidatia can scope this '
        'in a free 30-minute review.'),
    'cleanup_before_upgrade': gettext_lazy(
        'Schedule a customization cleanup before committing to an upgrade — it '
        'reduces migration cost and risk. Bidatia can prioritize the work with you '
        'in a free 30-minute review.'),
    'targeted_review': gettext_lazy(
        'A short, targeted review of the flagged items is enough to keep this '
        'installation healthy — Bidatia offers that as a free 30-minute session.'),
    'healthy': gettext_lazy(
        'No significant customization debt detected. A periodic re-scan before '
        'each upgrade keeps it that way.'),
}

FRICTION_LABELS = {
    'minimal': gettext_lazy('Minimal'),
    'moderate': gettext_lazy('Moderate'),
    'high': gettext_lazy('High'),
    'very_high': gettext_lazy('Very high'),
}

FRICTION_NOTES = {
    'minimal': gettext_lazy(
        'You are on a recent version with limited customization debt — keep '
        'scanning before each upgrade.'),
    'moderate': gettext_lazy(
        'Plan the next upgrade deliberately: review the flagged customizations '
        'first so the migration stays predictable.'),
    'high': gettext_lazy(
        'Expect real migration friction: budget a cleanup phase before the '
        'upgrade project, not during it.'),
    'very_high': gettext_lazy(
        'Upgrading as-is would be expensive and risky. A staged cleanup-then-'
        'migrate plan is strongly recommended.'),
}

SCORE_INPUT_LABELS = {
    'plain_studio_fields': gettext_lazy('Studio fields'),
    'computed_studio_fields': gettext_lazy('Computed / related fields'),
    'studio_views': gettext_lazy('Studio views'),
    'automated_actions': gettext_lazy('Automated actions'),
    'code_server_actions': gettext_lazy('Code server actions'),
    'custom_models': gettext_lazy('Custom models'),
}

ORIGIN_LABELS = {
    'official': gettext_lazy('Official Odoo'),
    'oca': gettext_lazy('OCA / Community'),
    'third_party': gettext_lazy('Third-party vendor'),
    'custom': gettext_lazy('Custom / internal'),
}

# Finding titles/details by code: the analyzer stores English; the report
# shows the reader's language. Unknown codes fall back to the stored text.
FINDING_TEXTS = {
    'studio_fields_on_core_models': (
        gettext_lazy('Studio fields on core business models'),
        gettext_lazy('Fields added directly to core models are the most common source '
                     'of conflicts and data issues during version upgrades.')),
    'computed_studio_fields': (
        gettext_lazy('Computed or related Studio fields'),
        gettext_lazy('These fields carry business logic stored in the database instead '
                     'of a module — standard upgrade paths do not migrate that logic.')),
    'custom_studio_models': (
        gettext_lazy('Custom models created with Studio'),
        gettext_lazy('Studio (x_) models exist only in this database. Leaving Enterprise, '
                     'or any clean rebuild, requires reimplementing them as a proper module.')),
    'code_server_actions': (
        gettext_lazy('Custom server actions executing Python code from the database'),
        gettext_lazy('Hand-made code living in database records (module-shipped actions '
                     'are excluded): invisible to version control, untested, and a '
                     'frequent cause of silent upgrade breakage.')),
    'studio_view_inheritance': (
        gettext_lazy('Studio views inheriting standard views'),
        gettext_lazy('Inherited view customizations conflict with upstream view changes '
                     'on every upgrade.')),
    'automated_actions_present': (
        gettext_lazy('Automated actions configured in the database'),
        gettext_lazy('Worth reviewing one by one: automated actions are easy to create '
                     'and easy to forget, and their interactions are rarely documented.')),
    'non_standard_modules': (
        gettext_lazy('Modules that are not standard Odoo'),
        gettext_lazy('Every community, third-party or custom module must be verified — '
                     'and often upgraded or replaced — before each Odoo version migration.')),
}

EFFORT_ESTIMATES = {
    '1–3 days': gettext_lazy('1–3 days'),
    '4–8 days': gettext_lazy('4–8 days'),
    '2–3 weeks': gettext_lazy('2–3 weeks'),
    '4+ weeks': gettext_lazy('4+ weeks'),
}

EFFORT_NOTE_TEXT = gettext_lazy('Indicative estimate — an exact quote requires a code review.')


def _localized_finding(finding):
    texts = FINDING_TEXTS.get(finding.get('code'))
    if not texts:
        return finding
    localized = dict(finding)
    localized['title'], localized['detail'] = texts
    return localized


def _localized_scoring(scoring):
    localized = dict(scoring)
    estimate = scoring.get('effort_estimate')
    if estimate in EFFORT_ESTIMATES:
        localized['effort_estimate'] = EFFORT_ESTIMATES[estimate]
    if scoring.get('effort_note'):
        localized['effort_note'] = EFFORT_NOTE_TEXT
    return localized


def _risk_line(risk):
    template = RISK_LINES.get(risk['code'])
    return template % {'n': risk['count']} if template else ''


def _upgrade_display(upgrade):
    if not upgrade:
        return None
    friction = upgrade['friction']
    return {
        **upgrade,
        'friction_label': FRICTION_LABELS.get(friction, friction),
        'friction_note': FRICTION_NOTES.get(friction, ''),
    }


def _modules_display(modules):
    if not modules:
        return None
    origins = [
        {'key': key, 'label': ORIGIN_LABELS[key], 'count': modules['by_origin'].get(key, 0)}
        for key in ('official', 'oca', 'third_party', 'custom')
        if modules['by_origin'].get(key, 0)
    ]
    examples = (modules['examples'].get('custom', [])
                + modules['examples'].get('third_party', [])
                + modules['examples'].get('oca', []))[:8]
    return {**modules, 'origins': origins, 'example_names': examples}


def _score_breakdown(scoring):
    """Bars explaining where the score came from — uses the inputs/weights
    already stored with every report (old and new)."""
    inputs = scoring.get('inputs') or {}
    weights = scoring.get('weights') or {}
    raw = scoring.get('raw_points') or 0
    rows = []
    for key, label in SCORE_INPUT_LABELS.items():
        count = int(inputs.get(key, 0) or 0)
        points = count * int(weights.get(key, 0) or 0)
        if count <= 0:
            continue
        rows.append({
            'label': label,
            'count': count,
            'points': points,
            'pct': round(points * 100 / raw) if raw else 0,
        })
    rows.sort(key=lambda r: -r['points'])
    return rows


def _action_plan(findings, upgrade, modules):
    """Groups of concrete actions derived from the findings. Returned as
    (group_key, group_label, [entries]) tuples, empty groups skipped."""
    codes = {f.get('code') for f in (findings or [])}
    quick, structural, prep = [], [], []

    if 'automated_actions_present' in codes:
        quick.append(_('Review every automated action; deactivate and document the unused ones.'))
    if 'code_server_actions' in codes:
        quick.append(_('Export and back up the Python code of all code server actions.'))
        structural.append(_('Move database-stored Python code into a versioned, tested module.'))
    if 'custom_studio_models' in codes:
        structural.append(_('Rebuild the Studio-created models as a proper Odoo module.'))
    if 'computed_studio_fields' in codes:
        structural.append(_('Reimplement computed/related Studio fields inside a maintained module.'))
    if 'studio_view_inheritance' in codes:
        structural.append(_('Re-apply the needed Studio view changes as clean XML inheritance in a module.'))
    if upgrade and upgrade.get('gap', 0) >= 1:
        prep.append(_('Plan the upgrade path towards Odoo %(v)s and budget the cleanup before migrating.')
                    % {'v': upgrade['latest_known_major']})
    if 'studio_fields_on_core_models' in codes:
        prep.append(_('Map every core-model Studio field and decide keep / merge / drop before migration.'))
    if modules and modules.get('non_standard_total'):
        prep.append(_('Verify that your %(n)s non-standard modules are available for the target version.')
                    % {'n': modules['non_standard_total']})

    groups = []
    if quick:
        groups.append({'key': 'quick', 'label': _('Quick wins'), 'items': quick})
    if structural:
        groups.append({'key': 'structural', 'label': _('Structural work'), 'items': structural})
    if prep:
        groups.append({'key': 'prep', 'label': _('Upgrade preparation'), 'items': prep})
    return groups
