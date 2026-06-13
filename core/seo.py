"""SEO helpers: canonical URLs and JSON-LD structured data.

Centralised here so canonical/hreflang/Open-Graph URLs and schema.org markup
stay consistent across the context processor and the individual views, and so
JSON-LD is always serialised safely (never built via template interpolation,
which would HTML-escape quotes/ampersands and corrupt the JSON).
"""
import json

from django.conf import settings
from django.utils.safestring import mark_safe


def canonical_base(request):
    """Scheme + host every absolute SEO URL is built from.

    In production we pin to the configured production domain (``SITE_BASE_URL``)
    so that www/non-www and any proxy host all consolidate onto one canonical
    origin. In local development we use the live request host so links remain
    clickable.
    """
    if settings.DEBUG:
        return '%s://%s' % (request.scheme, request.get_host())
    return settings.SITE_BASE_URL.rstrip('/')


def absolute_url(request, path):
    return '%s%s' % (canonical_base(request), path or '/')


def json_ld(data):
    """Serialise ``data`` for a ``<script type="application/ld+json">`` body.

    ``mark_safe`` is correct here because the content is JSON produced from
    trusted application data (settings + model fields), and JSON string values
    have their own escaping via ``json.dumps``.
    """
    return mark_safe(json.dumps(data, ensure_ascii=False))


def organization_ld(request):
    """Sitewide Organization / ProfessionalService node.

    Deliberately conservative: no invented ratings, reviews, awards, employee
    counts or certifications.
    """
    base = canonical_base(request)
    return {
        '@context': 'https://schema.org',
        '@type': 'ProfessionalService',
        '@id': base + '/#organization',
        'name': settings.SITE_NAME,
        'description': str(settings.SITE_TAGLINE),
        'url': base + '/',
        'email': settings.CONTACT_EMAIL,
        'telephone': settings.CONTACT_WHATSAPP,
        'address': {
            '@type': 'PostalAddress',
            'addressLocality': 'Madrid',
            'addressCountry': 'ES',
        },
        'areaServed': 'Worldwide',
        'knowsAbout': [
            'Odoo ERP', 'ERP implementation', 'ERP modernization',
            'Data governance', 'Business intelligence', 'Data platforms',
            'ETL', 'AI agents', 'Process automation', 'Django', 'Python',
            'API integrations',
        ],
    }


def website_ld(request):
    base = canonical_base(request)
    return {
        '@context': 'https://schema.org',
        '@type': 'WebSite',
        '@id': base + '/#website',
        'name': settings.SITE_NAME,
        'url': base + '/',
        'publisher': {'@id': base + '/#organization'},
    }


def breadcrumb_ld(request, items):
    """Build a BreadcrumbList. ``items`` is a list of ``(name, path)`` tuples."""
    return {
        '@context': 'https://schema.org',
        '@type': 'BreadcrumbList',
        'itemListElement': [
            {
                '@type': 'ListItem',
                'position': position,
                'name': str(name),
                'item': absolute_url(request, path),
            }
            for position, (name, path) in enumerate(items, start=1)
        ],
    }


def service_ld(request, service):
    base = canonical_base(request)
    return {
        '@context': 'https://schema.org',
        '@type': 'Service',
        'name': service.title,
        'description': service.meta_description or service.short_description,
        'serviceType': service.title,
        'url': absolute_url(request, service.get_absolute_url()),
        'areaServed': 'Worldwide',
        'provider': {
            '@type': 'ProfessionalService',
            'name': settings.SITE_NAME,
            'url': base + '/',
        },
    }


def article_ld(request, post, image_url=None):
    url = absolute_url(request, post.get_absolute_url())
    data = {
        '@context': 'https://schema.org',
        '@type': 'Article',
        'headline': post.title,
        'description': post.meta_description or post.excerpt,
        'url': url,
        'mainEntityOfPage': url,
        'datePublished': post.published_at.isoformat(),
        'dateModified': post.updated_at.isoformat(),
        'author': {'@type': 'Organization', 'name': settings.SITE_NAME},
        'publisher': {'@type': 'Organization', 'name': settings.SITE_NAME},
    }
    # Prefer an explicitly resolved cover (the view passes the absolute URL of
    # the bundled slug-mapped cover); fall back to an uploaded cover_image.
    if image_url:
        data['image'] = image_url
    elif getattr(post, 'cover_image', None):
        data['image'] = absolute_url(request, post.cover_image.url)
    return data
