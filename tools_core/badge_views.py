"""Healthy System Badge views: opt-in creation, public verification page
and the embeddable SVG. The public surface reveals ONLY: badge status,
tool type, broad level, snapshot date and the company name the visitor
chose to type — never scores, findings or contact data.
"""
from django.conf import settings
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.translation import gettext_lazy
from django.views.decorators.http import require_POST

from .models import HealthBadge, ToolRun
from .services.analytics import track
from .services.badges import get_or_create_badge
from .utils import client_ip, rate_limit_exceeded

BADGE_TOOL = 'health_badge'
CREATE_LIMIT_PER_HOUR = 10

LEVEL_LABELS = {
    'stable': gettext_lazy('Stable result'),
    'low_complexity': gettext_lazy('Low-risk result'),
    'low_data_risk': gettext_lazy('Low data migration risk'),
}
TOOL_LABELS = {
    'erp_rescue': gettext_lazy('ERP Rescue Check'),
    'studio_xray': gettext_lazy('Odoo Studio X-Ray'),
    'data_risk': gettext_lazy('Data Risk Profiler'),
}


@require_POST
def badge_create(request, run_id):
    """Opt-in only: nothing public exists until this explicit POST."""
    run = get_object_or_404(ToolRun, pk=run_id)
    if rate_limit_exceeded(f'badge-create:{client_ip(request)}',
                           CREATE_LIMIT_PER_HOUR, 3600):
        raise Http404
    badge, created = get_or_create_badge(
        run, company_name=request.POST.get('company_name', ''))
    if badge is None:
        raise Http404  # not eligible (or result expired) — no badge surface
    if created:
        track(request, BADGE_TOOL, 'healthy_badge_created', run=run,
              source_tool=run.tool_slug, level=badge.level_code,
              has_company=bool(badge.company_name))
    return redirect(reverse('tools_core:badge_verify', args=[badge.pk]) + '?new=1')


def badge_verify(request, badge_id):
    badge = get_object_or_404(HealthBadge, pk=badge_id)
    if not badge.is_active:
        # Revoked: the URL stays resolvable but shows no details.
        return render(request, 'tools_core/badge_verify.html',
                      {'badge': None, 'revoked': True}, status=410)

    track(request, BADGE_TOOL, 'healthy_badge_viewed',
          source_tool=badge.tool_slug, level=badge.level_code)
    base = settings.SITE_BASE_URL.rstrip('/')
    page_url = base + reverse('tools_core:badge_verify', args=[badge.pk])
    svg_url = base + reverse('tools_core:badge_svg', args=[badge.pk])
    embed_snippet = (
        '<a href="%s" target="_blank" rel="noopener">'
        '<img src="%s" alt="Bidatia ERP Health Snapshot — %s" '
        'width="240" height="56" loading="lazy"></a>'
    ) % (page_url, svg_url, badge.level_code.replace('_', '-'))

    return render(request, 'tools_core/badge_verify.html', {
        'badge': badge,
        'revoked': False,
        'level_label': LEVEL_LABELS.get(badge.level_code, badge.level_code),
        'tool_label': TOOL_LABELS.get(badge.tool_slug, badge.tool_slug),
        'page_url': page_url,
        'embed_snippet': embed_snippet,
        'is_new': bool(request.GET.get('new')),
        'meta_description': (
            'Verification page for a Bidatia ERP Health Snapshot badge — a '
            'point-in-time result from a free diagnostic, not a certification.'
        ),
    })


def badge_svg(request, badge_id):
    badge = get_object_or_404(HealthBadge, pk=badge_id, is_active=True)
    svg = render_to_string('tools_core/_badge.svg', {
        'level_label': LEVEL_LABELS.get(badge.level_code, badge.level_code),
        'tool_label': TOOL_LABELS.get(badge.tool_slug, badge.tool_slug),
        'date': badge.created_at.strftime('%Y-%m-%d'),
    }, request=request)
    response = HttpResponse(svg, content_type='image/svg+xml')
    # Cacheable for embeds, but short: a REVOKED badge must disappear from
    # the Cloudflare edge within the hour, not within a day.
    response['Cache-Control'] = 'public, max-age=3600'
    return response
