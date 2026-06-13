"""Odoo Instant Detector — public micro-tool, no login, no credentials.

The visitor pastes a public website URL; the detector runs synchronously
(1–3 short requests) and the verdict renders on the same page. Nothing is
persisted beyond ToolEvent analytics rows (normalized domain + result
metadata only — never page content).
"""
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from tools_core.services.analytics import track
from tools_core.utils import client_ip, rate_limit_exceeded

from .detector import DetectorError, detect

TOOL_SLUG = 'odoo_detector'
DETECT_LIMIT_PER_HOUR = 10

EVIDENCE_LABELS = {
    'generator_meta': gettext_lazy('The page declares Odoo as its generator'),
    'asset_bundle': gettext_lazy('Odoo web asset bundles found in the page'),
    'web_assets_path': gettext_lazy('Odoo asset paths (/web/assets/) referenced'),
    'odoo_js': gettext_lazy('Odoo JavaScript framework markers found'),
    'website_markers': gettext_lazy('Odoo Website builder markers found in the HTML'),
    'frontend_cookie': gettext_lazy('Odoo visitor-language cookie set by the server'),
    'session_cookie': gettext_lazy('Odoo-style session cookie set by the server'),
    'login_page': gettext_lazy('A standard Odoo login page is publicly visible'),
    'odoo_online_host': gettext_lazy('Hosted on an odoo.com address'),
    'odoo_sh_host': gettext_lazy('Hosted on an Odoo.sh address'),
    'version_reported': gettext_lazy('The server publicly reports an Odoo version'),
}

HOSTING_LABELS = {
    'odoo_online': gettext_lazy('Odoo Online (odoo.com)'),
    'odoo_sh': gettext_lazy('Odoo.sh'),
    'self_hosted': gettext_lazy('Self-hosted or partner-hosted (best guess)'),
    'unknown': gettext_lazy('Unknown'),
}

CONFIDENCE_LABELS = {
    'high': gettext_lazy('High'),
    'medium': gettext_lazy('Medium'),
    'low': gettext_lazy('Low'),
}


def landing(request):
    result = None
    error = ''
    url_value = ''

    if request.method == 'POST':
        # Honeypot: bots fill the hidden "website" field; humans never see it.
        if request.POST.get('website'):
            return redirect('tool_odoo_detector:landing')
        url_value = (request.POST.get('url') or '').strip()
        if not url_value:
            error = _('Please enter a website URL to check.')
        elif rate_limit_exceeded(f'odoo-detect:{client_ip(request)}',
                                 DETECT_LIMIT_PER_HOUR, 3600):
            error = _('Too many checks from your network — please try again in an hour.')
        else:
            track(request, TOOL_SLUG, 'odoo_detector_started')
            try:
                result = detect(url_value)
            except DetectorError:
                error = _('We can only check public website addresses '
                          '(https://…) — please verify the URL and try again.')
            if result:
                track(request, TOOL_SLUG, 'odoo_detector_completed',
                      domain=result['domain'], detected=result['detected'],
                      confidence=result['confidence'], hosting=result['hosting'],
                      version=result['version'])
    else:
        track(request, TOOL_SLUG, 'odoo_detector_page_view')

    context = {
        'result': _present(result) if result else None,
        'error': error,
        'url_value': url_value,
        'meta_description': (
            'Free instant check: does a website appear to run on Odoo? '
            'Paste a URL and get a best-effort answer with confidence level, '
            'hosting guess and the public signals found — no login needed.'
        ),
    }
    return render(request, 'tool_odoo_detector/landing.html', context)


def _present(result):
    """Translate machine codes into display strings for the template."""
    return {
        **result,
        'evidence_labels': [EVIDENCE_LABELS[code] for code in result['evidence']
                            if code in EVIDENCE_LABELS],
        'hosting_label': HOSTING_LABELS.get(result['hosting'], result['hosting']),
        'confidence_label': CONFIDENCE_LABELS.get(result['confidence'],
                                                  result['confidence']),
    }


# ── CTA redirects (server-side tracking, immune to blocked beacons) ──────────

def go_xray(request):
    track(request, TOOL_SLUG, 'odoo_detector_xray_clicked')
    return redirect('tool_studio_xray:landing')


def go_rescue(request):
    track(request, TOOL_SLUG, 'odoo_detector_rescue_clicked')
    return redirect('tool_erp_rescue:landing')


def go_demo(request):
    track(request, TOOL_SLUG, 'odoo_detector_demo_clicked')
    return redirect('tool_studio_xray:demo_report')
