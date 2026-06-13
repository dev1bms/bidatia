from datetime import date

from django.core.cache import cache
from django.test import SimpleTestCase, TestCase, override_settings

from tools_core.models import ToolEvent

from .odoo_versions import (
    ODOO_VERSIONS,
    STATUS_ENDED,
    STATUS_ENDING_SOON,
    STATUS_SUPPORTED,
    annotate,
    annotated_versions,
    get_version,
)


class VersionDataIntegrityTests(SimpleTestCase):
    def test_every_entry_is_complete_and_consistent(self):
        slugs = set()
        for v in ODOO_VERSIONS:
            self.assertRegex(v['slug'], r'^odoo-\d+$')
            self.assertNotIn(v['slug'], slugs)
            slugs.add(v['slug'])
            self.assertEqual(v['slug'], 'odoo-%d' % v['major'])
            self.assertIsInstance(v['release_date'], date)
            self.assertIsInstance(v['support_end'], date)
            self.assertLess(v['release_date'], v['support_end'])
            # Accuracy rule: every support-end claim must carry the
            # estimated flag so templates phrase it as a planning horizon.
            self.assertTrue(v['support_end_estimated'])

    def test_ordered_newest_first(self):
        majors = [v['major'] for v in ODOO_VERSIONS]
        self.assertEqual(majors, sorted(majors, reverse=True))

    def test_get_version(self):
        self.assertIsNotNone(get_version('odoo-16'))
        self.assertIsNone(get_version('odoo-99'))

    def test_annotate_statuses(self):
        v = get_version('odoo-17')  # support_end 2026-10-01
        far_before = annotate(v, today=date(2024, 1, 1))
        self.assertEqual(far_before['status'], STATUS_SUPPORTED)
        self.assertGreater(far_before['days_left'], 365)

        close = annotate(v, today=date(2026, 6, 1))
        self.assertEqual(close['status'], STATUS_ENDING_SOON)
        self.assertGreater(close['days_left'], 0)

        after = annotate(v, today=date(2027, 1, 1))
        self.assertEqual(after['status'], STATUS_ENDED)
        self.assertEqual(after['days_left'], 0)
        self.assertGreater(after['days_since_end'], 0)

    def test_annotated_versions_covers_all(self):
        self.assertEqual(len(annotated_versions()), len(ODOO_VERSIONS))


@override_settings(ALLOWED_HOSTS=['testserver'])
class EolPageTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_index_renders_all_versions_in_all_languages(self):
        for lang in ('en', 'es', 'ar'):
            response = self.client.get(f'/{lang}/odoo-version-support/')
            self.assertEqual(response.status_code, 200)
        response = self.client.get('/en/odoo-version-support/')
        for v in ODOO_VERSIONS:
            self.assertContains(response, v['name'])
            self.assertContains(response, f"/en/odoo-version-support/{v['slug']}/")

    def test_detail_renders_with_countdown_and_faq_schema(self):
        response = self.client.get('/en/odoo-version-support/odoo-18/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Odoo 18')
        self.assertContains(response, 'FAQPage')
        self.assertContains(response, 'planning horizon')
        # estimated wording must be present (accuracy rule)
        self.assertContains(response, 'stimated')

    def test_detail_handles_past_dates_gracefully(self):
        response = self.client.get('/en/odoo-version-support/odoo-14/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'days since the estimated end of support')

    def test_unknown_version_404s(self):
        self.assertEqual(
            self.client.get('/en/odoo-version-support/odoo-99/').status_code, 404)

    def test_page_view_events_recorded_with_version(self):
        self.client.get('/en/odoo-version-support/')
        self.client.get('/en/odoo-version-support/odoo-16/')
        events = ToolEvent.objects.filter(tool='odoo_eol',
                                          event='odoo_eol_page_view')
        versions = {e.metadata.get('version') for e in events}
        self.assertIn('index', versions)
        self.assertIn('odoo-16', versions)

    def test_cta_redirects_track(self):
        response = self.client.get('/en/odoo-version-support/odoo-16/go/xray/')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], '/en/tools/studio-xray/')
        self.assertTrue(ToolEvent.objects.filter(
            tool='odoo_eol', event='odoo_eol_xray_clicked').exists())

        response = self.client.get('/en/odoo-version-support/odoo-16/go/rescue/')
        self.assertEqual(response['Location'], '/en/tools/erp-rescue/')
        self.assertTrue(ToolEvent.objects.filter(
            tool='odoo_eol', event='odoo_eol_rescue_clicked').exists())

    def test_sitemap_includes_version_pages(self):
        response = self.client.get('/sitemap.xml')
        content = response.content.decode()
        self.assertIn('/odoo-version-support/odoo-16/', content)
        self.assertIn('/odoo-version-support/', content)
