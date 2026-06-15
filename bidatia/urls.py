"""
URL configuration for bidatia project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.conf import settings
from django.conf.urls.i18n import i18n_patterns
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.sitemaps.views import sitemap
from django.urls import include, path
from django.views.generic import TemplateView

from blog import urls as blog_urls
from blog.feeds import (
    LatestCaseStudiesFeed,
    LatestInsightsAtomFeed,
    LatestInsightsFeed,
)
from core import views as core_views
from core.sitemaps import sitemaps

# Non-localized URLs: no language prefix (admin, language switcher, SEO files).
urlpatterns = [
    # Outside i18n: stable path for external uptime monitoring.
    path('healthz/', core_views.healthz, name='healthz'),
    path('admin/', admin.site.urls),
    path('i18n/', include('django.conf.urls.i18n')),  # set_language view
    path('sitemap.xml', sitemap, {'sitemaps': sitemaps}, name='sitemap'),
    path('robots.txt', TemplateView.as_view(template_name='robots.txt', content_type='text/plain'), name='robots'),
    # Discovery feeds (recent published content only) — additional GSC source.
    path('feed/insights.xml', LatestInsightsFeed(), name='insights_feed'),
    path('feed/insights.atom', LatestInsightsAtomFeed(), name='insights_feed_atom'),
    path('feed/case-studies.xml', LatestCaseStudiesFeed(), name='case_studies_feed'),
]

# Localized URLs: prefixed with the active language (/en/, /es/, /ar/).
# prefix_default_language=True keeps English explicitly under /en/ and lets the
# LocaleMiddleware redirect "/" to the visitor's browser language automatically.
urlpatterns += i18n_patterns(
    path('', include('core.urls')),
    path('services/', include('services.urls')),
    path('book-consultation/', include('booking.urls')),
    path('contact/', include('leads.urls')),
    path('insights/', include('blog.urls')),
    path('case-studies/', include((blog_urls.case_study_urlpatterns, 'case_studies'), namespace='case_studies')),
    path('tools/', include('tools_core.urls')),
    path('tools/studio-xray/', include('tool_studio_xray.urls')),
    path('tools/erp-rescue/', include('tool_erp_rescue.urls')),
    path('tools/odoo-detector/', include('tool_odoo_detector.urls')),
    path('tools/erp-chaos-cost-calculator/', include('tool_chaos_calc.urls')),
    path('tools/data-risk-profiler/', include('tool_data_risk.urls')),
    path('odoo-glossary/', include('glossary.urls')),
    path('tasks/', include('jobs.urls')),
    path('', include('pages.urls')),
    prefix_default_language=True,
)

# Serve user-uploaded media during local development. In production, media is
# served by the reverse proxy (Nginx) or object storage / CDN.
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
