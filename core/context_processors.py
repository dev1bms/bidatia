from django.conf import settings
from django.templatetags.static import static
from django.urls import NoReverseMatch, reverse
from django.utils import translation
from django.utils.translation import gettext_lazy as _

from core.seo import (
    canonical_base,
    json_ld,
    organization_ld,
    website_ld,
)
# Reuse the exact language-prefix rewriting the on-page switcher uses, so
# canonical/hreflang URLs stay perfectly consistent with the visible links.
from core.templatetags.i18n_urls import _LANG_CODES, _PREFIX_RE, build_language_url

# schema.org/Open-Graph "og:locale" codes for each site language.
_OG_LOCALES = {'en': 'en_US', 'es': 'es_ES', 'ar': 'ar_AR'}


def site_settings(request):
    return {
        'SITE_NAME': settings.SITE_NAME,
        'SITE_BRAND': settings.SITE_BRAND,
        'SITE_DIVISION': settings.SITE_DIVISION,
        'SITE_TAGLINE': settings.SITE_TAGLINE,
        'CONTACT_EMAIL': settings.CONTACT_EMAIL,
        'CONTACT_WHATSAPP': settings.CONTACT_WHATSAPP,
        'SITE_CITY': settings.SITE_CITY,
        'ENABLE_ANALYTICS': settings.ENABLE_ANALYTICS,
        'GA_MEASUREMENT_ID': settings.GA_MEASUREMENT_ID,
        'GOOGLE_SITE_VERIFICATION': settings.GOOGLE_SITE_VERIFICATION,
    }


def admin_toolbar(request):
    """Data for the staff-only frontend admin toolbar.

    Returns an empty/disabled marker for everyone except active staff, so the
    partial renders nothing for anonymous or normal users. Section links are
    each gated on the matching ``view`` permission (the admin enforces this too).
    """
    user = getattr(request, 'user', None)
    if not (user and user.is_authenticated and user.is_active and user.is_staff):
        return {'show_admin_toolbar': False}

    def link(perm, url_name, label):
        if not user.has_perm(perm):
            return None
        try:
            return {'label': label, 'url': reverse(url_name)}
        except NoReverseMatch:
            return None

    candidates = [
        link('services.view_service', 'admin:services_service_changelist', _('Services')),
        link('blog.view_blogpost', 'admin:blog_blogpost_changelist', _('Insights')),
        link('blog.view_casestudy', 'admin:blog_casestudy_changelist', _('Case studies')),
        link('booking.view_consultationrequest',
             'admin:booking_consultationrequest_changelist', _('Consultation requests')),
        link('booking.view_availabilityslot',
             'admin:booking_availabilityslot_changelist', _('Availability slots')),
        link('leads.view_lead', 'admin:leads_lead_changelist', _('Leads')),
    ]
    try:
        dashboard_url = reverse('admin:index')
    except NoReverseMatch:
        dashboard_url = '/admin/'

    return {
        'show_admin_toolbar': True,
        'admin_toolbar_dashboard': dashboard_url,
        'admin_toolbar_links': [item for item in candidates if item],
    }


def seo(request):
    """Canonical URL, hreflang alternates, OG locale and sitewide JSON-LD.

    Available on every page rendered with ``base.html``.
    """
    base = canonical_base(request)
    path = request.path

    # Default social-share card: use the env override if set, otherwise the
    # bundled 1200x630 OG image (always an absolute, domain-correct URL).
    og_image = settings.OG_DEFAULT_IMAGE or ('%s%s' % (base, static('img/og.png')))

    context = {
        'SITE_BASE_URL': base,
        'OG_DEFAULT_IMAGE': og_image,
        'canonical_url': '%s%s' % (base, path),
        'jsonld_org': json_ld(organization_ld(request)),
        'jsonld_website': json_ld(website_ld(request)),
    }

    # Only language-prefixed pages (/en/…, /es/…, /ar/…) get hreflang/OG-locale
    # alternates. Non-localised paths (admin, sitemap.xml, robots.txt) skip them.
    match = _PREFIX_RE.match(path or '/')
    if match and match.group('lang') in _LANG_CODES:
        context['hreflang_alternates'] = [
            {'lang': code, 'url': '%s%s' % (base, build_language_url(path, '', code))}
            for code, _name in settings.LANGUAGES
        ]
        # x-default points at the default language version (English).
        context['x_default_url'] = '%s%s' % (
            base, build_language_url(path, '', settings.LANGUAGE_CODE),
        )
        current = translation.get_language()
        context['og_locale'] = _OG_LOCALES.get(current, 'en_US')
        context['og_locale_alternates'] = [
            code for lang, code in _OG_LOCALES.items() if lang != current
        ]

    return context
