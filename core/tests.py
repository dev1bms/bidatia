import json
import re
import xml.etree.ElementTree as ET
from io import StringIO

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings

from blog.models import BlogPost, CaseStudy
from core.seo import canonical_base
from core.templatetags.i18n_urls import build_language_url
from services.models import Service

_LD_RE = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)
_LOC_RE = re.compile(r'<loc>(.*?)</loc>')
_SITEMAP_NS = {'s': 'http://www.sitemaps.org/schemas/sitemap/0.9'}


def _ld_types(html):
    """Parse every JSON-LD block (validating it is well-formed) and return the
    list of @type values found on the page."""
    types = []
    for block in _LD_RE.findall(html):
        data = json.loads(block)  # raises if escaping corrupted the JSON
        types.append(data.get('@type'))
    return types


class BuildLanguageUrlTests(SimpleTestCase):
    """Unit tests for the language-prefix rewriting helper."""

    def test_replaces_leading_language_segment(self):
        self.assertEqual(build_language_url('/en/', '', 'ar'), '/ar/')
        self.assertEqual(build_language_url('/en/services/', '', 'ar'), '/ar/services/')
        self.assertEqual(build_language_url('/es/contact/', '', 'en'), '/en/contact/')
        self.assertEqual(
            build_language_url('/ar/services/odoo-health-check/', '', 'es'),
            '/es/services/odoo-health-check/',
        )

    def test_root_path_gets_prefixed(self):
        self.assertEqual(build_language_url('/', '', 'ar'), '/ar/')
        self.assertEqual(build_language_url('/', '', 'en'), '/en/')

    def test_query_string_is_preserved(self):
        self.assertEqual(
            build_language_url('/en/book-consultation/', 'service=odoo-health-check', 'ar'),
            '/ar/book-consultation/?service=odoo-health-check',
        )

    def test_unknown_prefix_is_prepended_not_replaced(self):
        # A path without a recognised language prefix keeps its first segment.
        self.assertEqual(build_language_url('/services/', '', 'ar'), '/ar/services/')


@override_settings(ALLOWED_HOSTS=['testserver'])
class LanguageSwitcherViewTests(TestCase):
    """Integration tests: rendered switcher links and i18n routing."""

    def test_switcher_links_point_to_other_languages(self):
        resp = self.client.get('/en/services/')
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        self.assertIn('href="/es/services/"', content)
        self.assertIn('href="/ar/services/"', content)

    def test_query_string_preserved_in_links(self):
        resp = self.client.get('/en/book-consultation/?service=odoo-health-check')
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        self.assertIn('href="/ar/book-consultation/?service=odoo-health-check"', content)

    def test_following_switch_link_changes_active_language(self):
        resp = self.client.get('/ar/services/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers.get('Content-Language'), 'ar')

    def test_arabic_is_rtl_and_others_ltr(self):
        ar = self.client.get('/ar/services/').content.decode()
        self.assertIn('dir="rtl"', ar)
        for lang in ('/en/services/', '/es/services/'):
            html = self.client.get(lang).content.decode()
            self.assertIn('dir="ltr"', html)


# DEBUG=False mirrors production: canonical/hreflang/OG URLs pin to SITE_BASE_URL.
@override_settings(DEBUG=False, ALLOWED_HOSTS=['testserver'], SITE_BASE_URL='https://bidatia.xyz')
class SeoHeadTests(TestCase):
    """Canonical, hreflang, OG locale and sitewide JSON-LD in the page head."""

    def test_canonical_is_self_referencing_per_language(self):
        for lang in ('en', 'es', 'ar'):
            html = self.client.get(f'/{lang}/services/').content.decode()
            self.assertIn(
                f'<link rel="canonical" href="https://bidatia.xyz/{lang}/services/">',
                html,
            )

    def test_hreflang_alternates_reference_all_languages(self):
        html = self.client.get('/en/services/').content.decode()
        for lang in ('en', 'es', 'ar'):
            self.assertIn(
                f'hreflang="{lang}" href="https://bidatia.xyz/{lang}/services/"',
                html,
            )
        self.assertIn('hreflang="x-default"', html)

    def test_og_locale_matches_active_language(self):
        self.assertIn('content="en_US"', self.client.get('/en/').content.decode())
        self.assertIn('content="es_ES"', self.client.get('/es/').content.decode())
        self.assertIn('content="ar_AR"', self.client.get('/ar/').content.decode())

    def test_sitewide_jsonld_is_valid_and_present(self):
        types = _ld_types(self.client.get('/en/').content.decode())
        self.assertIn('ProfessionalService', types)
        self.assertIn('WebSite', types)

    def test_public_pages_are_indexable(self):
        for url in ('/en/', '/en/services/', '/en/contact/', '/en/book-consultation/'):
            html = self.client.get(url).content.decode()
            self.assertNotIn('noindex', html)

    def test_og_image_defaults_to_bundled_card(self):
        # With no env override, the bundled 1200x630 card is used (absolute URL).
        html = self.client.get('/en/').content.decode()
        self.assertIn(
            '<meta property="og:image" content="https://bidatia.xyz/static/img/og.png">',
            html,
        )
        self.assertIn('<meta property="og:image:width" content="1200">', html)
        self.assertIn('<meta property="og:image:height" content="630">', html)
        self.assertIn('name="twitter:image" content="https://bidatia.xyz/static/img/og.png"', html)

    @override_settings(OG_DEFAULT_IMAGE='https://cdn.example.com/custom-og.png')
    def test_og_image_env_override_wins(self):
        html = self.client.get('/en/').content.decode()
        self.assertIn('content="https://cdn.example.com/custom-og.png"', html)


@override_settings(ALLOWED_HOSTS=['testserver'])
class SeoStructuredDataTests(TestCase):
    """Per-page schema.org nodes on detail pages."""

    def setUp(self):
        self.service = Service.objects.create(
            title='Odoo Health Check',
            slug='seo-test-service',
            short_description='A focused technical audit of your Odoo system.',
            description='Full audit.\nClear fix list.',
            price_label='From €350',
            is_published=True,
        )

    def test_service_detail_has_service_and_breadcrumb(self):
        html = self.client.get(f'/en/services/{self.service.slug}/').content.decode()
        types = _ld_types(html)
        self.assertIn('Service', types)
        self.assertIn('BreadcrumbList', types)
        # And the sitewide nodes are still present.
        self.assertIn('ProfessionalService', types)


@override_settings(ALLOWED_HOSTS=['testserver'], SITE_BASE_URL='https://bidatia.xyz')
class SeoSitemapRobotsTests(TestCase):
    def _sitemap(self):
        resp = self.client.get('/sitemap.xml')
        self.assertEqual(resp.status_code, 200)
        return resp

    def test_sitemap_returns_200_and_is_valid_xml(self):
        resp = self._sitemap()
        # Correct content type (not text/html / plain text).
        self.assertTrue(resp['Content-Type'].startswith(('application/xml', 'text/xml')))
        # Parses as real XML with the sitemaps.org urlset root (not concatenated text).
        root = ET.fromstring(resp.content)
        self.assertEqual(root.tag, '{http://www.sitemaps.org/schemas/sitemap/0.9}urlset')
        self.assertTrue(root.findall('s:url', _SITEMAP_NS))

    def test_sitemap_has_i18n_alternates(self):
        body = self._sitemap().content.decode()
        self.assertIn('xhtml:link', body)
        self.assertIn('hreflang="x-default"', body)
        for lang in ('/en/', '/es/', '/ar/'):
            self.assertIn(lang, body)

    def test_loc_urls_are_clean_and_absolute(self):
        body = self._sitemap().content.decode()
        locs = _LOC_RE.findall(body)
        self.assertGreater(len(locs), 0)
        # Catches the feared "changefreq/priority glued onto the URL" bug, e.g.
        # .../monthly1.0 — a real URL would never have a digit after a freq word.
        glued = re.compile(r'(monthly|weekly|daily|always|hourly|yearly|never)\d')
        for loc in locs:
            self.assertTrue(loc.startswith('https://'), f'not absolute https: {loc}')
            self.assertTrue(loc.endswith('/'), f'loc should end with a slash: {loc}')
            self.assertNotIn(' ', loc)
            self.assertIsNone(glued.search(loc), f'sitemap metadata leaked into URL: {loc}')
            self.assertNotIn('/admin', loc)
            self.assertNotIn('/i18n', loc)

    def test_important_public_pages_present_in_all_languages(self):
        body = self._sitemap().content.decode()
        paths = ('', 'services/', 'about/', 'contact/',
                 'book-consultation/', 'insights/', 'case-studies/')
        for lang in ('en', 'es', 'ar'):
            for path in paths:
                self.assertIn(f'https://bidatia.xyz/{lang}/{path}', body)

    def test_robots_returns_200_and_points_to_sitemap(self):
        resp = self.client.get('/robots.txt')
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        self.assertIn('Disallow: /admin/', body)
        self.assertIn('/sitemap.xml', body)


@override_settings(ALLOWED_HOSTS=['testserver'])
class SitemapContentDiscoveryTests(TestCase):
    """New published content appears in the sitemap (with lastmod) and on the
    listing pages; unpublished content appears in neither."""

    def setUp(self):
        self.pub_service = Service.objects.create(
            title='Published Service', slug='pub-service', short_description='x',
            description='x', price_label='From €1', is_published=True)
        Service.objects.create(
            title='Draft Service', slug='draft-service', short_description='x',
            description='x', price_label='From €1', is_published=False)
        self.pub_post = BlogPost.objects.create(
            title='Published Insight', slug='pub-insight', excerpt='x',
            content='x', is_published=True)
        BlogPost.objects.create(
            title='Draft Insight', slug='draft-insight', excerpt='x',
            content='x', is_published=False)
        self.pub_case = CaseStudy.objects.create(
            title='Published Case', slug='pub-case', client_summary='x',
            challenge='x', approach='x', results='x', is_published=True)
        CaseStudy.objects.create(
            title='Draft Case', slug='draft-case', client_summary='x',
            challenge='x', approach='x', results='x', is_published=False)

    def _sitemap_body(self):
        return self.client.get('/sitemap.xml').content.decode()

    def test_published_items_appear_immediately(self):
        body = self._sitemap_body()
        for slug in ('pub-service', 'pub-insight', 'pub-case'):
            self.assertIn(f'/{slug}/', body)

    def test_unpublished_items_are_excluded(self):
        body = self._sitemap_body()
        for slug in ('draft-service', 'draft-insight', 'draft-case'):
            self.assertNotIn(f'/{slug}/', body)

    def test_dynamic_entries_carry_lastmod(self):
        root = ET.fromstring(self._sitemap_body())
        checked = 0
        for url in root.findall('s:url', _SITEMAP_NS):
            loc = url.find('s:loc', _SITEMAP_NS).text
            if any(s in loc for s in ('/pub-insight/', '/pub-service/', '/pub-case/')):
                self.assertIsNotNone(
                    url.find('s:lastmod', _SITEMAP_NS), f'missing <lastmod> for {loc}')
                checked += 1
        self.assertGreaterEqual(checked, 3)

    def test_published_items_linked_from_listing_pages(self):
        for lang in ('en', 'es', 'ar'):
            self.assertIn(
                f'/{lang}/services/pub-service/',
                self.client.get(f'/{lang}/services/').content.decode())
            self.assertIn(
                f'/{lang}/insights/pub-insight/',
                self.client.get(f'/{lang}/insights/').content.decode())
            self.assertIn(
                f'/{lang}/case-studies/pub-case/',
                self.client.get(f'/{lang}/case-studies/').content.decode())

    def test_unpublished_items_not_linked(self):
        self.assertNotIn('/draft-service/', self.client.get('/en/services/').content.decode())
        self.assertNotIn('/draft-insight/', self.client.get('/en/insights/').content.decode())
        self.assertNotIn('/draft-case/', self.client.get('/en/case-studies/').content.decode())


@override_settings(
    ALLOWED_HOSTS=['testserver', 'www.other.example'],
    SITE_BASE_URL='https://bidatia.xyz',
)
class DiscoveryFeedTests(TestCase):
    """RSS/Atom feeds: valid, published-only, canonical-English links pinned to
    SITE_BASE_URL (never the request host)."""

    def setUp(self):
        self.pub = BlogPost.objects.create(
            title='Feed Published', slug='feed-pub', excerpt='hello world',
            content='x', is_published=True)
        BlogPost.objects.create(
            title='Feed Draft', slug='feed-draft', excerpt='x',
            content='x', is_published=False)
        self.case = CaseStudy.objects.create(
            title='Feed Case', slug='feed-case', client_summary='x',
            challenge='x', approach='x', results='x', is_published=True)

    def test_insights_rss_is_valid_and_published_only(self):
        resp = self.client.get('/feed/insights.xml')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('xml', resp['Content-Type'])
        ET.fromstring(resp.content)  # parseable
        body = resp.content.decode()
        self.assertIn('Feed Published', body)
        self.assertNotIn('Feed Draft', body)
        # Items link to the canonical English URL on the pinned origin.
        self.assertIn('https://bidatia.xyz/en/insights/feed-pub/', body)

    def test_feed_urls_pinned_to_canonical_origin_not_request_host(self):
        # Even when served via an allowed non-canonical host, every URL in the
        # feed must use SITE_BASE_URL, matching the sitemap/canonical design.
        resp = self.client.get('/feed/insights.xml', HTTP_HOST='www.other.example')
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        self.assertIn('https://bidatia.xyz/en/insights/feed-pub/', body)
        self.assertNotIn('www.other.example', body)

    def test_insights_atom_is_valid(self):
        resp = self.client.get('/feed/insights.atom')
        self.assertEqual(resp.status_code, 200)
        ET.fromstring(resp.content)

    def test_case_studies_feed_is_valid(self):
        resp = self.client.get('/feed/case-studies.xml')
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        self.assertIn('Feed Case', body)
        self.assertIn('/en/case-studies/feed-case/', body)

    def test_feed_autodiscovery_links_in_head(self):
        html = self.client.get('/en/').content.decode()
        self.assertIn('type="application/rss+xml"', html)
        self.assertIn('/feed/insights.xml', html)
        self.assertIn('/feed/case-studies.xml', html)


class CanonicalBaseTests(SimpleTestCase):
    """The canonical origin is pinned in production, request-based in dev."""

    @override_settings(DEBUG=False, SITE_BASE_URL='https://bidatia.xyz')
    def test_pins_to_site_base_url_in_production(self):
        request = RequestFactory().get('/en/')
        self.assertEqual(canonical_base(request), 'https://bidatia.xyz')

    @override_settings(DEBUG=True)
    def test_uses_request_host_in_development(self):
        request = RequestFactory().get('/en/')
        self.assertTrue(canonical_base(request).endswith('testserver'))


@override_settings(ALLOWED_HOSTS=['testserver'])
class AdminTests(TestCase):
    """Admin is protected, the Unfold dashboard renders, and every business
    model is registered and browsable."""

    @classmethod
    def setUpTestData(cls):
        from blog.models import BlogPost, CaseStudy
        from booking.models import ConsultationRequest
        from leads.models import Lead
        from services.models import Service

        cls.admin = get_user_model().objects.create_superuser(
            username='boss', email='boss@bidatia.xyz', password='x')
        # A little data so the dashboard/changelists have rows to render.
        Service.objects.create(title='Svc', slug='svc-admin', short_description='x',
                               description='x', price_label='€1', is_published=True)
        BlogPost.objects.create(title='Post', slug='post-admin', excerpt='x',
                                content='x', is_published=True)
        CaseStudy.objects.create(title='Case', slug='case-admin', client_summary='x',
                                 challenge='x', approach='x', results='x', is_published=True)
        ConsultationRequest.objects.create(
            full_name='Jane', email='jane@x.com', phone='+34 600', country='ES',
            consultation_type='intro_call', problem_summary='hi', consent=True)
        Lead.objects.create(name='Bob', email='bob@x.com', message='hello')

    def test_admin_index_redirects_anonymous(self):
        resp = self.client.get('/admin/')
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/admin/login/', resp['Location'])

    def test_admin_index_dashboard_renders_for_superuser(self):
        self.client.force_login(self.admin)
        resp = self.client.get('/admin/')
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        # Dashboard KPI cards + recent panels are present.
        self.assertIn('Published services', body)
        self.assertIn('Recent consultation requests', body)
        self.assertIn('dbms-kpi', body)

    def test_key_models_are_registered(self):
        from blog.models import BlogPost, CaseStudy
        from booking.models import AvailabilitySlot, ConsultationRequest
        from leads.models import Lead
        from services.models import Service
        for model in (Service, BlogPost, CaseStudy, ConsultationRequest, AvailabilitySlot, Lead):
            self.assertIn(model, admin.site._registry)

    def test_changelists_load_for_superuser(self):
        self.client.force_login(self.admin)
        for url in (
            '/admin/booking/consultationrequest/',
            '/admin/booking/availabilityslot/',
            '/admin/leads/lead/',
            '/admin/services/service/',
            '/admin/blog/blogpost/',
            '/admin/blog/casestudy/',
        ):
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_translated_change_form_renders(self):
        # The Unfold + modeltranslation combination must render per-language
        # fields on translated content models.
        self.client.force_login(self.admin)
        resp = self.client.get('/admin/services/service/add/')
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        for field in ('name="title_en"', 'name="title_es"', 'name="title_ar"'):
            self.assertIn(field, body)


@override_settings(ALLOWED_HOSTS=['testserver'], SITE_BASE_URL='https://bidatia.xyz')
class SeedContentTests(TestCase):
    """The market-ready content seed produces the full, trilingual catalogue and
    surfaces it through the public site, sitemap and feeds."""

    NEW_SERVICE_SLUGS = (
        'odoo-crm-sales-workflow-optimization',
        'odoo-accounting-invoicing-process-review',
        'odoo-automation-server-actions-review',
    )
    NEW_ARTICLE_SLUGS = (
        'planning-a-move-to-odoo-19-what-to-check-before-you-upgrade',
        'how-django-and-odoo-work-together-to-close-process-gaps',
        'outgrowing-spreadsheets-signs-your-business-needs-a-real-erp',
    )

    @classmethod
    def setUpTestData(cls):
        call_command('seed_demo_data', stdout=StringIO())

    def test_published_services_and_insights_counts(self):
        from blog.models import BlogPost
        from services.models import Service
        self.assertEqual(Service.objects.filter(is_published=True).count(), 15)
        self.assertEqual(BlogPost.objects.filter(is_published=True).count(), 9)

    def test_every_article_has_a_bundled_slug_cover(self):
        # Each seeded article maps to its own committed static cover (not the
        # shared default), so cards and social previews show a topical image.
        from blog.covers import DEFAULT_COVER, cover_static_name
        from blog.models import BlogPost
        for post in BlogPost.objects.filter(is_published=True):
            name = cover_static_name(post)
            self.assertEqual(name, f'img/insights/{post.slug}.png', post.slug)
            self.assertNotEqual(name, DEFAULT_COVER, post.slug)

    def test_default_cover_is_bundled(self):
        from django.contrib.staticfiles import finders
        self.assertIsNotNone(finders.find('img/insights/default.png'))

    def test_article_detail_has_cover_and_social_image(self):
        slug = 'outgrowing-spreadsheets-signs-your-business-needs-a-real-erp'
        html = self.client.get(f'/en/insights/{slug}/').content.decode()
        self.assertIn(f'/static/img/insights/{slug}.png', html)   # hero image
        self.assertIn('property="og:image"', html)                # social card
        self.assertIn('name="twitter:image"', html)

    def test_insights_list_shows_all_covers(self):
        html = self.client.get('/en/insights/').content.decode()
        self.assertEqual(html.count('/static/img/insights/'), 9)

    def test_new_services_have_all_three_languages_and_features(self):
        from services.models import Service
        for slug in self.NEW_SERVICE_SLUGS:
            s = Service.objects.get(slug=slug)
            self.assertTrue(s.title_en and s.title_es and s.title_ar, slug)
            self.assertTrue(s.description_es and s.description_ar, slug)
            self.assertTrue(s.meta_description_es and s.meta_description_ar, slug)
            self.assertGreaterEqual(s.features.count(), 1, slug)

    def test_new_articles_have_all_three_languages(self):
        from blog.models import BlogPost
        for slug in self.NEW_ARTICLE_SLUGS:
            p = BlogPost.objects.get(slug=slug)
            self.assertTrue(p.excerpt_es and p.excerpt_ar, slug)
            self.assertTrue(p.content_es and p.content_ar, slug)
            self.assertTrue(p.meta_description_es and p.meta_description_ar, slug)

    def test_seed_is_idempotent(self):
        from services.models import Service
        call_command('seed_demo_data', stdout=StringIO())
        self.assertEqual(Service.objects.filter(is_published=True).count(), 15)

    def test_new_content_appears_in_sitemap(self):
        body = self.client.get('/sitemap.xml').content.decode()
        for slug in self.NEW_SERVICE_SLUGS:
            self.assertIn(f'/services/{slug}/', body)
        for slug in self.NEW_ARTICLE_SLUGS:
            self.assertIn(f'/insights/{slug}/', body)

    def test_new_article_appears_in_feed(self):
        feed = self.client.get('/feed/insights.xml').content.decode()
        self.assertIn('Odoo 19', feed)

    def test_new_service_detail_page_renders(self):
        html = self.client.get('/en/services/odoo-crm-sales-workflow-optimization/').content.decode()
        self.assertIn('CRM', html)

    def test_twelve_case_studies_with_translations(self):
        from blog.models import CaseStudy
        self.assertEqual(CaseStudy.objects.filter(is_published=True).count(), 12)
        cs = CaseStudy.objects.get(
            slug='auditing-years-of-odoo-studio-changes-at-a-freight-forwarding-company')
        self.assertTrue(cs.challenge_es and cs.challenge_ar)
        self.assertTrue(cs.approach_es and cs.approach_ar)
        self.assertTrue(cs.results_es and cs.results_ar)
        self.assertTrue(cs.meta_description_es and cs.meta_description_ar)

    def test_new_case_study_in_sitemap_and_detail_page(self):
        slug = 'auditing-years-of-odoo-studio-changes-at-a-freight-forwarding-company'
        self.assertIn(f'/case-studies/{slug}/', self.client.get('/sitemap.xml').content.decode())
        for lang in ('en', 'es', 'ar'):
            self.assertEqual(self.client.get(f'/{lang}/case-studies/{slug}/').status_code, 200)


@override_settings(ALLOWED_HOSTS=['testserver'])
class AdminToolbarTests(TestCase):
    """Staff-only frontend admin toolbar: visibility, edit links, permissions
    and cache safety."""

    MARKER = 'dbms-adminbar'

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.superuser = User.objects.create_superuser('boss2', 'boss2@bidatia.xyz', 'x')
        cls.staff_no_perms = User.objects.create_user('staffx', 'staffx@bidatia.xyz', 'x', is_staff=True)
        cls.normal = User.objects.create_user('viewer', 'viewer@bidatia.xyz', 'x')

        from blog.models import BlogPost, CaseStudy
        from services.models import Service
        cls.service = Service.objects.create(
            title='Toolbar Service', slug='toolbar-service', short_description='x',
            description='x', price_label='From €1', is_published=True)
        cls.post = BlogPost.objects.create(
            title='Toolbar Insight', slug='toolbar-insight', excerpt='x', content='x', is_published=True)
        cls.case = CaseStudy.objects.create(
            title='Toolbar Case', slug='toolbar-case', client_summary='x',
            challenge='x', approach='x', results='x', is_published=True)

    # ── Visibility ────────────────────────────────────────────────────────────
    def test_anonymous_does_not_see_toolbar(self):
        html = self.client.get('/en/').content.decode()
        self.assertNotIn(self.MARKER, html)

    def test_normal_user_does_not_see_toolbar(self):
        self.client.force_login(self.normal)
        html = self.client.get('/en/').content.decode()
        self.assertNotIn(self.MARKER, html)

    def test_staff_sees_toolbar_and_dashboard(self):
        self.client.force_login(self.superuser)
        html = self.client.get('/en/').content.decode()
        self.assertIn(self.MARKER, html)
        self.assertIn('Admin dashboard', html)
        self.assertIn('/admin/', html)
        self.assertIn('Services', html)
        self.assertIn('Consultation requests', html)

    # ── Per-object edit links ─────────────────────────────────────────────────
    def test_staff_sees_edit_this_service(self):
        self.client.force_login(self.superuser)
        html = self.client.get(f'/en/services/{self.service.slug}/').content.decode()
        self.assertIn('Edit this service', html)
        self.assertIn(f'/admin/services/service/{self.service.pk}/change/', html)

    def test_staff_sees_edit_this_insight(self):
        self.client.force_login(self.superuser)
        html = self.client.get(f'/en/insights/{self.post.slug}/').content.decode()
        self.assertIn('Edit this insight', html)
        self.assertIn(f'/admin/blog/blogpost/{self.post.pk}/change/', html)

    def test_staff_sees_edit_this_case_study(self):
        self.client.force_login(self.superuser)
        html = self.client.get(f'/en/case-studies/{self.case.slug}/').content.decode()
        self.assertIn('Edit this case study', html)
        self.assertIn(f'/admin/blog/casestudy/{self.case.pk}/change/', html)

    # ── Permission awareness ──────────────────────────────────────────────────
    def test_staff_without_change_perm_sees_toolbar_but_no_edit_link(self):
        self.client.force_login(self.staff_no_perms)
        html = self.client.get(f'/en/services/{self.service.slug}/').content.decode()
        self.assertIn(self.MARKER, html)          # toolbar shows (is_staff)
        self.assertNotIn('Edit this service', html)  # but no edit (no change perm)

    def test_normal_user_sees_no_edit_link(self):
        self.client.force_login(self.normal)
        html = self.client.get(f'/en/services/{self.service.slug}/').content.decode()
        self.assertNotIn('Edit this service', html)

    # ── Cache safety ──────────────────────────────────────────────────────────
    def test_authenticated_response_is_not_cacheable(self):
        self.client.force_login(self.superuser)
        resp = self.client.get('/en/')
        self.assertIn('no-store', resp['Cache-Control'])
        self.assertIn('private', resp['Cache-Control'])
        self.assertIn('Cookie', resp.get('Vary', ''))

    def test_anonymous_response_is_not_forced_no_store(self):
        resp = self.client.get('/en/')
        self.assertNotIn('no-store', resp.get('Cache-Control', ''))

    # ── Public pages still render ─────────────────────────────────────────────
    def test_public_pages_render_for_anonymous(self):
        for url in ('/en/', f'/en/services/{self.service.slug}/',
                    f'/en/insights/{self.post.slug}/', f'/en/case-studies/{self.case.slug}/'):
            self.assertEqual(self.client.get(url).status_code, 200, url)
