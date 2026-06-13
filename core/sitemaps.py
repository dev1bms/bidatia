from django.conf import settings
from django.contrib.sitemaps import Sitemap
from django.urls import reverse

from blog.models import BlogPost, CaseStudy
from glossary.data import TERMS
from pages.odoo_versions import ODOO_VERSIONS
from services.models import Service


def _canonical_domain():
    """Host portion of SITE_BASE_URL, e.g. 'bidatia.xyz'."""
    return settings.SITE_BASE_URL.split('://', 1)[-1].strip('/')


class BaseSitemap(Sitemap):
    """Shared config: emit one entry per language with hreflang alternates.

    ``i18n`` generates a URL per active language (/en/…, /es/…, /ar/…),
    ``alternates`` adds <xhtml:link rel="alternate" hreflang=…> for each, and
    ``x_default`` adds the x-default pointer. ``protocol`` forces https so the
    production sitemap always advertises secure URLs.
    """
    i18n = True
    alternates = True
    x_default = True
    protocol = 'https'

    def get_urls(self, page=1, site=None, protocol=None):
        # Pin every URL to the configured canonical domain (SITE_BASE_URL) over
        # https, so the sitemap never emits www/proxy host variants that would
        # disagree with the page-level canonical/hreflang tags.
        domain = _canonical_domain()
        site = type('CanonicalSite', (), {'domain': domain, 'name': domain})()
        return super().get_urls(page=page, site=site, protocol='https')


class StaticViewSitemap(BaseSitemap):
    changefreq = 'monthly'

    def items(self):
        return [
            'core:home', 'core:about', 'services:service_list',
            'booking:book_consultation', 'leads:contact',
            'blog:blog_list', 'case_studies:case_study_list',
            'tools_core:hub', 'tool_studio_xray:landing',
            'tool_erp_rescue:landing', 'tool_odoo_detector:landing',
            'tool_chaos_calc:landing', 'tool_data_risk:landing',
            'pages:odoo_eol_index', 'glossary:index',
            'pages:privacy', 'pages:terms',
        ]

    def location(self, item):
        return reverse(item)

    def priority(self, item):
        # The homepage is the most important static URL.
        return 1.0 if item == 'core:home' else 0.6


class OdooVersionSitemap(BaseSitemap):
    """Evergreen SEO pages — one per Odoo version support timeline."""
    priority = 0.7
    changefreq = 'weekly'  # the countdown number changes daily; weekly is honest enough

    def items(self):
        return [v['slug'] for v in ODOO_VERSIONS]

    def location(self, item):
        return reverse('pages:odoo_eol_detail', args=[item])


class GlossarySitemap(BaseSitemap):
    """Evergreen glossary term pages (Arabic-first SEO asset)."""
    priority = 0.6
    changefreq = 'monthly'

    def items(self):
        return [t['slug'] for t in TERMS]

    def location(self, item):
        return reverse('glossary:term', args=[item])


class ServiceSitemap(BaseSitemap):
    priority = 0.8
    changefreq = 'monthly'

    def items(self):
        return Service.objects.filter(is_published=True)

    def lastmod(self, obj):
        return obj.updated_at


class BlogPostSitemap(BaseSitemap):
    priority = 0.5
    changefreq = 'weekly'

    def items(self):
        return BlogPost.objects.filter(is_published=True)

    def lastmod(self, obj):
        return obj.updated_at


class CaseStudySitemap(BaseSitemap):
    priority = 0.5
    changefreq = 'monthly'

    def items(self):
        return CaseStudy.objects.filter(is_published=True)

    def lastmod(self, obj):
        return obj.updated_at


sitemaps = {
    'static': StaticViewSitemap,
    'services': ServiceSitemap,
    'blog': BlogPostSitemap,
    'case_studies': CaseStudySitemap,
    'odoo_versions': OdooVersionSitemap,
    'glossary': GlossarySitemap,
}
