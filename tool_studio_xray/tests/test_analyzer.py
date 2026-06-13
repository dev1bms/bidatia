import copy
import json
from pathlib import Path

from django.test import SimpleTestCase

from tool_studio_xray.analyzer import (
    SEVERITY_CRITICAL,
    SEVERITY_INFO,
    SEVERITY_WARNING,
    analyze,
)

FIXTURES = Path(__file__).parent / 'fixtures'


def load(name):
    with open(FIXTURES / name, encoding='utf-8') as f:
        return json.load(f)


class CleanDatabaseTests(SimpleTestCase):
    def setUp(self):
        self.result = analyze(load('clean_small.json'))

    def test_no_findings_for_clean_database(self):
        # 2 plain fields on a non-core model + 1 non-inheriting view: nothing to flag.
        self.assertEqual(self.result['findings'], [])

    def test_totals(self):
        totals = self.result['totals']
        self.assertEqual(totals['studio_fields'], 2)
        self.assertEqual(totals['computed_studio_fields'], 0)
        self.assertEqual(totals['plain_studio_fields'], 2)
        self.assertEqual(totals['custom_models'], 0)
        self.assertEqual(totals['code_server_actions'], 0)
        self.assertEqual(totals['studio_views'], 1)
        self.assertEqual(totals['automated_actions'], 0)

    def test_breakdown_lists_the_single_customized_model(self):
        breakdown = self.result['model_breakdown']
        self.assertEqual(breakdown[0]['model'], 'maintenance.equipment')
        self.assertEqual(breakdown[0]['fields'], 2)
        self.assertEqual(breakdown[0]['views'], 1)
        self.assertEqual(breakdown[0]['total'], 3)

    def test_no_section_errors(self):
        self.assertEqual(self.result['sections_with_errors'], [])


class HeavyDatabaseTests(SimpleTestCase):
    def setUp(self):
        self.result = analyze(load('heavy_studio.json'))
        self.by_code = {f['code']: f for f in self.result['findings']}

    def test_all_expected_findings_present_with_severities(self):
        expected = {
            'studio_fields_on_core_models': SEVERITY_WARNING,
            'computed_studio_fields': SEVERITY_WARNING,
            'custom_studio_models': SEVERITY_CRITICAL,
            'code_server_actions': SEVERITY_CRITICAL,
            'studio_view_inheritance': SEVERITY_WARNING,
            'automated_actions_present': SEVERITY_INFO,
        }
        self.assertEqual({c: f['severity'] for c, f in self.by_code.items()}, expected)

    def test_finding_counts(self):
        self.assertEqual(self.by_code['custom_studio_models']['count'], 6)
        self.assertEqual(self.by_code['code_server_actions']['count'], 8)
        self.assertEqual(self.by_code['computed_studio_fields']['count'], 15)
        self.assertEqual(self.by_code['studio_view_inheritance']['count'], 18)
        self.assertEqual(self.by_code['automated_actions_present']['count'], 12)

    def test_examples_are_capped_and_useful(self):
        examples = self.by_code['studio_fields_on_core_models']['examples']
        self.assertLessEqual(len(examples), 20)
        self.assertTrue(all('.' in e for e in examples))  # model.field format

    def test_totals_feed_scoring_inputs(self):
        totals = self.result['totals']
        self.assertEqual(totals['studio_fields'], 60)
        self.assertEqual(totals['computed_studio_fields'], 15)
        self.assertEqual(totals['plain_studio_fields'], 45)
        self.assertEqual(totals['custom_models'], 6)
        self.assertEqual(totals['code_server_actions'], 8)
        self.assertEqual(totals['studio_views'], 25)
        self.assertEqual(totals['automated_actions'], 12)
        self.assertEqual(totals['studio_menus'], 9)

    def test_breakdown_sorted_heaviest_first(self):
        breakdown = self.result['model_breakdown']
        totals = [row['total'] for row in breakdown]
        self.assertEqual(totals, sorted(totals, reverse=True))
        self.assertGreater(len(breakdown), 3)


class SectionErrorToleranceTests(SimpleTestCase):
    def test_failed_section_is_reported_and_skipped(self):
        inventory = copy.deepcopy(load('heavy_studio.json'))
        inventory['sections']['automated_actions'] = {'error': 'access denied'}
        result = analyze(inventory)
        self.assertEqual(result['sections_with_errors'], ['automated_actions'])
        self.assertEqual(result['totals']['automated_actions'], 0)
        self.assertNotIn('automated_actions_present',
                         [f['code'] for f in result['findings']])
        # other findings unaffected
        self.assertIn('custom_studio_models', [f['code'] for f in result['findings']])

    def test_empty_inventory_is_handled(self):
        result = analyze({'meta': {}, 'sections': {}})
        self.assertEqual(result['findings'], [])
        self.assertEqual(result['model_breakdown'], [])
        self.assertEqual(result['totals']['studio_fields'], 0)
