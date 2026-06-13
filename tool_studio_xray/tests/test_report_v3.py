"""Report v3: identity header, system pulse, usage tiers, code footprint."""
from unittest import mock

from django.test import SimpleTestCase, TestCase, override_settings

from tool_studio_xray.analyzer import (
    analyze, summarize_code, summarize_identity, summarize_usage,
)
from tool_studio_xray.collector import collect
from tool_studio_xray.scoring import compute_score
from tool_studio_xray.tests.test_collector import INFO, FakeConnector
from tool_studio_xray.tests.test_views import make_done_run


class CollectorV3Tests(SimpleTestCase):
    def test_identity_usage_and_pulse_sections_collected(self):
        sections = collect(FakeConnector(), INFO)['sections']

        identity = sections['identity']
        self.assertEqual(identity['company_name'], 'Boss Continental')
        self.assertEqual(identity['company_city'], 'Madrid')
        self.assertEqual(identity['company_country'], 'Spain')
        self.assertEqual(identity['company_logo'], 'aGVsbG8=')
        self.assertEqual(identity['companies_total'], 3)
        self.assertEqual(identity['user_name'], 'Audit User')

        usage = sections['usage']
        self.assertEqual(usage['custom_model_records'],
                         [{'model': 'x_studio_fleet', 'records': 12400}])
        self.assertEqual(usage['business_volumes']['res.partner'], 5200)

        self.assertEqual(sections['users_pulse'],
                         {'internal_users': 41, 'portal_users': 7,
                          'active_users_30d': 34})
        self.assertEqual(sections['storage'],
                         {'attachments': 3400, 'attachment_bytes': 1234567})
        self.assertEqual(sections['ops_flags']['crons_disabled'], 3)
        self.assertEqual(sections['ops_flags']['stuck_mails'], 12)

    def test_scope_controls_code_section_and_meta(self):
        studio = collect(FakeConnector(), INFO, scope='studio')
        self.assertEqual(studio['meta']['scan_scope'], 'studio')
        self.assertNotIn('code_customizations', studio['sections'])

        full = collect(FakeConnector(), INFO, scope='full')
        self.assertEqual(full['meta']['scan_scope'], 'full')
        code = full['sections']['code_customizations']
        self.assertEqual(code['modules'][0]['module'], 'acme_connector')
        self.assertEqual(code['modules'][0]['counts']['ir.model.fields'], 9)
        self.assertEqual(code['code_model_records'],
                         [{'model': 'acme.shipment', 'label': 'Shipment',
                           'records': 7300}])

    def test_identity_failure_does_not_sink_other_sections(self):
        sections = collect(FakeConnector(fail_models={'res.users'}), INFO)['sections']
        self.assertIn('error', sections['identity'])
        self.assertNotIn('error', sections['usage'])


class AnalyzerV3Tests(SimpleTestCase):
    def _usage_section(self, counts):
        return {'usage': {
            'custom_model_records': [{'model': m, 'records': n}
                                     for m, n in counts.items()],
            'skipped_models': 1, 'business_volumes': {'res.partner': 10}}}

    def test_usage_summary_tiers_and_bars(self):
        usage = summarize_usage(self._usage_section(
            {'x_big': 9000, 'x_small': 40, 'x_dead': 0}))
        tiers = {r['model']: r['tier'] for r in usage['rows']}
        self.assertEqual(tiers, {'x_big': 'critical', 'x_small': 'active',
                                 'x_dead': 'dead'})
        self.assertEqual(usage['rows'][0]['bar'], 100)
        self.assertEqual(usage['total_custom_records'], 9040)
        self.assertEqual(usage['dead_count'], 1)
        self.assertEqual(usage['dead_examples'], ['x_dead'])
        self.assertEqual(usage['skipped'], 1)

    def test_usage_findings_added_to_analysis(self):
        inventory = {'sections': self._usage_section({'x_big': 9000, 'x_dead': 0})}
        analysis = analyze(inventory)
        codes = {f['code'] for f in analysis['findings']}
        self.assertIn('business_critical_custom_models', codes)
        self.assertIn('dead_custom_models', codes)
        self.assertEqual(analysis['totals']['dead_custom_models'], 1)
        self.assertEqual(analysis['totals']['critical_custom_models'], 1)

    def test_old_inventory_is_backward_compatible(self):
        analysis = analyze({'sections': {}})
        self.assertIsNone(analysis['usage_summary'])
        self.assertIsNone(analysis['pulse'])
        self.assertIsNone(analysis['identity'])
        self.assertIsNone(analysis['code_summary'])
        self.assertNotIn('dead_custom_models', analysis['totals'])

    def test_identity_summary_builds_location(self):
        summary = summarize_identity({'identity': {
            'company_name': 'Acme', 'company_city': 'Madrid',
            'company_country': 'Spain', 'companies_total': 2,
            'user_name': 'U', 'user_login': 'u@x.com', 'company_logo': ''}})
        self.assertEqual(summary['company_location'], 'Madrid, Spain')
        self.assertEqual(summary['companies_total'], 2)

    def test_code_summary_flattens_counts(self):
        summary = summarize_code({'code_customizations': {
            'modules': [{'module': 'acme', 'origin': 'custom',
                         'counts': {'ir.model.fields': 9, 'ir.ui.view': 4},
                         'total': 13}],
            'code_model_records': [{'model': 'acme.shipment', 'label': 'S',
                                    'records': 7300}],
            'total_items': 13}})
        self.assertEqual(summary['modules'][0]['fields'], 9)
        self.assertEqual(summary['modules'][0]['views'], 4)
        self.assertEqual(summary['code_models'][0]['tier'], 'critical')
        self.assertEqual(summary['total_items'], 13)


class ScoringUsageTests(SimpleTestCase):
    def test_dead_models_discount_effort_but_not_score(self):
        totals = {'custom_models': 10, 'plain_studio_fields': 50}
        plain = compute_score(totals)
        discounted = compute_score(totals, usage={'dead_count': 6})
        self.assertEqual(discounted['score'], plain['score'])
        self.assertEqual(discounted['dead_models_discounted'], 6)
        self.assertLess(
            ('1–3 days', '4–8 days', '2–3 weeks', '4+ weeks').index(
                discounted['effort_estimate']),
            ('1–3 days', '4–8 days', '2–3 weeks', '4+ weeks').index(
                plain['effort_estimate']) + 1)

    def test_discount_never_exceeds_model_count(self):
        result = compute_score({'custom_models': 2}, usage={'dead_count': 99})
        self.assertEqual(result['dead_models_discounted'], 2)


@override_settings(ALLOWED_HOSTS=['testserver'])
class ReportV3RenderTests(TestCase):
    def _v3_run(self):
        run = make_done_run()
        result = dict(run.result_json)
        result['identity'] = {
            'company_name': 'Boss Continental', 'company_location': 'Madrid, Spain',
            'company_logo': '', 'companies_total': 3,
            'user_name': 'Audit User', 'user_login': 'audit@example.com'}
        result['pulse'] = {
            'internal_users': 41, 'portal_users': 7, 'active_users_30d': 34,
            'attachments': 3400, 'attachment_bytes': 1234567,
            'crons_disabled': 3, 'stuck_mails': 12,
            'business_volumes': [{'model': 'res.partner', 'records': 5200}]}
        result['usage'] = {
            'rows': [{'model': 'x_studio_fleet', 'records': 12400,
                      'tier': 'critical', 'bar': 100},
                     {'model': 'x_dead', 'records': 0, 'tier': 'dead', 'bar': 0}],
            'counted': 2, 'skipped': 0, 'total_custom_records': 12400,
            'critical_count': 1, 'active_count': 0,
            'dead_count': 1, 'dead_examples': ['x_dead']}
        result['code'] = {
            'modules': [{'module': 'acme_connector', 'origin': 'custom',
                         'models': 1, 'fields': 9, 'views': 4,
                         'server_actions': 2, 'automations': 1, 'crons': 0,
                         'reports': 0, 'total': 17}],
            'module_count': 1, 'total_items': 17,
            'code_models': [{'model': 'acme.shipment', 'label': 'Shipment',
                             'records': 7300, 'tier': 'critical'}],
            'code_model_count': 1}
        result['meta']['scan_scope'] = 'full'
        run.result_json = result
        run.save(update_fields=['result_json'])
        return run

    def test_v3_sections_render(self):
        run = self._v3_run()
        content = self.client.get(
            f'/en/tools/studio-xray/report/{run.pk}/').content.decode()
        self.assertIn('Boss Continental', content)            # identity strip
        self.assertIn('Prepared at the request of', content)
        self.assertIn('System pulse', content)
        self.assertIn('1.2 MB', content)                      # humanized storage
        self.assertIn('Where your custom data lives', content)
        self.assertIn('x_studio_fleet', content)
        self.assertIn('Critical', content)                    # tier label
        self.assertIn('Code customizations (Python modules)', content)
        self.assertIn('acme_connector', content)
        self.assertIn('Contacts', content)                    # volume label

    def test_old_report_without_v3_keys_still_renders(self):
        run = make_done_run()
        response = self.client.get(f'/en/tools/studio-xray/report/{run.pk}/')
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertNotIn('System pulse', content)
        self.assertNotIn('Code customizations', content)

    def test_form_passes_scope_to_task(self):
        with mock.patch('tool_studio_xray.views.run_studio_xray.delay') as delay:
            response = self.client.post('/en/tools/studio-xray/', {
                'odoo_url': 'https://x.odoo.com', 'database': 'x',
                'login': 'a@x.com', 'api_key': 'k',
                'scan_scope': 'full',
                'email': 'lead@example.com', 'consent': 'on',
            })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(delay.call_args[0][6], 'full')

    def test_invalid_scope_rejected_by_form(self):
        with mock.patch('tool_studio_xray.views.run_studio_xray.delay') as delay:
            response = self.client.post('/en/tools/studio-xray/', {
                'odoo_url': 'https://x.odoo.com', 'database': 'x',
                'login': 'a@x.com', 'api_key': 'k',
                'scan_scope': 'everything',
                'email': 'lead@example.com', 'consent': 'on',
            })
        self.assertEqual(response.status_code, 200)  # re-rendered with errors
        delay.assert_not_called()
