"""ERP Rescue Check — interactive self-assessment, no Odoo connection.

Deterministic by design: scoring lives in checklist.py (pure Python); this
module owns ALL human wording (translated), the lead capture, the unified
email and the booking handoff. No Celery, no connector, no AI.
"""
from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone, translation
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from core.email_service import send_email
from tools_core.models import ToolRun
from tools_core.services.analytics import track
from tools_core.services.hot_leads import alert_hot_lead
from tools_core.services.lead_service import capture_lead
from tools_core.utils import rate_limit_exceeded

from .checklist import ANSWERS, QUESTIONS, SECTIONS, compute_result
from .forms import RescueCheckForm
from .tasks import generate_advisor_reading

TOOL_SLUG = 'erp_rescue'
RUNS_PER_EMAIL_PER_DAY = 10

# A rescue score at/above this is a hot lead on its own.
HOT_RESCUE_SCORE = 70

SECTION_LABELS = {
    'ownership': gettext_lazy('Ownership & documentation'),
    'people': gettext_lazy('People dependency'),
    'trust': gettext_lazy('Trust in the numbers'),
    'upgrade': gettext_lazy('Customizations & upgrade risk'),
    'operations': gettext_lazy('Operations & adoption'),
    'continuity': gettext_lazy('Support & continuity'),
}

QUESTION_LABELS = {
    'owner_defined': gettext_lazy('Is there one named owner of the ERP inside your company (not the vendor)?'),
    'customizations_documented': gettext_lazy('Are your customizations documented somewhere your team can actually read?'),
    'process_map': gettext_lazy('Does a written map of your core processes in the ERP exist?'),
    'shared_knowledge': gettext_lazy('Can more than one person explain how the system is configured?'),
    'single_developer': gettext_lazy('Does every change depend on a single developer or a single partner?'),
    'single_operator': gettext_lazy('Is there exactly one employee who knows how the key workflows are done?'),
    'absence_risk': gettext_lazy('Would daily operations suffer if that key person were unavailable for two weeks?'),
    'written_knowledge': gettext_lazy("Is operational knowledge written down — not only in people's heads?"),
    'parallel_excel': gettext_lazy("Does any department keep parallel spreadsheets because they don't trust the system?"),
    'reports_match': gettext_lazy('Do finance, sales and inventory reports tell the same story?'),
    'manual_corrections': gettext_lazy('Are numbers regularly corrected by hand outside the ERP?'),
    'management_trust': gettext_lazy('Does management trust the numbers enough to make decisions from them?'),
    'upgrade_fear': gettext_lazy('Does your team avoid or fear upgrading the system?'),
    'unknown_customizations': gettext_lazy('Are there customizations nobody on the team fully understands anymore?'),
    'recent_upgrade': gettext_lazy('Have you completed a successful version upgrade in the last two years?'),
    'customization_inventory': gettext_lazy('Do you have an up-to-date list of custom fields, modules and automations?'),
    'workarounds': gettext_lazy('Do employees work around the system instead of through it?'),
    'manual_steps': gettext_lazy('Do everyday processes require many manual steps or double data entry?'),
    'outside_processes': gettext_lazy('Are recurring business processes still run outside the ERP (email, paper, chat)?'),
    'system_slows': gettext_lazy('Does the system slow work down instead of organizing it?'),
    'support_contract': gettext_lazy('Do you have a clear support agreement with defined response times?'),
    'test_environment': gettext_lazy('Is there a test or staging environment separate from production?'),
    'tested_backup': gettext_lazy('Has a backup actually been restored as a test in the last year?'),
    'emergency_plan': gettext_lazy('Is there a written plan for what to do if the system goes down?'),
}

# Top-risk lines: how the risk reads on the result page (problem framing).
RISK_LINES = {
    'owner_defined': gettext_lazy('Nobody inside the company owns the ERP — every decision defaults to the vendor.'),
    'customizations_documented': gettext_lazy('Customizations are undocumented — changes are guesswork and onboarding is slow.'),
    'process_map': gettext_lazy('Core processes are not mapped — the system works "by memory".'),
    'shared_knowledge': gettext_lazy('Only one person can explain the configuration — a single point of failure.'),
    'single_developer': gettext_lazy('Every change depends on one developer or partner — you are one resignation away from a standstill.'),
    'single_operator': gettext_lazy('Key workflows live in one employee\'s head.'),
    'absence_risk': gettext_lazy('Two weeks without the key person would hurt daily operations.'),
    'written_knowledge': gettext_lazy('Operational knowledge exists only in people\'s heads — nothing is written down.'),
    'parallel_excel': gettext_lazy('Departments keep parallel spreadsheets — trust in the system\'s numbers is already broken.'),
    'reports_match': gettext_lazy('Finance, sales and inventory reports disagree — nobody knows which number is true.'),
    'manual_corrections': gettext_lazy('Numbers are corrected by hand outside the system — the ERP is no longer the source of truth.'),
    'management_trust': gettext_lazy('Management does not trust the system\'s numbers enough to decide from them.'),
    'upgrade_fear': gettext_lazy('The team fears upgrading — the system is drifting further behind with every release.'),
    'unknown_customizations': gettext_lazy('Customizations exist that nobody fully understands — invisible risk in every change.'),
    'recent_upgrade': gettext_lazy('No successful upgrade in over two years — the version gap is compounding.'),
    'customization_inventory': gettext_lazy('There is no inventory of custom fields, modules and automations.'),
    'workarounds': gettext_lazy('Employees work around the system — it is losing the battle against habit.'),
    'manual_steps': gettext_lazy('Everyday processes need many manual steps or double entry.'),
    'outside_processes': gettext_lazy('Recurring processes still run outside the ERP, in email, paper or chat.'),
    'system_slows': gettext_lazy('The system slows the work down instead of organizing it.'),
    'support_contract': gettext_lazy('There is no clear support agreement — when something breaks, response time is luck.'),
    'test_environment': gettext_lazy('Changes go straight to production — there is no test environment.'),
    'tested_backup': gettext_lazy('Backups have never been test-restored — you may discover they fail on the worst day.'),
    'emergency_plan': gettext_lazy('There is no written plan for a system outage.'),
}

# Rescue-plan steps: the action that answers each risk (solution framing).
PLAN_LINES = {
    'owner_defined': gettext_lazy('Name one internal owner for the ERP with a clear mandate, this week.'),
    'customizations_documented': gettext_lazy('Start a living document of customizations — even one page per area beats nothing.'),
    'process_map': gettext_lazy('Map your 5 most important processes end-to-end, one page each.'),
    'shared_knowledge': gettext_lazy('Schedule shadowing sessions so a second person learns the configuration.'),
    'single_developer': gettext_lazy('Break the single-developer dependency: get the code/configuration documented and a second pair of hands introduced.'),
    'single_operator': gettext_lazy('Have the key user record their workflows — video walkthroughs count.'),
    'absence_risk': gettext_lazy('Run a "key person on holiday" drill and write down everything that breaks.'),
    'written_knowledge': gettext_lazy('Create a shared operations handbook and make updating it part of the job.'),
    'parallel_excel': gettext_lazy('Pick ONE parallel spreadsheet and kill it: fix the underlying report until the team can let go of it.'),
    'reports_match': gettext_lazy('Reconcile finance, sales and inventory reports once — then fix the root cause of every mismatch found.'),
    'manual_corrections': gettext_lazy('Log every manual correction for two weeks — each one points at a process or configuration defect.'),
    'management_trust': gettext_lazy('Agree with management on 5 numbers the system must get right, and make them right first.'),
    'upgrade_fear': gettext_lazy('De-risk the upgrade: inventory what is custom, test the upgrade on a copy, then plan it properly.'),
    'unknown_customizations': gettext_lazy('Audit the unknown customizations first — what they do, who uses them, what depends on them.'),
    'recent_upgrade': gettext_lazy('Plan a supported-version upgrade path before the gap grows another year.'),
    'customization_inventory': gettext_lazy('Build the customization inventory — an automated scan is the fastest first step.'),
    'workarounds': gettext_lazy('Interview the teams that bypass the system and fix the top friction they name.'),
    'manual_steps': gettext_lazy('List the 3 most repetitive manual steps and automate or eliminate them.'),
    'outside_processes': gettext_lazy('Bring one outside process per month into the ERP — start with the riskiest.'),
    'system_slows': gettext_lazy('Measure where the system loses people time and tune those screens and steps first.'),
    'support_contract': gettext_lazy('Put a support agreement with response times in place before the next incident.'),
    'test_environment': gettext_lazy('Set up a staging environment — never change production blind again.'),
    'tested_backup': gettext_lazy('Restore a backup to a sandbox THIS month and prove the recovery actually works.'),
    'emergency_plan': gettext_lazy('Write a one-page outage plan: who acts, what is checked, who is informed.'),
}

LEVEL_LABELS = {
    'stable': gettext_lazy('Stable'),
    'needs_monitoring': gettext_lazy('Needs monitoring'),
    'at_risk': gettext_lazy('At risk'),
    'rescue_urgent': gettext_lazy('Rescue needed urgently'),
}

LEVEL_BLURBS = {
    'stable': gettext_lazy('Your ERP fundamentals look healthy. Keep the habits that got you here — and re-check after major changes.'),
    'needs_monitoring': gettext_lazy('The system works, but cracks are forming. Address the top risks below before they become incidents.'),
    'at_risk': gettext_lazy('Several rescue indicators are active. Without a plan, problems of this profile tend to escalate, not settle.'),
    'rescue_urgent': gettext_lazy('Your answers match the profile of systems that fail suddenly. The top risks below need attention now.'),
}


def landing(request):
    if request.method == 'POST':
        form = RescueCheckForm(request.POST)
        if form.is_bot():
            return redirect('tool_erp_rescue:landing')
        answers, missing = _collect_answers(request.POST)
        if form.is_valid() and not missing:
            return _finish_check(request, form, answers)
        if missing:
            form.add_error(None, _('Please answer all the questions — every axis matters for an honest score.'))
    else:
        form = RescueCheckForm()
        track(request, TOOL_SLUG, 'tool_page_view')

    context = {
        'form': form,
        'sections': _question_catalog(),
        'meta_description': (
            'Free 3-minute ERP rescue check: 24 consultant-grade questions, '
            'a 0-100 rescue score, your top 3 risks and a first recovery '
            'plan. No login, no system connection — works for any ERP.'
        ),
    }
    return render(request, 'tool_erp_rescue/landing.html', context)


def result(request, run_id):
    run = get_object_or_404(ToolRun, pk=run_id, tool_slug=TOOL_SLUG)
    context = {'run': run, 'expired': run.is_expired}
    data = (run.result_json or {}).get('rescue') if not run.is_expired else None

    if data:
        erp_type = (run.result_json.get('meta') or {}).get('erp_type', 'unknown')
        context.update({
            'score': data['score'],
            'level': data['level'],
            'level_label': LEVEL_LABELS.get(data['level'], data['level']),
            'level_blurb': LEVEL_BLURBS.get(data['level'], ''),
            'sections': [
                {'code': code, 'label': SECTION_LABELS[code],
                 'score': data['sections'].get(code, 0)}
                for code in SECTIONS
            ],
            'top_risks': [RISK_LINES[code] for code in data['top_risks']
                          if code in RISK_LINES],
            'plan_steps': [PLAN_LINES[code] for code in data['top_risks']
                           if code in PLAN_LINES],
            'is_odoo': erp_type == 'odoo',
            'book_url': reverse('tool_erp_rescue:book_review', args=[run.pk]),
            'share_url': reverse('tool_erp_rescue:send_to_manager', args=[run.pk]),
            'xray_url': reverse('tool_studio_xray:landing'),
        })
        advisor = run.result_json.get('advisor') or {}
        context.update({
            'advisor_status': advisor.get('status') or '',
            'advisor': advisor if advisor.get('status') == 'done' else None,
            'advisor_status_url': reverse('tool_erp_rescue:advisor_status',
                                          args=[run.pk]),
        })
        _add_badge_context(request, run, context)
    return render(request, 'tool_erp_rescue/result.html', context)


def _add_badge_context(request, run, context):
    """Healthy System Badge offer — only on eligible (stable) results."""
    from tools_core.services.badges import badge_eligibility, get_active_badge

    badge = get_active_badge(run)
    if badge:
        context['badge_url'] = reverse('tools_core:badge_verify', args=[badge.pk])
    elif badge_eligibility(run):
        context['badge_offer_url'] = reverse('tools_core:badge_create',
                                             args=[run.pk])
        track(request, 'health_badge', 'healthy_badge_offered', run=run,
              source_tool=TOOL_SLUG)


def send_to_manager(request, run_id):
    """Forward a short executive summary of the result to a decision-maker.
    CSRF-protected POST, rate-limited, archived in EmailLog. Never includes
    the raw pain text or any internal sales content."""
    from django.views.decorators.http import require_POST  # noqa: F401  (decorated below)
    return _send_to_manager(request, run_id)


def _send_to_manager(request, run_id):
    import json as json_mod

    from django.core.exceptions import ValidationError
    from django.core.validators import validate_email

    from tools_core.utils import client_ip

    if request.method != 'POST':
        return JsonResponse({'ok': False}, status=405)
    run = get_object_or_404(ToolRun, pk=run_id, tool_slug=TOOL_SLUG)
    data = (run.result_json or {}).get('rescue') if not run.is_expired else None
    if not data:
        return JsonResponse({'ok': False, 'code': 'unavailable'}, status=409)
    if (rate_limit_exceeded(f'mgr-run:{run.pk}', 3, 86400)
            or rate_limit_exceeded(f'mgr-ip:{client_ip(request)}', 5, 600)):
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
    result_url = settings.SITE_BASE_URL.rstrip('/') + reverse(
        'tool_erp_rescue:result', args=[run.pk])
    meta = (run.result_json or {}).get('meta') or {}
    with translation.override(language):
        rows = [(_('Rescue score'), '%s / 100' % data['score']),
                (_('Risk level'), str(LEVEL_LABELS.get(data['level'], data['level'])))]
        for i, code in enumerate(data.get('top_risks') or [], 1):
            if code in RISK_LINES:
                rows.append((_('Risk %(n)s') % {'n': i}, str(RISK_LINES[code])))
        if (meta.get('pain_text') or '').strip():
            rows.append((_('Reported pain point'),
                         _('Yes — see the full result for context.')))
        log = send_email(
            to=manager_email,
            subject=_('An ERP Rescue Check result was shared with you — %(site)s') % {
                'site': settings.SITE_NAME},
            category='report_to_manager',
            heading=_('A colleague shared their ERP Rescue Check results with you'),
            paragraphs=[str(LEVEL_BLURBS.get(data['level'], ''))],
            rows=rows,
            cta_label=_('Open the full result'),
            cta_url=result_url,
            footnotes=[_('Reply to this email to book a free 30-minute rescue review with a consultant.')],
            language=language,
            related=run,
            metadata={'tool_slug': TOOL_SLUG, 'kind': 'manager_share'},
        )
    if log.status != 'sent':
        return JsonResponse({'ok': False, 'code': 'send_failed'}, status=502)
    track(request, TOOL_SLUG, 'report_sent_to_manager', run=run)
    return JsonResponse({'ok': True})


def advisor_status(request, run_id):
    """Polled by the result page. Visitor-facing fields only — the internal
    sales signal stays in the admin."""
    run = get_object_or_404(ToolRun, pk=run_id, tool_slug=TOOL_SLUG)
    advisor = ((run.result_json or {}).get('advisor') or {}) if not run.is_expired else {}
    payload = {'status': advisor.get('status') or 'failed'}
    if payload['status'] == 'done':
        payload.update({
            'advisor_reading': advisor.get('advisor_reading', ''),
            'next_3_steps': advisor.get('next_3_steps', []),
            'management_questions': advisor.get('management_questions', []),
        })
    return JsonResponse(payload)


def book_review(request, run_id):
    """Hand off to the booking flow with the rescue findings as the agenda."""
    run = get_object_or_404(ToolRun, pk=run_id, tool_slug=TOOL_SLUG)
    data = (run.result_json or {}).get('rescue') if not run.is_expired else None

    message_lines = [_('Booking the free 30-minute rescue review of my ERP Rescue Check results.')]
    if data:
        message_lines += [
            '',
            _('Rescue score: %(score)s/100 — %(level)s') % {
                'score': data['score'],
                'level': LEVEL_LABELS.get(data['level'], data['level'])},
            '',
            _('Main risks:'),
            *['%d. %s' % (i, RISK_LINES[code])
              for i, code in enumerate(data['top_risks'], 1) if code in RISK_LINES],
            '',
            _('Result link: %(url)s') % {
                'url': settings.SITE_BASE_URL.rstrip('/') + reverse(
                    'tool_erp_rescue:result', args=[run.pk])},
        ]
    prefill = {
        'problem_summary': '\n'.join(message_lines),
        'consultation_type': 'intro_call',
    }
    erp_type = ((run.result_json or {}).get('meta') or {}).get('erp_type')
    if erp_type:
        prefill['odoo_version'] = {'odoo': 'Odoo', 'other': 'Other ERP',
                                   'unknown': 'ERP (unknown)'}.get(erp_type, '')
    if run.lead:
        if run.lead.full_name:
            prefill['full_name'] = run.lead.full_name
        if run.lead.company:
            prefill['company_name'] = run.lead.company
        if run.lead.email:
            prefill['email'] = run.lead.email

    track(request, TOOL_SLUG, 'rescue_booking_clicked', run=run,
          email=(run.lead.email if run.lead else ''))
    track(request, TOOL_SLUG, 'booking_started_from_tool', run=run,
          email=(run.lead.email if run.lead else ''))
    alert_hot_lead(run, 'booking_clicked',
                   score=(data or {}).get('score'),
                   level=str(LEVEL_LABELS.get((data or {}).get('level'), '')) if data else '',
                   signals=[str(RISK_LINES[c]) for c in ((data or {}).get('top_risks') or [])
                            if c in RISK_LINES])

    request.session['booking_prefill'] = prefill
    if settings.TOOLS_BOOKING_URL:
        return redirect(settings.TOOLS_BOOKING_URL)
    return redirect('booking:book_consultation')


# ── internals ─────────────────────────────────────────────────────────────────

def _question_catalog():
    """Translated questions grouped by section, for the template."""
    grouped = {code: [] for code in SECTIONS}
    for code, section, _w, _r in QUESTIONS:
        grouped[section].append({'code': code, 'label': QUESTION_LABELS[code]})
    return [{'code': section, 'label': SECTION_LABELS[section],
             'questions': grouped[section]} for section in SECTIONS]


def _collect_answers(post):
    answers, missing = {}, []
    for code, *_ in QUESTIONS:
        value = post.get('q_%s' % code, '')
        if value in ANSWERS:
            answers[code] = value
        else:
            missing.append(code)
    return answers, missing


def _finish_check(request, form, answers):
    data = form.cleaned_data
    email = data['email'].strip().lower()
    if rate_limit_exceeded(f'rescue-run:{email}', RUNS_PER_EMAIL_PER_DAY, 86400):
        form.add_error(None, _('You have reached the daily limit for this tool — please try again tomorrow.'))
        return render(request, 'tool_erp_rescue/landing.html',
                      {'form': form, 'sections': _question_catalog()})

    rescue = compute_result(answers)
    lead = capture_lead(
        email, source_tool=TOOL_SLUG,
        full_name=data.get('full_name', ''), company=data.get('company', ''),
        consent_marketing=data['consent'],
    )
    advisor_enabled = bool(settings.TOOLS_AI_MODEL)
    run = ToolRun.objects.create(
        lead=lead, tool_slug=TOOL_SLUG, status='done',
        odoo_url='https://tools.bidatia.local/none', odoo_db='-',
        finished_at=timezone.now(),
        result_json={
            'meta': {'tool': TOOL_SLUG,
                     'erp_type': data.get('erp_type') or 'unknown',
                     'language': getattr(request, 'LANGUAGE_CODE', 'en') or 'en',
                     # The visitor's own words — pure sales gold; wiped at 72h.
                     'pain_text': (data.get('pain_text') or '').strip()[:400]},
            'rescue': rescue,
            'advisor': {'status': 'pending'} if advisor_enabled else None,
        },
    )
    # Deterministic email goes out NOW — it never waits for the model.
    _send_result_email(request, run, rescue, data)
    track(request, TOOL_SLUG, 'rescue_completed', run=run, email=email,
          score=rescue['score'], level=rescue['level'],
          erp_type=data.get('erp_type') or 'unknown')
    if (data.get('pain_text') or '').strip():
        track(request, TOOL_SLUG, 'rescue_pain_text_provided', run=run, email=email)
    pain = (data.get('pain_text') or '').strip()
    if rescue['score'] >= HOT_RESCUE_SCORE or pain:
        alert_hot_lead(
            run, 'rescue_hot', score=rescue['score'],
            level=str(LEVEL_LABELS.get(rescue['level'], rescue['level'])),
            signals=[str(RISK_LINES[c]) for c in rescue['top_risks'] if c in RISK_LINES],
            pain_text=pain)
    if advisor_enabled:
        try:
            generate_advisor_reading.delay(str(run.pk))
        except Exception:  # noqa: BLE001 — broker down: page works without the card
            run.result_json['advisor'] = {'status': 'failed'}
            run.save(update_fields=['result_json'])
    return redirect('tool_erp_rescue:result', run_id=run.pk)


def _send_result_email(request, run, rescue, data):
    """Best-effort: the visitor is redirected to the result either way."""
    language = getattr(request, 'LANGUAGE_CODE', 'en') or 'en'
    result_url = settings.SITE_BASE_URL.rstrip('/') + reverse(
        'tool_erp_rescue:result', args=[run.pk])
    with translation.override(language):
        send_email(
            to=data['email'].strip().lower(),
            recipient_name=data.get('full_name', ''),
            subject=_('Your ERP Rescue Check results — %(site)s') % {
                'site': settings.SITE_NAME},
            category='rescue_check',
            heading=_('Your ERP Rescue Check results'),
            paragraphs=[LEVEL_BLURBS.get(rescue['level'], '')],
            rows=[
                (_('Rescue score'), '%s / 100' % rescue['score']),
                (_('Risk level'), LEVEL_LABELS.get(rescue['level'], rescue['level'])),
            ] + [
                (_('Risk %(n)s') % {'n': i}, RISK_LINES[code])
                for i, code in enumerate(rescue['top_risks'], 1)
                if code in RISK_LINES
            ],
            cta_label=_('Open my full results'),
            cta_url=result_url,
            footnotes=[
                _('Reply to this email to book a free 30-minute rescue review of your results.'),
            ] + ([_('Your system is Odoo — run the free Studio X-Ray to turn these risks into real numbers from your own database.')]
                 if data.get('erp_type') == 'odoo' else []),
            language=language,
            related=run,
            metadata={'tool_slug': TOOL_SLUG},
        )
