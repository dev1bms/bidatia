from django.core.cache import cache
from django.test import SimpleTestCase, TestCase, override_settings

from tools_core.models import ToolEvent

from .calculator import InvalidInput, compute


class FormulaTests(SimpleTestCase):
    def test_per_employee_path(self):
        result = compute(employees=10, hours_per_employee=4, hourly_cost=35)
        self.assertEqual(result['weekly_hours'], 40.0)
        self.assertEqual(result['weekly_cost'], 1400)
        self.assertEqual(result['yearly_cost'], 1400 * 52)
        self.assertEqual(result['monthly_cost'], round(1400 * 52 / 12))

    def test_total_hours_overrides_per_employee(self):
        result = compute(employees=99, hours_per_employee=80,
                         total_weekly_hours=10, hourly_cost=20)
        self.assertEqual(result['weekly_hours'], 10.0)
        self.assertEqual(result['weekly_cost'], 200)

    def test_rework_adds_monthly_cost(self):
        result = compute(total_weekly_hours=10, hourly_cost=20,
                         rework_hours_month=15)
        self.assertEqual(result['rework_yearly_cost'], 15 * 20 * 12)
        self.assertEqual(result['yearly_cost'], 10 * 20 * 52 + 15 * 20 * 12)

    def test_decimal_comma_accepted(self):
        result = compute(total_weekly_hours='2,5', hourly_cost='40')
        self.assertEqual(result['weekly_hours'], 2.5)

    def test_invalid_inputs_raise_with_field_code(self):
        cases = [
            (dict(employees=0, hours_per_employee=4, hourly_cost=35), 'employees'),
            (dict(employees=10, hours_per_employee=500, hourly_cost=35),
             'hours_per_employee'),
            (dict(total_weekly_hours='abc', hourly_cost=35), 'total_weekly_hours'),
            (dict(total_weekly_hours=10, hourly_cost=-5), 'hourly_cost'),
            (dict(total_weekly_hours=10, hourly_cost=35,
                  rework_hours_month='x'), 'rework_hours_month'),
            (dict(total_weekly_hours='inf', hourly_cost=35), 'total_weekly_hours'),
        ]
        for kwargs, field in cases:
            with self.subTest(field=field):
                with self.assertRaises(InvalidInput) as ctx:
                    compute(**kwargs)
                self.assertEqual(str(ctx.exception), field)

    def test_zero_rework_is_fine(self):
        result = compute(total_weekly_hours=10, hourly_cost=20, rework_hours_month=0)
        self.assertEqual(result['rework_yearly_cost'], 0)


@override_settings(ALLOWED_HOSTS=['testserver'])
class CalculatorPageTests(TestCase):
    URL = '/en/tools/erp-chaos-cost-calculator/'

    def setUp(self):
        cache.clear()

    def test_renders_in_all_languages(self):
        for lang in ('en', 'es', 'ar'):
            response = self.client.get(f'/{lang}/tools/erp-chaos-cost-calculator/')
            self.assertEqual(response.status_code, 200)
        self.assertTrue(ToolEvent.objects.filter(
            tool='chaos_calculator', event='chaos_calculator_page_view').exists())

    def test_successful_calculation_renders_and_tracks(self):
        response = self.client.post(self.URL, {
            'employees': '10', 'hours_per_employee': '4', 'hourly_cost': '35',
            'rework_hours_month': '', 'total_weekly_hours': '', 'currency': 'EUR',
        })
        self.assertContains(response, '72,800')  # 10*4*35*52
        self.assertContains(response, 'not financial advice')
        event = ToolEvent.objects.get(tool='chaos_calculator',
                                      event='chaos_calculator_completed')
        self.assertEqual(event.metadata['yearly_cost'], 72800)
        self.assertEqual(event.metadata['currency'], 'EUR')

    def test_invalid_input_polite_error(self):
        response = self.client.post(self.URL, {
            'employees': '10', 'hours_per_employee': '4', 'hourly_cost': 'banana',
            'currency': 'EUR',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'hourly cost')
        self.assertFalse(ToolEvent.objects.filter(
            event='chaos_calculator_completed').exists())

    def test_missing_hours_inputs_polite_error(self):
        response = self.client.post(self.URL, {'hourly_cost': '35', 'currency': 'EUR'})
        self.assertContains(response, 'Tell us either')

    def test_unknown_currency_falls_back_to_eur(self):
        response = self.client.post(self.URL, {
            'total_weekly_hours': '10', 'hourly_cost': '20', 'currency': 'XXX',
        })
        self.assertContains(response, '€')

    def test_honeypot_redirects(self):
        response = self.client.post(self.URL, {
            'total_weekly_hours': '10', 'hourly_cost': '20', 'website': 'spam',
        })
        self.assertEqual(response.status_code, 302)
        self.assertFalse(ToolEvent.objects.exists())

    def test_cta_redirects_track(self):
        response = self.client.get(self.URL + 'go/rescue/')
        self.assertEqual(response['Location'], '/en/tools/erp-rescue/')
        response = self.client.get(self.URL + 'go/xray/')
        self.assertEqual(response['Location'], '/en/tools/studio-xray/')
        events = set(ToolEvent.objects.filter(tool='chaos_calculator')
                     .values_list('event', flat=True))
        self.assertIn('chaos_calculator_rescue_clicked', events)
        self.assertIn('chaos_calculator_xray_clicked', events)

    def test_hub_shows_calculator_card(self):
        response = self.client.get('/en/tools/')
        self.assertContains(response, 'ERP Chaos Cost Calculator')
        self.assertContains(response, '/en/tools/erp-chaos-cost-calculator/')
