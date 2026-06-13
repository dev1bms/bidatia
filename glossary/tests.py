from django.core.cache import cache
from django.test import SimpleTestCase, TestCase, override_settings

from tools_core.models import ToolEvent

from .data import CATEGORY_ORDER, TERMS, get_term, localized, terms_by_category
from .views import CATEGORY_LABELS

REQUIRED_TEXT_FIELDS = ('title', 'definition', 'example', 'why', 'mistake')


class GlossaryDataIntegrityTests(SimpleTestCase):
    def test_mvp_scope_30_plus_terms(self):
        self.assertGreaterEqual(len(TERMS), 30)

    def test_every_term_is_complete_in_arabic_and_english(self):
        slugs = set()
        for term in TERMS:
            with self.subTest(slug=term['slug']):
                self.assertRegex(term['slug'], r'^[a-z0-9-]+$')
                self.assertNotIn(term['slug'], slugs)
                slugs.add(term['slug'])
                self.assertIn(term['category'], CATEGORY_ORDER)
                self.assertIn(term['cta'], ('xray', 'rescue', ''))
                for field in REQUIRED_TEXT_FIELDS:
                    for lang in ('ar', 'en'):
                        value = term[field].get(lang, '')
                        # Titles can be legitimately short ("ORM", "View");
                        # the long-form fields must be real sentences.
                        minimum = 2 if field == 'title' else 30
                        self.assertTrue(value and len(value) >= minimum,
                                        f"{term['slug']}.{field}.{lang} too short")

    def test_related_slugs_exist_and_never_self_reference(self):
        slugs = {t['slug'] for t in TERMS}
        for term in TERMS:
            for related in term['related']:
                self.assertIn(related, slugs,
                              f"{term['slug']} references unknown {related}")
                self.assertNotEqual(related, term['slug'])

    def test_every_category_has_a_label(self):
        for category in CATEGORY_ORDER:
            self.assertIn(category, CATEGORY_LABELS)

    def test_localized_fallback_spanish_gets_english(self):
        term = get_term('odoo-studio')
        spanish = localized(term, 'es')
        english = localized(term, 'en')
        self.assertEqual(spanish['definition'], english['definition'])
        arabic = localized(term, 'ar')
        self.assertNotEqual(arabic['definition'], english['definition'])

    def test_grouping_covers_all_terms(self):
        grouped = terms_by_category()
        self.assertEqual(sum(len(v) for v in grouped.values()), len(TERMS))


@override_settings(ALLOWED_HOSTS=['testserver'])
class GlossaryPageTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_index_renders_in_all_languages(self):
        for lang in ('en', 'es', 'ar'):
            response = self.client.get(f'/{lang}/odoo-glossary/')
            self.assertEqual(response.status_code, 200)
        response = self.client.get('/ar/odoo-glossary/')
        self.assertContains(response, 'ستوديو أودو')  # Arabic-first content
        self.assertTrue(ToolEvent.objects.filter(
            tool='glossary', event='glossary_index_view').exists())

    def test_index_links_every_term(self):
        response = self.client.get('/en/odoo-glossary/')
        for term in TERMS:
            self.assertContains(response, f"/en/odoo-glossary/{term['slug']}/")

    def test_term_page_renders_with_structured_data(self):
        response = self.client.get('/en/odoo-glossary/odoo-studio/')
        self.assertContains(response, 'Odoo Studio')
        self.assertContains(response, 'DefinedTerm')
        self.assertContains(response, 'BreadcrumbList')
        self.assertTrue(ToolEvent.objects.filter(
            tool='glossary', event='glossary_term_view',
            metadata__term='odoo-studio').exists())

    def test_arabic_term_page_shows_arabic_content(self):
        response = self.client.get('/ar/odoo-glossary/custom-field/')
        self.assertContains(response, 'حقل مخصص')
        self.assertContains(response, 'x_studio')

    def test_unknown_term_404s(self):
        self.assertEqual(
            self.client.get('/en/odoo-glossary/odoo-flying-car/').status_code, 404)

    def test_cta_redirect_tracks_and_routes_by_term(self):
        response = self.client.get('/en/odoo-glossary/odoo-studio/go/')
        self.assertEqual(response['Location'], '/en/tools/studio-xray/')
        response = self.client.get('/en/odoo-glossary/ir-cron/go/')
        self.assertEqual(response['Location'], '/en/tools/erp-rescue/')
        self.assertEqual(ToolEvent.objects.filter(
            tool='glossary', event='glossary_tool_cta_clicked').count(), 2)

    def test_related_terms_render_as_links(self):
        response = self.client.get('/en/odoo-glossary/odoo-studio/')
        self.assertContains(response, '/en/odoo-glossary/custom-field/')

    def test_sitemap_includes_glossary(self):
        content = self.client.get('/sitemap.xml').content.decode()
        self.assertIn('/odoo-glossary/', content)
        self.assertIn('/odoo-glossary/odoo-studio/', content)
