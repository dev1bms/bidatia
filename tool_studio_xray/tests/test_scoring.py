import json
from pathlib import Path

from django.test import SimpleTestCase

from tool_studio_xray.analyzer import analyze
from tool_studio_xray.scoring import EFFORT_NOTE, WEIGHTS, compute_score

FIXTURES = Path(__file__).parent / 'fixtures'


def fields(n):
    """totals dict with n plain fields — raw points == n (weight 1)."""
    return {'plain_studio_fields': n}


class ScoringBandTests(SimpleTestCase):
    def test_zero_inventory_scores_zero_lowest_band(self):
        result = compute_score({})
        self.assertEqual(result['score'], 0)
        self.assertEqual(result['raw_points'], 0)
        self.assertEqual(result['effort_estimate'], '1–3 days')

    def test_band_boundaries(self):
        # raw points -> score (raw * 100 / 250) -> band
        cases = [
            (38, 15, '1–3 days'),    # top of band 1
            (40, 16, '4–8 days'),    # bottom of band 2
            (100, 40, '4–8 days'),   # top of band 2
            (103, 41, '2–3 weeks'),  # bottom of band 3
            (175, 70, '2–3 weeks'),  # top of band 3
            (178, 71, '4+ weeks'),   # bottom of band 4
            (250, 100, '4+ weeks'),  # saturation
            (1000, 100, '4+ weeks'),  # capped at 100
        ]
        for raw, expected_score, expected_band in cases:
            with self.subTest(raw=raw):
                result = compute_score(fields(raw))
                self.assertEqual(result['score'], expected_score)
                self.assertEqual(result['effort_estimate'], expected_band)

    def test_weights_match_plan(self):
        self.assertEqual(WEIGHTS, {
            'plain_studio_fields': 1,
            'computed_studio_fields': 3,
            'studio_views': 2,
            'automated_actions': 3,
            'code_server_actions': 5,
            'custom_models': 8,
        })

    def test_weighted_sum(self):
        result = compute_score({
            'plain_studio_fields': 10,   # 10
            'computed_studio_fields': 2,  # 6
            'studio_views': 3,            # 6
            'automated_actions': 1,       # 3
            'code_server_actions': 2,     # 10
            'custom_models': 1,           # 8
        })
        self.assertEqual(result['raw_points'], 43)
        self.assertEqual(result['score'], 17)
        self.assertEqual(result['effort_estimate'], '4–8 days')

    def test_output_is_a_range_never_a_price(self):
        result = compute_score(fields(120))
        text = json.dumps(result)
        for currency in ('€', '$', 'EUR', 'USD', 'price'):
            self.assertNotIn(currency, text)
        self.assertEqual(result['effort_note'], EFFORT_NOTE)
        self.assertIn('weights', result)
        self.assertIn('inputs', result)


class EndToEndFixtureTests(SimpleTestCase):
    """Inventory JSON -> analyzer -> scoring, exactly as the M5 task will chain them."""

    def _score(self, fixture):
        with open(FIXTURES / fixture, encoding='utf-8') as f:
            inventory = json.load(f)
        return compute_score(analyze(inventory)['totals'])

    def test_clean_small_database_lowest_band(self):
        result = self._score('clean_small.json')
        self.assertEqual(result['raw_points'], 4)   # 2 fields + 1 view*2
        self.assertEqual(result['score'], 2)
        self.assertEqual(result['effort_estimate'], '1–3 days')

    def test_heavy_studio_database_saturates(self):
        result = self._score('heavy_studio.json')
        self.assertEqual(result['raw_points'], 264)
        self.assertEqual(result['score'], 100)
        self.assertEqual(result['effort_estimate'], '4+ weeks')
