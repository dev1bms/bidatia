from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils.translation import gettext as _

from core.admin_links import admin_change_link
from core.seo import breadcrumb_ld, json_ld, service_ld

from .models import Service


def service_list(request):
    services = Service.objects.filter(is_published=True)
    context = {
        'services': services,
        'meta_description': _(
            'Explore BidERP Odoo and ERP technical services: paid consultations, health checks, '
            'Studio cleanup, migration assessments, custom module development, integrations and monthly support.'
        ),
    }
    return render(request, 'services/service_list.html', context)


def service_detail(request, slug):
    service = get_object_or_404(Service, slug=slug, is_published=True)
    other_services = Service.objects.filter(is_published=True).exclude(pk=service.pk)[:3]
    context = {
        'service': service,
        'other_services': other_services,
        'admin_edit': admin_change_link(request, service, _('Edit this service')),
        'meta_description': service.meta_description or service.short_description,
        'jsonld_blocks': [
            json_ld(service_ld(request, service)),
            json_ld(breadcrumb_ld(request, [
                (_('Home'), reverse('core:home')),
                (_('Services'), reverse('services:service_list')),
                (service.title, service.get_absolute_url()),
            ])),
        ],
    }
    return render(request, 'services/service_detail.html', context)
