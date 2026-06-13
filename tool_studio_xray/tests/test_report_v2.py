import json
from pathlib import Path

from django.test import SimpleTestCase, TestCase, override_settings

from tool_studio_xray.analyzer import (
    LATEST_KNOWN_MAJOR,
    analyze,
    assess_upgrade,
    build_executive_summary,
    classify_module_author,
    summarize_modules,
)
from tool_studio_xray.tests.test_views import make_done_run

FIXTURES = Path(__file__).parent / 'fixtures'

MODULE_ITEMS = [
    {'name': 'sale', 'display_name': 'Sales', 'author': 'Odoo S.A.'},
    {'name': 'account', 'display_name': 'Invoicing', 'author': 'Odoo S.A.'},
    {'name': 'partner_firstname', 'display_name': 'Partner first name',
     'author': 'Camptocamp, Odoo Community Association (OCA)'},
    {'name': 'acme_connector', 'display_name': 'Acme Connector', 'author': 'Acme Corp'},
    {'name': 'internal_tweaks', 'display_name': 'Internal Tweaks', 'author': ''},
]


def sections_with_modules(installed_total=42, studio=True):
    return {
        'installed_modules': {'items': MODULE_ITEMS, 'total': len(MODULE_ITEMS)},
        'module_context': {'installed_modules': installed_total, 'studio_installed': studio},
    }


class ClassifyModuleAuthorTests(SimpleTestCase):
    def test_classification_rules(self):
        self.assertEqual(classify_module_author('Odoo S.A.'), 'official')
        self.assertEqual(classify_module_author('Odoo'), 'official')
        # OCA listed together with the original author -> OCA wins
        self.assertEqual(
            classify_module_author('Camptocamp, Odoo Community Association (OCA)'), 'oca')
        self.assertEqual(classify_module_author('Acme Corp'), 'third_party')
        self.assertEqual(classify_module_author(''), 'custom')
        self.assertEqual(classify_module_author(None), 'custom')


class SummarizeModulesTests(SimpleTestCase):
    def test_summary_counts_and_examples(self):
        summary = summarize_modules(sections_with_modules())
        self.assertEqual(summary['installed_total'], 42)
        self.assertTrue(summary['studio_installed'])
        self.assertEqual(summary['by_origin'],
                         {'official': 2, 'oca': 1, 'third_party': 1, 'custom': 1})
        self.assertEqual(summary['non_standard_total'], 3)
        self.assertEqual(summary['examples']['third_party'], ['Acme Connector'])

    def test_missing_section_returns_none(self):
        self.assertIsNone(summarize_modules({}))
        self.assertIsNone(summarize_modules({'installed_modules': {'error': 'denied'}}))

    def test_errored_module_context_falls_back_to_items(self):
        sections = sections_with_modules()
        sections['module_context'] = {'error': 'denied'}
        summary = summarize_modules(sections)
        self.assertEqual(summary['installed_total'], len(MODULE_ITEMS))
        self.assertFalse(summary['studio_installed'])  # web_studio not in items


class AnalyzeModuleIntegrationTests(SimpleTestCase):
    def test_analyze_emits_module_summary_and_finding(self):
        inventory = {'meta': {}, 'sections': sections_with_modules()}
        result = analyze(inventory)
        self.assertEqual(result['module_summary']['non_standard_total'], 3)
        self.assertEqual(result['totals']['non_standard_modules'], 3)
        by_code = {f['code']: f for f in result['findings']}
        self.assertIn('non_standard_modules', by_code)
        self.assertEqual(by_code['non_standard_modules']['severity'], 'info')  # 3 < 15

    def test_warning_severity_at_threshold(self):
        many = [{'name': 'm%d' % i, 'display_name': 'M%d' % i, 'author': 'Vendor'}
                for i in range(15)]
        inventory = {'meta': {}, 'sections': {
            'installed_modules': {'items': many, 'total': 15},
        }}
        by_code = {f['code']: f for f in analyze(inventory)['findings']}
        self.assertEqual(by_code['non_standard_modules']['severity'], 'warning')

    def test_old_inventory_without_module_section_is_unchanged(self):
        with open(FIXTURES / 'heavy_studio.json', encoding='utf-8') as f:
            result = analyze(json.load(f))
        self.assertIsNone(result['module_summary'])
        self.assertEqual(result['totals']['non_standard_modules'], 0)
        self.assertNotIn('non_standard_modules',
                         [f['code'] for f in result['findings']])


class AssessUpgradeTests(SimpleTestCase):
    def test_version_parsing(self):
        self.assertEqual(assess_upgrade('15.0', 0)['detected_major'], 15)
        self.assertEqual(assess_upgrade('saas~17.2', 0)['detected_major'], 17)
        self.assertEqual(assess_upgrade('19.0', 0)['gap'], 0)

    def test_unparseable_or_implausible_returns_none(self):
        self.assertIsNone(assess_upgrade('', 50))
        self.assertIsNone(assess_upgrade(None, 50))
        self.assertIsNone(assess_upgrade('unknown', 50))
        self.assertIsNone(assess_upgrade('7.0', 50))

    def test_friction_matrix(self):
        self.assertEqual(assess_upgrade(str(LATEST_KNOWN_MAJOR), 5)['friction'], 'minimal')
        self.assertEqual(assess_upgrade(str(LATEST_KNOWN_MAJOR), 50)['friction'], 'moderate')
        self.assertEqual(assess_upgrade(str(LATEST_KNOWN_MAJOR - 2), 50)['friction'], 'moderate')
        self.assertEqual(assess_upgrade(str(LATEST_KNOWN_MAJOR - 2), 90)['friction'], 'high')
        self.assertEqual(assess_upgrade(str(LATEST_KNOWN_MAJOR - 4), 10)['friction'], 'high')
        self.assertEqual(assess_upgrade(str(LATEST_KNOWN_MAJOR - 4), 90)['friction'], 'very_high')

    def test_support_window(self):
        self.assertTrue(assess_upgrade(str(LATEST_KNOWN_MAJOR - 2), 0)['within_support_window'])
        self.assertFalse(assess_upgrade(str(LATEST_KNOWN_MAJOR - 3), 0)['within_support_window'])


class ExecutiveSummaryTests(SimpleTestCase):
    def _findings(self, *codes, count=5):
        return [{'code': c, 'count': count} for c in codes]

    def test_top_risks_priority_and_cap(self):
        findings = self._findings(
            'automated_actions_present', 'studio_view_inheritance',
            'computed_studio_fields', 'studio_fields_on_core_models',
            'code_server_actions', 'custom_studio_models')
        summary = build_executive_summary(findings, 80)
        self.assertEqual([r['code'] for r in summary['risks']],
                         ['custom_studio_models', 'code_server_actions',
                          'studio_fields_on_core_models'])

    def test_version_gap_risk_included_when_gap_large(self):
        upgrade = {'gap': 4}
        summary = build_executive_summary([], 10, upgrade=upgrade)
        self.assertEqual(summary['risks'], [{'code': 'version_gap', 'count': 4}])

    def test_small_module_count_not_headlined(self):
        findings = self._findings('non_standard_modules', count=3)
        summary = build_executive_summary(findings, 10)
        self.assertEqual(summary['risks'], [])

    def test_next_step_codes(self):
        rebuild = build_executive_summary(self._findings('custom_studio_models'), 10)
        self.assertEqual(rebuild['next_step'], 'rebuild')
        cleanup = build_executive_summary(self._findings('computed_studio_fields'), 60)
        self.assertEqual(cleanup['next_step'], 'cleanup_before_upgrade')
        review = build_executive_summary(self._findings('automated_actions_present'), 5)
        self.assertEqual(review['next_step'], 'targeted_review')
        healthy = build_executive_summary([], 0)
        self.assertEqual(healthy['next_step'], 'healthy')


@override_settings(ALLOWED_HOSTS=['testserver'])
class ReportV2ViewTests(TestCase):
    """Old payloads keep rendering; new sections appear when data exists."""

    def test_old_payload_renders_with_executive_summary(self):
        run = make_done_run()  # pre-v2 payload: no 'modules' key
        resp = self.client.get(f'/en/tools/studio-xray/report/{run.pk}/')
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        self.assertIn('Executive summary', content)
        self.assertIn('Recommended next step', content)
        self.assertIn('Why this score', content)        # inputs/weights exist in old payloads too
        self.assertIn('Upgrade readiness', content)      # derived from meta.server_version
        self.assertIn('Print or save as PDF', content)
        self.assertNotIn('Installed modules', content)   # no modules key -> card hidden

    def test_new_payload_renders_module_card(self):
        run = make_done_run()
        run.result_json['modules'] = {
            'installed_total': 42, 'studio_installed': True,
            'by_origin': {'official': 38, 'oca': 2, 'third_party': 1, 'custom': 1},
            'non_standard_total': 4,
            'examples': {'oca': ['Partner first name'], 'third_party': ['Acme Connector'],
                         'custom': ['Internal Tweaks']},
        }
        run.save(update_fields=['result_json'])
        resp = self.client.get(f'/en/tools/studio-xray/report/{run.pk}/')
        content = resp.content.decode()
        self.assertIn('Installed modules', content)
        self.assertIn('not standard Odoo', content)
        self.assertIn('Acme Connector', content)
        self.assertIn('OCA / Community', content)

    def test_action_plan_renders_groups(self):
        run = make_done_run()
        resp = self.client.get(f'/en/tools/studio-xray/report/{run.pk}/')
        content = resp.content.decode()
        self.assertIn('Recommended action plan', content)
        # payload has custom models (structural) + automations (quick) + core fields? no — check groups present
        self.assertIn('Structural work', content)
        self.assertIn('Quick wins', content)
        self.assertIn('Upgrade preparation', content)    # 17.0 -> gap 2

    def test_scoring_with_zero_raw_points_renders(self):
        run = make_done_run()
        run.result_json['scoring'] = {'score': 0, 'raw_points': 0, 'effort_estimate': '1–3 days',
                                      'effort_note': 'n', 'inputs': {}, 'weights': {}}
        run.result_json['analysis']['findings'] = []
        run.save(update_fields=['result_json'])
        resp = self.client.get(f'/en/tools/studio-xray/report/{run.pk}/')
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn('Why this score', resp.content.decode())  # no rows -> hidden

    def test_arabic_rtl_report_renders(self):
        run = make_done_run()
        resp = self.client.get(f'/ar/tools/studio-xray/report/{run.pk}/')
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        self.assertIn('dir="rtl"', content)
        # language-independent markers: the exec-summary print button and the
        # score gauge must render on the RTL page without template errors
        self.assertIn('window.print()', content)
        self.assertIn('37', content)


class ProvenanceFilteringTests(SimpleTestCase):
    def test_module_shipped_code_actions_are_not_critical(self):
        inventory = {'meta': {}, 'sections': {
            'server_actions': {'items': [
                {'name': 'Custom hack', 'state': 'code', 'from_module': False},
                {'name': 'Send an email', 'state': 'code', 'from_module': True},
                {'name': 'Auto-vacuum', 'state': 'code', 'from_module': True},
            ], 'total': 3},
        }}
        result = analyze(inventory)
        by_code = {f['code']: f for f in result['findings']}
        self.assertEqual(by_code['code_server_actions']['count'], 1)
        self.assertEqual(by_code['code_server_actions']['examples'], ['Custom hack'])
        self.assertEqual(result['totals']['code_server_actions'], 1)
        self.assertEqual(result['totals']['shipped_code_server_actions'], 2)

    def test_all_shipped_means_no_code_finding_at_all(self):
        inventory = {'meta': {}, 'sections': {
            'server_actions': {'items': [
                {'name': 'Send an email', 'state': 'code', 'from_module': True},
            ], 'total': 1},
        }}
        result = analyze(inventory)
        self.assertNotIn('code_server_actions', [f['code'] for f in result['findings']])
        self.assertEqual(result['totals']['code_server_actions'], 0)

    def test_shipped_automations_excluded(self):
        inventory = {'meta': {}, 'sections': {
            'automated_actions': {'items': [
                {'name': 'Mine', 'trigger': 'on_create', 'from_module': False},
                {'name': 'Shipped', 'trigger': 'on_create', 'from_module': True},
            ], 'total': 2},
        }}
        result = analyze(inventory)
        self.assertEqual(result['totals']['automated_actions'], 1)

    def test_old_inventory_without_flags_counts_everything(self):
        # pre-v2.1 inventories have no from_module key -> previous behavior
        inventory = {'meta': {}, 'sections': {
            'server_actions': {'items': [
                {'name': 'A', 'state': 'code'}, {'name': 'B', 'state': 'code'},
            ], 'total': 2},
        }}
        result = analyze(inventory)
        by_code = {f['code']: f for f in result['findings']}
        self.assertEqual(by_code['code_server_actions']['count'], 2)


@override_settings(ALLOWED_HOSTS=['testserver'])
class LocalizedFindingTests(TestCase):
    def test_known_finding_codes_get_view_layer_titles(self):
        run = make_done_run()
        resp = self.client.get(f'/en/tools/studio-xray/report/{run.pk}/')
        # the stored payload has the old v1 title; the view swaps in the
        # code-based one (identical in English for this code)
        self.assertContains(resp, 'Custom models created with Studio')

    def test_unknown_finding_code_falls_back_to_stored_text(self):
        run = make_done_run()
        run.result_json['analysis']['findings'].append({
            'code': 'future_check', 'severity': 'info', 'section': 'x',
            'title': 'A future finding title', 'detail': 'Stored detail text.',
            'count': 1, 'examples': []})
        run.save(update_fields=['result_json'])
        resp = self.client.get(f'/en/tools/studio-xray/report/{run.pk}/')
        self.assertContains(resp, 'A future finding title')

    def test_effort_estimate_translated_on_arabic_page(self):
        run = make_done_run()
        resp = self.client.get(f'/ar/tools/studio-xray/report/{run.pk}/')
        content = resp.content.decode()
        # '4–8 days' must no longer appear raw — its Arabic catalog entry does
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn('4–8 days', content)
