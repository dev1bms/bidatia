"""Syndication feeds for fast content discovery.

Served at non-localized URLs (e.g. /feed/insights.xml). Every emitted URL —
the feed self-link, item links and item GUIDs — is pinned to the canonical
origin (SITE_BASE_URL) and to the English version of each item, so feeds stay
consistent with the host-pinned sitemap and page canonicals regardless of which
(allowed) host actually served the request. Only published content appears.
"""
from django.conf import settings
from django.contrib.syndication.views import Feed
from django.urls import reverse
from django.utils import translation
from django.utils.feedgenerator import Atom1Feed

from .models import BlogPost, CaseStudy


def _origin():
    """Canonical scheme+host, e.g. 'https://bidatia.xyz' (no trailing slash)."""
    return settings.SITE_BASE_URL.rstrip('/')


def _abs_en(path_or_item):
    """Absolute canonical (English) URL. Accepts a model instance or a path.

    Returning a fully-qualified URL makes Django's syndication add_domain() a
    no-op, so the request host can never override the canonical origin.
    """
    with translation.override('en'):
        path = path_or_item if isinstance(path_or_item, str) else path_or_item.get_absolute_url()
    return _origin() + path


class _PinnedFeed(Feed):
    """Base feed that pins the self-link and feed_url to the canonical origin."""
    list_url_name = None   # e.g. 'blog:blog_list'
    feed_url_name = None   # e.g. 'insights_feed'

    def link(self):
        with translation.override('en'):
            return _origin() + reverse(self.list_url_name)

    def feed_url(self):
        return _origin() + reverse(self.feed_url_name)

    def item_link(self, item):
        return _abs_en(item)


class LatestInsightsFeed(_PinnedFeed):
    """RSS 2.0 feed of the most recent published insight articles."""
    title = 'Bidatia Insights'
    description = (
        'Practical articles on Odoo, ERP automation, Django integrations and '
        'business technology from Bidatia, Madrid.'
    )
    list_url_name = 'blog:blog_list'
    feed_url_name = 'insights_feed'

    def items(self):
        return BlogPost.objects.filter(is_published=True).order_by('-published_at')[:20]

    def item_title(self, item):
        return item.title

    def item_description(self, item):
        return item.meta_description or item.excerpt

    def item_pubdate(self, item):
        return item.published_at

    def item_updateddate(self, item):
        return item.updated_at


class LatestInsightsAtomFeed(LatestInsightsFeed):
    """Atom 1.0 variant of the insights feed."""
    feed_type = Atom1Feed
    subtitle = LatestInsightsFeed.description
    feed_url_name = 'insights_feed_atom'


class LatestCaseStudiesFeed(_PinnedFeed):
    """RSS 2.0 feed of the most recent published case studies."""
    title = 'Bidatia Case Studies'
    description = (
        'Recent Odoo and ERP technical case studies delivered by Bidatia — '
        'audits, migrations, integrations and ongoing support.'
    )
    list_url_name = 'case_studies:case_study_list'
    feed_url_name = 'case_studies_feed'

    def items(self):
        return CaseStudy.objects.filter(is_published=True).order_by('-created_at')[:20]

    def item_title(self, item):
        return item.title

    def item_description(self, item):
        return item.meta_description or item.client_summary

    def item_pubdate(self, item):
        return item.created_at

    def item_updateddate(self, item):
        return item.updated_at
