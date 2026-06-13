import json

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from django.views.decorators.http import require_POST

from .connectors import ConnectorError, OdooXmlRpcConnector
from .connectors.discovery import detect_databases
from .services.analytics import track
from .services.lead_service import capture_lead
from .utils import client_ip, rate_limit_exceeded

TEST_CONNECTION_LIMIT_PER_HOUR = 10
DETECT_DB_LIMIT_PER_HOUR = 15

# Registry of tool cards on the hub. `url_name` is None until the tool app
# ships — cards without a URL render as "coming soon" with a notify-me form.
TOOLS = [
    {
        'slug': 'studio_xray',
        'name': gettext_lazy('Odoo Studio X-Ray'),
        'description': gettext_lazy(
            'See everything Studio really built: x_studio fields, custom models, '
            'automations and views — plus the upgrade risks they hide.'
        ),
        'icon': 'xray',
        'featured': True,
        'url_name': 'tool_studio_xray:landing',
    },
    {
        'slug': 'migration_scanner',
        'name': gettext_lazy('Migration Readiness Scanner'),
        'description': gettext_lazy(
            'Check how ready your Odoo is for the next version: module mapping, '
            'renamed or removed apps, and custom code exposure.'
        ),
        'icon': 'migration',
        'featured': False,
        'url_name': None,
    },
    {
        'slug': 'data_risk_profiler',
        'name': gettext_lazy('Data Risk Profiler'),
        'description': gettext_lazy(
            'Assess your master data before migration: duplicates, orphaned '
            'records and import risks — before they slow down your go-live.'
        ),
        'icon': 'shield',
        'featured': False,
        'url_name': 'tool_data_risk:landing',
    },
    {
        'slug': 'erp_rescue_checklist',
        'name': gettext_lazy('ERP Rescue Check'),
        'description': gettext_lazy(
            'Is your ERP quietly failing? 24 consultant-grade questions, a '
            'rescue score and your top 3 risks — in 3 minutes, no connection needed.'
        ),
        'icon': 'checklist',
        'featured': False,
        'url_name': 'tool_erp_rescue:landing',
    },
    {
        'slug': 'odoo_detector',
        'name': gettext_lazy('Odoo Instant Detector'),
        'description': gettext_lazy(
            'Paste any public website URL and find out in seconds whether it '
            'appears to run on Odoo — with confidence level and the signals found.'
        ),
        'icon': 'radar',
        'featured': False,
        'url_name': 'tool_odoo_detector:landing',
    },
    {
        'slug': 'chaos_calculator',
        'name': gettext_lazy('ERP Chaos Cost Calculator'),
        'description': gettext_lazy(
            'Spreadsheets, double entry, month-end corrections — put in your own '
            'numbers and see the estimated yearly cost of manual ERP chaos.'
        ),
        'icon': 'calculator',
        'featured': False,
        'url_name': 'tool_chaos_calc:landing',
    },
]

VALID_WAITLIST_SLUGS = {tool['slug'] for tool in TOOLS}


def hub(request):
    if request.method == 'POST':
        return _handle_waitlist_signup(request)

    track(request, 'hub', 'tool_page_view')
    context = {
        'tools': TOOLS,
        'meta_description': (
            'Free Odoo diagnostic tools by Bidatia: Studio customization X-Ray, migration '
            'readiness scanner and more. Read-only, secure, built by Odoo migration engineers.'
        ),
    }
    return render(request, 'tools_core/hub.html', context)


def _handle_waitlist_signup(request):
    email = request.POST.get('email', '').strip()
    slug = request.POST.get('tool', '')

    # Honeypot: bots fill the hidden "website" field. Pretend success so they
    # don't learn the form rejected them; create nothing.
    if request.POST.get('website'):
        messages.success(request, _("You're on the list — we'll email you once when it launches."))
        return redirect('tools_core:hub')

    if slug not in VALID_WAITLIST_SLUGS:
        messages.error(request, _('Something went wrong — please try again.'))
        return redirect('tools_core:hub')

    try:
        validate_email(email)
    except ValidationError:
        messages.error(request, _('Please enter a valid email address.'))
        return redirect('tools_core:hub')

    capture_lead(email, source_tool=f'waitlist_{slug}')
    messages.success(request, _("You're on the list — we'll email you once when it launches."))
    return redirect('tools_core:hub')


@require_POST
def test_connection_api(request):
    """Synchronous connection check used by tool landing pages before
    enabling the Run button. CSRF-protected; rate-limited per IP.

    Credentials from the request body are used for the check and discarded —
    they are never logged or stored.
    """
    if rate_limit_exceeded(f'test-connection:{client_ip(request)}', TEST_CONNECTION_LIMIT_PER_HOUR, 3600):
        return JsonResponse(
            {'ok': False, 'error': _('Too many connection attempts — please try again in an hour.')},
            status=429,
        )

    data = _request_payload(request)
    url = (data.get('url') or '').strip()
    db = (data.get('database') or data.get('db') or '').strip()
    login = (data.get('login') or '').strip()
    api_key = (data.get('api_key') or '').strip()
    if not all([url, db, login, api_key]):
        return JsonResponse(
            {'ok': False, 'error': _('URL, database, login and API key are all required.')},
            status=400,
        )

    try:
        connector = OdooXmlRpcConnector(url, db, login, api_key)
        info = connector.test_connection()
    except ConnectorError as exc:
        return JsonResponse({'ok': False, 'error': str(exc)})

    return JsonResponse({
        'ok': True,
        'server_version': info.server_version,
        'edition': info.edition,
        'user_name': info.user_name,
    })


@require_POST
def detect_database_api(request):
    """Auto-suggest the database name for a given Odoo URL. Same SSRF gate
    and best-effort philosophy as everything else: an empty answer is fine,
    the visitor can always type the name manually."""
    if rate_limit_exceeded(f'detect-db:{client_ip(request)}', DETECT_DB_LIMIT_PER_HOUR, 3600):
        return JsonResponse(
            {'ok': False, 'error': _('Too many connection attempts — please try again in an hour.')},
            status=429,
        )

    data = _request_payload(request)
    url = (data.get('url') or '').strip()
    if not url:
        return JsonResponse({'ok': False}, status=400)

    try:
        detected = detect_databases(url)
    except ConnectorError as exc:
        return JsonResponse({'ok': False, 'error': str(exc)})
    return JsonResponse({'ok': True, **detected})


def _request_payload(request):
    if request.content_type == 'application/json':
        try:
            return json.loads(request.body.decode() or '{}')
        except (ValueError, UnicodeDecodeError):
            return {}
    return request.POST


# ── internal analytics beacon ─────────────────────────────────────────────────

# Only these (tool, event) pairs may be reported from the BROWSER; everything
# else is recorded server-side where it cannot be forged as easily.
CLIENT_EVENTS = {
    ('erp_rescue', 'rescue_started'),
    ('erp_rescue', 'rescue_xray_clicked'),
    ('health_badge', 'healthy_badge_copied'),
}
TRACK_LIMIT_PER_10MIN = 60


@require_POST
def track_event(request):
    """Tiny first-party beacon for client-side funnel moments."""
    if rate_limit_exceeded(f'track:{client_ip(request)}', TRACK_LIMIT_PER_10MIN, 600):
        return JsonResponse({'ok': False}, status=429)
    body = _request_payload(request)
    pair = (str(body.get('tool') or ''), str(body.get('event') or ''))
    if pair not in CLIENT_EVENTS:
        return JsonResponse({'ok': False}, status=400)
    track(request, pair[0], pair[1])
    return JsonResponse({'ok': True})
