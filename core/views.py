from django.shortcuts import render
from django.utils.translation import gettext_lazy as _

from blog.models import CaseStudy
from services.models import Service


def home(request):
    services = Service.objects.filter(is_published=True)[:6]
    featured_service = Service.objects.filter(is_published=True, is_featured=True).first()
    case_study = CaseStudy.objects.filter(is_published=True).first()
    context = {
        'services': services,
        'featured_service': featured_service,
        'case_study': case_study,
        'meta_description': _(
            'BidERP Business Systems implements, modernizes and governs Odoo ERP — connected to your '
            'data platform, BI dashboards and AI agents. The Business Systems division of BidERP, Madrid.'
        ),
    }
    return render(request, 'core/home.html', context)


def about(request):
    context = {
        'skills': [
            _('Odoo ERP implementation & custom module development'),
            _('Odoo migration & modernization'),
            _('Data governance for ERP & CRM'),
            _('BI dashboards & management reporting'),
            _('AI agents for business processes'),
            _('ETL & data platform integration'),
            _('Python, Django & cloud engineering'),
            _('Automation & workflow optimization'),
        ],
        'meta_description': _(
            'About BidERP Business Systems — the ERP and Business Systems division of BidERP. '
            'A team of engineers bringing data, AI and governance discipline to Odoo and enterprise systems.'
        ),
    }
    return render(request, 'core/about.html', context)


def healthz(request):
    """Liveness + DB check for external uptime monitoring. No auth, no
    secrets in the response — just app-and-database-are-alive."""
    from django.db import connection
    from django.http import JsonResponse
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
            cursor.fetchone()
    except Exception:  # noqa: BLE001
        return JsonResponse({'status': 'degraded'}, status=503)
    return JsonResponse({'status': 'ok'})
