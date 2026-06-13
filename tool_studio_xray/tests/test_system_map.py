from django.core.cache import cache
from django.test import SimpleTestCase, TestCase, override_settings

from tools_core.models import ToolEvent

from tool_studio_xray.demo import build_result_json, get_or_create_demo_run
from tool_studio_xray.system_map import MAX_NODES, build_map


class BuildMapTests(SimpleTestCase):
    def test_demo_report_produces_rich_map(self):
        system_map = build_map(build_result_json())
        self.assertIsNotNone(system_map)
        self.assertGreaterEqual(len(system_map['nodes']), 5)
        self.assertLessEqual(len(system_map['nodes']), MAX_NODES)
        self.assertIn('16.0', system_map['center_label'])
        # The demo has 6 automations on one model — they fan into a capped
        # bundle of threads, not a single ambiguous line.
        self.assertGreaterEqual(len(system_map['threads']), 3)
        self.assertGreater(system_map['automation_total'], 0)
        # Every ring is captioned so readers can decode the orbits.
        self.assertEqual([r['label'] for r in system_map['rings']],
                         ['Core', 'Standard', 'Custom'])

    def test_node_classification_and_colors(self):
        system_map = build_map(build_result_json())
        by_model = {n['model']: n for n in system_map['nodes']}

        critical = by_model['x_air_waybill']  # 41,902 records
        self.assertEqual(critical['kind'], 'custom')
        self.assertEqual(critical['fill'], '#be123c')
        self.assertEqual(critical['opacity'], 1.0)
        self.assertEqual(critical['sub'], '41.9k records')

        dead = by_model['x_test_model']  # zero records
        self.assertEqual(dead['fill'], '#94a3b8')
        self.assertLess(dead['opacity'], 1.0)

        core = by_model['sale.order']
        self.assertEqual(core['kind'], 'core')
        self.assertEqual(core['fill'], '#f59e0b')
        self.assertIsNotNone(core['halo_r'])  # has custom fields → halo

    def test_geometry_stays_inside_viewbox(self):
        system_map = build_map(build_result_json())
        for node in system_map['nodes']:
            self.assertGreater(node['x'], 0)
            self.assertLess(node['x'], system_map['view_w'])
            self.assertGreater(node['y'], 0)
            self.assertLess(node['sub_y'], system_map['view_h'])

    def test_insufficient_data_returns_none(self):
        self.assertIsNone(build_map(None))
        self.assertIsNone(build_map({}))
        self.assertIsNone(build_map({'analysis': {'model_breakdown': [
            {'model': 'sale.order', 'fields': 2, 'views': 0,
             'automations': 0, 'total': 2}]}}))

    def test_map_without_usage_data_still_works(self):
        """Old reports (no v3 usage block) must still get a map."""
        result = build_result_json()
        result.pop('usage', None)
        system_map = build_map(result)
        self.assertIsNotNone(system_map)
        for node in system_map['nodes']:
            # without usage data the stat line falls back to customization
            # counts — never to record counts it does not have
            self.assertNotIn('records', node['sub'])

    def test_deterministic_output(self):
        result = build_result_json()
        self.assertEqual(build_map(result), build_map(result))

    def test_svg_coordinates_survive_decimal_comma_locales(self):
        """Regression: Arabic ('٫') and Spanish (',') decimal separators must
        never leak into SVG coordinates — that scrambles the whole drawing.
        Every numeric attribute must parse as a plain float in every locale."""
        import xml.etree.ElementTree as ET

        from django.template.loader import render_to_string
        from django.utils import translation

        numeric_attrs = ('cx', 'cy', 'r', 'x', 'y', 'x1', 'y1', 'x2', 'y2',
                         'width', 'height', 'stroke-width', 'font-size')
        for lang in ('en', 'es', 'ar'):
            with self.subTest(lang=lang), translation.override(lang):
                svg = render_to_string('tool_studio_xray/_system_map.html',
                                       {'map': build_map(build_result_json())})
                root = ET.fromstring(svg)  # malformed SVG would raise here
                checked = 0
                for element in root.iter():
                    for attr in numeric_attrs:
                        value = element.get(attr)
                        if value is not None:
                            float(value)  # raises on '614٫9' or '614,9'
                            checked += 1
                    if element.tag.endswith('path'):
                        for token in element.get('d', '').replace(
                                'M', ' ').replace('Q', ' ').split():
                            float(token)
                            checked += 1
                self.assertGreater(checked, 50)


@override_settings(ALLOWED_HOSTS=['testserver'])
class SystemMapViewTests(TestCase):
    def setUp(self):
        cache.clear()
        self.run = get_or_create_demo_run()

    def test_demo_report_renders_map_section(self):
        response = self.client.get(f'/en/tools/studio-xray/report/{self.run.pk}/')
        self.assertContains(response, 'Your Odoo Customization Map')
        self.assertContains(response, '<svg xmlns="http://www.w3.org/2000/svg"')
        self.assertContains(response, 'map.svg')
        self.assertTrue(ToolEvent.objects.filter(
            tool='studio_xray', event='xray_system_map_viewed').exists())

    def test_map_svg_endpoint_serves_svg(self):
        response = self.client.get(
            f'/en/tools/studio-xray/report/{self.run.pk}/map.svg')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'image/svg+xml')
        self.assertNotIn('Content-Disposition', response)
        # 'private' keeps the Cloudflare edge from caching the .svg past
        # the report's 72h expiry (it caches by extension otherwise).
        self.assertIn('private', response['Cache-Control'])
        self.assertIn(b'bidatia.xyz', response.content)
        self.assertTrue(ToolEvent.objects.filter(
            event='xray_system_map_opened').exists())

    def test_map_svg_download_sets_attachment(self):
        response = self.client.get(
            f'/en/tools/studio-xray/report/{self.run.pk}/map.svg?download=1')
        self.assertIn('attachment', response['Content-Disposition'])
        self.assertTrue(ToolEvent.objects.filter(
            event='xray_system_map_downloaded').exists())

    def test_expired_or_dataless_run_404s(self):
        from django.utils import timezone

        self.run.expires_at = timezone.now()
        self.run.save(update_fields=['expires_at'])
        response = self.client.get(
            f'/en/tools/studio-xray/report/{self.run.pk}/map.svg')
        self.assertEqual(response.status_code, 404)

    def test_report_without_map_data_hides_section(self):
        import uuid

        from tools_core.models import ToolRun

        run = ToolRun.objects.create(
            id=uuid.uuid4(), tool_slug='studio_xray', status='done',
            odoo_url='https://x.example.com', odoo_db='x',
            result_json={'meta': {}, 'analysis': {'findings': [], 'totals': {},
                                                  'model_breakdown': []},
                         'scoring': {'score': 0, 'level': 'low'}},
        )
        response = self.client.get(f'/en/tools/studio-xray/report/{run.pk}/')
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Your Odoo Customization Map')
