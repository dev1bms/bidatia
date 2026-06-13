import json
from unittest import mock

from django.core.cache import cache
from django.test import SimpleTestCase, TestCase, override_settings

from tools_core.connectors.base import ConnectorError
from tools_core.models import ToolEvent, ToolRun

from . import masking
from .analyzer import analyze
from .collector import collect
from .demo import build_collected, build_result_json, get_or_create_demo_run

READ_ONLY_METHODS = {'search_read', 'search_count', 'read_group',
                     'fields_get', 'test_connection'}


class MaskingTests(SimpleTestCase):
    def test_masks_never_leak_the_original(self):
        cases = [
            (masking.mask_email, 'alex@acme.com'),
            (masking.mask_text, 'Acme Trading SL'),
            (masking.mask_vat, 'ESB12345678'),
            (masking.mask_phone, '+34 681 096 066'),
            (masking.mask_code, 'SKU-998877'),
        ]
        for fn, raw in cases:
            with self.subTest(fn=fn.__name__):
                masked = fn(raw)
                self.assertIn('***', masked)
                self.assertNotEqual(masked, raw)
                # the bulk of the value must be gone
                self.assertLess(len(masked.replace('***', '')), len(raw) - 3)

    def test_mask_email_shape(self):
        self.assertEqual(masking.mask_email('alex@acme.com'), 'a***@a***.com')

    def test_empty_values_are_safe(self):
        for fn in (masking.mask_email, masking.mask_text, masking.mask_vat,
                   masking.mask_phone, masking.mask_code):
            fn('')  # must not raise
            fn(None)


class FakeConnector:
    """Read-only fake Odoo. Records every call so tests can assert the
    collector never strays outside the whitelisted read methods."""

    def __init__(self, models=None, counts=None, count_rules=None,
                 samples=None, groups=None, errors=None, xid_distinct=None,
                 sample_batches=None):
        self.models = models if models is not None else [
            'res.partner', 'product.template', 'product.product',
            'product.category', 'sale.order', 'sale.order.line',
            'purchase.order', 'crm.lead', 'account.move', 'account.tax',
            'account.fiscal.position', 'ir.attachment', 'ir.model.data',
            'res.users', 'res.currency', 'res.company', 'ir.model']
        self.counts = counts or {}
        self.count_rules = count_rules or []      # (model, substring, value)
        self.samples = samples or {}              # model -> rows
        self.groups = groups or []                # read_group rows
        self.errors = errors or set()             # models raising on count
        # {model: distinct res_id count} → count_distinct aggregate works;
        # None → the aggregate raises and the collector falls back.
        self.xid_distinct = xid_distinct
        # {model: [rows, rows, ...]} consumed one list per search_read call —
        # lets tests simulate the stratified oldest/newest/middle batches.
        self.sample_batches = sample_batches or {}
        self.calls = []

    def search_read(self, model, domain, fields, limit=None, order=None):
        self.calls.append(('search_read', model))
        if model == 'ir.model':
            if any(isinstance(c, (list, tuple)) and c[0] == 'model'
                   for c in domain):
                return [{'model': m} for m in self.models]
            return self.samples.get('ir.model', [])
        if self.sample_batches.get(model):
            return self.sample_batches[model].pop(0)
        return self.samples.get(model, [])

    def search_count(self, model, domain):
        self.calls.append(('search_count', model))
        if model in self.errors:
            raise ConnectorError('Access denied on this model.')
        text = str(domain)
        for rule_model, fragment, value in self.count_rules:
            if rule_model == model and fragment in text:
                return value
        return self.counts.get(model, 0)

    def read_group(self, model, domain, fields, groupby):
        self.calls.append(('read_group', model))
        if model == 'ir.model.data':
            if isinstance(self.xid_distinct, dict):
                text = str(domain)
                for target, value in self.xid_distinct.items():
                    if f"'{target}'" in text:
                        return [{'model': target, 'res_id': value}]
                return []
            raise ConnectorError('count_distinct unsupported on this version.')
        return self.groups


class CollectorTests(SimpleTestCase):
    def test_only_read_methods_are_used(self):
        connector = FakeConnector()
        collect(connector)
        used = {method for method, _model in connector.calls}
        self.assertTrue(used.issubset(READ_ONLY_METHODS), used)

    def test_missing_apps_mark_sections_skipped(self):
        connector = FakeConnector(models=['res.partner', 'ir.model.data',
                                          'res.users', 'ir.model'])
        collected = collect(connector)
        sections = collected['sections']
        self.assertTrue(sections['products'].get('skipped'))
        self.assertTrue(sections['accounting'].get('skipped'))
        self.assertTrue(sections['attachments'].get('skipped'))
        self.assertNotIn('error', sections['partners'])

    def test_permission_error_marks_section_error_not_failure(self):
        connector = FakeConnector(errors={'res.partner'})
        collected = collect(connector)
        self.assertIn('error', collected['sections']['partners'])
        # sections not touching the denied model still collect normally
        self.assertNotIn('error', collected['sections']['attachments'])
        self.assertNotIn('error', collected['sections']['custom_data'])

    def test_duplicates_detected_and_masked(self):
        sample = [
            {'name': 'Acme SL', 'email': 'INFO@acme.com', 'vat': 'ES111',
             'phone': '600111222', 'is_company': True},
            {'name': 'ACME, S.L.', 'email': 'info@acme.com ', 'vat': 'es-111',
             'phone': '+34 600 111 222', 'is_company': True},
            {'name': 'Other Co', 'email': 'x@other.com', 'vat': 'ES999',
             'phone': '', 'is_company': True},
        ]
        connector = FakeConnector(samples={'res.partner': sample})
        partners = collect(connector)['sections']['partners']
        self.assertEqual(partners['dup_email']['clusters'], 1)
        self.assertEqual(partners['dup_email']['affected'], 2)
        self.assertEqual(partners['dup_name']['clusters'], 1)  # legal-suffix normalization
        self.assertEqual(partners['dup_vat']['clusters'], 1)   # punctuation/case
        self.assertEqual(partners['dup_phone']['clusters'], 1)  # digit normalization
        # privacy: every stored example is masked, raw values absent
        payload = json.dumps(partners)
        self.assertNotIn('info@acme.com', payload)
        self.assertNotIn('ES111', payload)
        for example in partners['dup_email']['examples']:
            self.assertIn('***', example)
        self.assertEqual(partners['dup_phone']['examples'], [])

    def test_import_id_coverage(self):
        connector = FakeConnector(
            counts={'res.partner': 1000, 'product.template': 0,
                    'product.product': 0, 'product.category': 0,
                    'account.tax': 0},
            count_rules=[('ir.model.data', "'res.partner'", 100)])
        section = collect(connector)['sections']['import_ids']
        self.assertEqual(section['models']['res.partner']['coverage_pct'], 10)


class AnalyzerTests(SimpleTestCase):
    def test_demo_profile_scores_deterministically(self):
        first = analyze(build_collected())
        second = analyze(build_collected())
        self.assertEqual(first['score'], second['score'])
        self.assertEqual(first['level'], second['level'])
        self.assertGreaterEqual(first['score'], 1)
        self.assertLessEqual(first['score'], 100)
        self.assertEqual(len(first['categories']), 8)
        self.assertTrue(first['blockers'])
        self.assertLessEqual(len(first['blockers']), 5)

    def test_clean_database_scores_low(self):
        collected = build_collected()
        clean = {
            'partners': {'total_active': 100, 'archived': 0, 'companies': 40,
                         'sample_size': 100,
                         'dup_email': {'clusters': 0, 'affected': 0, 'examples': []},
                         'dup_vat': {'clusters': 0, 'affected': 0, 'examples': []},
                         'dup_name': {'clusters': 0, 'affected': 0, 'examples': []},
                         'dup_phone': {'clusters': 0, 'affected': 0, 'examples': []},
                         'missing_contact': 0, 'missing_country': 0,
                         'companies_missing_vat': 0, 'placeholder_names': 0},
            'products': {'total_templates': 50, 'total_variants': 50,
                         'archived_templates': 0, 'sample_size': 50,
                         'dup_default_code': {'clusters': 0, 'affected': 0, 'examples': []},
                         'dup_barcode': {'clusters': 0, 'affected': 0, 'examples': []},
                         'missing_default_code': 0, 'missing_barcode': 0,
                         'zero_priced': 0, 'categories': 10},
            'orphans': {'open_sales': 10, 'sales_archived_partner': 0,
                        'old_quotations': 0, 'so_lines_archived_product': 0,
                        'open_purchases': 5, 'purchases_archived_vendor': 0,
                        'open_leads': 5, 'leads_no_partner_no_email': 0},
            'import_ids': {'models': {'res.partner': {
                'records': 100, 'xids': 100, 'coverage_pct': 100}}},
            'attachments': {'total': 100, 'total_bytes': 1000, 'top_models': []},
            'accounting': {'old_draft_moves': 0, 'companies': 1,
                           'active_currencies': 1, 'fiscal_positions': 1},
            'ownership': {'inactive_users': 0, 'active_users': 5,
                          'sales_inactive_owner': 0, 'leads_inactive_owner': 0,
                          'partners_inactive_salesperson': 0},
            'custom_data': {'total_custom_models': 0, 'models': []},
        }
        result = analyze({'meta': collected['meta'], 'sections': clean})
        self.assertLess(result['score'], 40)
        self.assertEqual(result['level'], 'low')
        self.assertEqual(result['blockers'], [])

    def test_skipped_sections_excluded_from_score(self):
        collected = build_collected()
        collected['sections']['attachments'] = {'skipped': True}
        collected['sections']['custom_data'] = {'error': 'denied'}
        result = analyze(collected)
        by_code = {c['code']: c for c in result['categories']}
        self.assertEqual(by_code['attachments']['state'], 'skipped')
        self.assertIsNone(by_code['attachments']['score'])
        self.assertEqual(by_code['custom_data']['state'], 'error')
        self.assertIn('attachments', result['skipped_sections'])
        self.assertIn('custom_data', result['error_sections'])
        self.assertGreater(result['score'], 0)

    def test_import_id_score_capped_below_50(self):
        collected = build_collected()
        collected['sections']['import_ids'] = {'models': {
            'res.partner': {'records': 5000, 'xids': 0, 'coverage_pct': 0}}}
        result = analyze(collected)
        by_code = {c['code']: c for c in result['categories']}
        self.assertLessEqual(by_code['import_ids']['score'], 45)

    def test_stored_payload_contains_no_unmasked_examples(self):
        payload = json.dumps(build_result_json())
        # demo examples mirror real masking — every example carries ***
        self.assertNotIn('@meridian', payload)
        for fragment in ('i***@m***.com', 'ES***41', 'ME***12'):
            self.assertIn(fragment, payload)


@override_settings(ALLOWED_HOSTS=['testserver'])
class LandingViewTests(TestCase):
    URL = '/en/tools/data-risk-profiler/'
    DELAY = 'tool_data_risk.views.run_data_risk_scan.delay'

    VALID = {
        'odoo_url': 'https://mycompany.odoo.com', 'database': 'mycompany',
        'login': 'audit@mycompany.com', 'api_key': 'k' * 20,
        'email': '', 'full_name': '', 'company': '',
    }

    def setUp(self):
        cache.clear()

    def test_renders_in_all_languages_with_privacy_promise(self):
        for lang in ('en', 'es', 'ar'):
            response = self.client.get(f'/{lang}/tools/data-risk-profiler/')
            self.assertEqual(response.status_code, 200)
        response = self.client.get(self.URL)
        self.assertContains(response, 'signals and counts')
        self.assertTrue(ToolEvent.objects.filter(
            tool='data_risk', event='data_risk_page_view').exists())

    def test_form_validation_errors(self):
        response = self.client.post(self.URL, {})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'required', status_code=200)
        self.assertEqual(ToolRun.objects.count(), 0)

    def test_email_requires_consent(self):
        data = dict(self.VALID, email='me@company.com')
        with mock.patch(self.DELAY):
            response = self.client.post(self.URL, data)
        self.assertContains(response, 'Please accept')
        self.assertEqual(ToolRun.objects.count(), 0)

    def test_valid_submission_queues_scan_without_email(self):
        with mock.patch(self.DELAY) as delay:
            response = self.client.post(self.URL, dict(self.VALID))
        run = ToolRun.objects.get()
        self.assertEqual(response.status_code, 302)
        self.assertIn(str(run.pk), response['Location'])
        self.assertIsNone(run.lead)
        self.assertEqual(run.odoo_url, 'https://mycompany.odoo.com')
        delay.assert_called_once()
        # the api key travels as a task argument, never stored on the run
        self.assertNotIn('k' * 20, run.odoo_url + run.odoo_db)
        self.assertTrue(ToolEvent.objects.filter(
            event='data_risk_started').exists())

    def test_valid_submission_with_email_creates_lead(self):
        data = dict(self.VALID, email='me@company.com', consent='on')
        with mock.patch(self.DELAY):
            self.client.post(self.URL, data)
        run = ToolRun.objects.get()
        self.assertEqual(run.lead.email, 'me@company.com')

    def test_honeypot_redirects_silently(self):
        with mock.patch(self.DELAY) as delay:
            response = self.client.post(self.URL,
                                        dict(self.VALID, website='spam'))
        self.assertEqual(response.status_code, 302)
        delay.assert_not_called()

    def test_ip_rate_limit(self):
        with mock.patch(self.DELAY):
            for _ in range(5):
                self.client.post(self.URL, dict(self.VALID))
            response = self.client.post(self.URL, dict(self.VALID))
        self.assertContains(response, 'daily limit')
        self.assertEqual(ToolRun.objects.count(), 5)


@override_settings(ALLOWED_HOSTS=['testserver'])
class TaskTests(TestCase):
    CONNECTOR = 'tool_data_risk.tasks.OdooXmlRpcConnector'
    COLLECT = 'tool_data_risk.tasks.collect'

    def _run(self):
        return ToolRun.objects.create(tool_slug='data_risk',
                                      odoo_url='https://x.example.com',
                                      odoo_db='x')

    def test_successful_scan_stores_masked_risk_payload(self):
        from .tasks import run_data_risk_scan
        run = self._run()
        connector = mock.MagicMock()
        connector.test_connection.return_value = mock.MagicMock(
            server_version='17.0', edition='enterprise', db_name='x')
        with mock.patch(self.CONNECTOR, return_value=connector), \
                mock.patch(self.COLLECT, return_value=build_collected()):
            run_data_risk_scan(str(run.pk), 'https://x.example.com', 'x',
                               'login', 'secret-key')
        run.refresh_from_db()
        self.assertEqual(run.status, 'done')
        self.assertIn('risk', run.result_json)
        self.assertNotIn('secret-key', json.dumps(run.result_json))
        self.assertTrue(ToolEvent.objects.filter(
            event='data_risk_completed').exists())

    def test_connector_error_fails_politely(self):
        from .tasks import run_data_risk_scan
        run = self._run()
        with mock.patch(self.CONNECTOR,
                        side_effect=ConnectorError('Authentication failed — check the database name, login and API key.')):
            run_data_risk_scan(str(run.pk), 'https://x.example.com', 'x',
                               'login', 'bad-key')
        run.refresh_from_db()
        self.assertEqual(run.status, 'failed')
        self.assertIn('Authentication failed', run.error_message)
        self.assertNotIn('bad-key', run.error_message)
        self.assertTrue(ToolEvent.objects.filter(
            event='data_risk_failed').exists())

    def test_report_email_sent_when_lead_exists(self):
        from tools_core.services.lead_service import capture_lead

        from .tasks import run_data_risk_scan
        run = self._run()
        run.lead = capture_lead('me@company.com', source_tool='data_risk')
        run.save(update_fields=['lead'])
        connector = mock.MagicMock()
        connector.test_connection.return_value = mock.MagicMock(
            server_version='17.0', edition='', db_name='x')
        with mock.patch(self.CONNECTOR, return_value=connector), \
                mock.patch(self.COLLECT, return_value=build_collected()):
            run_data_risk_scan(str(run.pk), 'https://x.example.com', 'x',
                               'login', 'key')
        from core.models import EmailLog
        self.assertTrue(EmailLog.objects.filter(
            recipient_email='me@company.com', category='tool_report').exists())


@override_settings(ALLOWED_HOSTS=['testserver'])
class ReportViewTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_demo_report_renders_with_badge_and_tracks(self):
        response = self.client.get('/en/tools/data-risk-profiler/demo/',
                                   follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'DEMO')
        self.assertContains(response, 'Top migration blockers')
        self.assertContains(response, 'Cleanup plan')
        self.assertContains(response, '***')  # masked examples visible
        self.assertTrue(ToolEvent.objects.filter(
            event='data_risk_demo_opened').exists())
        # demo never logs a report_opened event
        self.assertFalse(ToolEvent.objects.filter(
            event='data_risk_report_opened').exists())

    def test_real_report_tracks_opened(self):
        run = ToolRun.objects.create(
            tool_slug='data_risk', status='done',
            odoo_url='https://x.example.com', odoo_db='x',
            result_json=_real_result())
        response = self.client.get(
            f'/en/tools/data-risk-profiler/report/{run.pk}/')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(ToolEvent.objects.filter(
            event='data_risk_report_opened').exists())

    def test_expired_report_shows_expiry_page(self):
        from datetime import timedelta

        from django.utils import timezone
        run = ToolRun.objects.create(
            tool_slug='data_risk', status='done',
            odoo_url='https://x.example.com', odoo_db='x',
            result_json=_real_result(),
            expires_at=timezone.now() - timedelta(hours=1))
        response = self.client.get(
            f'/en/tools/data-risk-profiler/report/{run.pk}/')
        self.assertContains(response, 'expired')

    def test_pending_run_redirects_to_progress(self):
        run = ToolRun.objects.create(tool_slug='data_risk',
                                     odoo_url='https://x.example.com',
                                     odoo_db='x')
        response = self.client.get(
            f'/en/tools/data-risk-profiler/report/{run.pk}/')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/run/', response['Location'])

    def test_status_endpoint_shape(self):
        run = ToolRun.objects.create(tool_slug='data_risk', status='collecting',
                                     odoo_url='https://x.example.com',
                                     odoo_db='x')
        data = self.client.get(
            f'/en/tools/data-risk-profiler/run/{run.pk}/status/').json()
        self.assertEqual(data['status'], 'collecting')
        self.assertEqual(data['step'], 1)

    def test_cta_redirects_track(self):
        response = self.client.get('/en/tools/data-risk-profiler/go/xray/')
        self.assertEqual(response['Location'], '/en/tools/studio-xray/')
        response = self.client.get('/en/tools/data-risk-profiler/go/rescue/')
        self.assertEqual(response['Location'], '/en/tools/erp-rescue/')
        events = set(ToolEvent.objects.filter(tool='data_risk')
                     .values_list('event', flat=True))
        self.assertIn('data_risk_xray_clicked', events)
        self.assertIn('data_risk_rescue_clicked', events)

    def test_booking_handoff_prefills_and_tracks(self):
        run = ToolRun.objects.create(
            tool_slug='data_risk', status='done',
            odoo_url='https://x.example.com', odoo_db='x',
            result_json=_real_result())
        response = self.client.get(
            f'/en/tools/data-risk-profiler/report/{run.pk}/book/')
        self.assertEqual(response.status_code, 302)
        prefill = self.client.session.get('booking_prefill') or {}
        self.assertIn('Data Risk Profiler', prefill.get('problem_summary', ''))
        self.assertTrue(ToolEvent.objects.filter(
            event='data_risk_booking_clicked').exists())

    def test_report_contains_no_raw_pii(self):
        response = self.client.get('/en/tools/data-risk-profiler/demo/',
                                   follow=True)
        content = response.content.decode()
        # nothing that looks like an unmasked email from the dataset
        self.assertNotIn('@meridian', content)

    def test_hub_card_links_to_tool(self):
        response = self.client.get('/en/tools/')
        self.assertContains(response, '/en/tools/data-risk-profiler/')
        self.assertContains(response, 'Data Risk Profiler')

    def test_sitemap_lists_landing(self):
        content = self.client.get('/sitemap.xml').content.decode()
        self.assertIn('/tools/data-risk-profiler/', content)


def _real_result():
    """A non-demo stored payload (demo flag stripped)."""
    result = build_result_json()
    result['meta'] = dict(result['meta'])
    result['meta'].pop('demo', None)
    return result


@override_settings(ALLOWED_HOSTS=['testserver'])
class DemoIdempotencyTests(TestCase):
    def test_demo_run_created_once(self):
        first = get_or_create_demo_run()
        second = get_or_create_demo_run()
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(ToolRun.objects.filter(tool_slug='data_risk').count(), 1)

    def test_stale_demo_payload_self_refreshes(self):
        run = get_or_create_demo_run()
        stale = dict(run.result_json)
        stale['meta'] = dict(stale['meta'], demo_version=1)
        del stale['risk']  # simulate an old-schema payload
        run.result_json = stale
        run.save(update_fields=['result_json'])
        refreshed = get_or_create_demo_run()
        self.assertEqual(refreshed.pk, run.pk)
        self.assertIn('risk', refreshed.result_json)
        from .demo import DEMO_VERSION
        self.assertEqual(refreshed.result_json['meta']['demo_version'],
                         DEMO_VERSION)


# ── v1.1 ──────────────────────────────────────────────────────────────────────

def _low_risk_result():
    result = _real_result()
    result['risk'] = dict(result['risk'], score=12, level='low')
    return result


@override_settings(ALLOWED_HOSTS=['testserver'])
class SendToManagerTests(TestCase):
    def setUp(self):
        cache.clear()
        self.run = ToolRun.objects.create(
            tool_slug='data_risk', status='done',
            odoo_url='https://x.example.com', odoo_db='x',
            result_json=_real_result())
        self.url = f'/en/tools/data-risk-profiler/report/{self.run.pk}/share/'

    def _post(self, payload):
        return self.client.post(self.url, json.dumps(payload),
                                content_type='application/json')

    def test_report_page_renders_share_form(self):
        response = self.client.get(
            f'/en/tools/data-risk-profiler/report/{self.run.pk}/')
        self.assertContains(response, 'Send this report to my manager')
        self.assertContains(response, '/share/')

    def test_valid_email_sends_and_logs(self):
        response = self._post({'email': 'boss@acme.com'})
        self.assertEqual(response.json(), {'ok': True})
        from core.models import EmailLog
        log = EmailLog.objects.get(category='report_to_manager')
        self.assertEqual(log.recipient_email, 'boss@acme.com')
        self.assertIn('Data risk score', log.text_body)
        # masked examples never travel in the manager email
        self.assertNotIn('***@', log.text_body)
        self.assertTrue(ToolEvent.objects.filter(
            event='data_risk_report_sent_to_manager').exists())

    def test_invalid_email_fails_politely(self):
        self.assertEqual(self._post({'email': 'nope'}).status_code, 400)
        self.assertEqual(self._post({}).status_code, 400)

    def test_get_not_allowed_and_demo_blocked(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)
        demo = get_or_create_demo_run()
        response = self.client.post(
            f'/en/tools/data-risk-profiler/report/{demo.pk}/share/',
            json.dumps({'email': 'boss@acme.com'}),
            content_type='application/json')
        self.assertEqual(response.status_code, 409)

    def test_rate_limited_per_run(self):
        for _ in range(3):
            self.assertEqual(self._post({'email': 'boss@acme.com'}).status_code, 200)
        self.assertEqual(self._post({'email': 'boss@acme.com'}).status_code, 429)


@override_settings(ALLOWED_HOSTS=['testserver'])
class DataRiskBadgeTests(TestCase):
    def setUp(self):
        cache.clear()

    def _run(self, result):
        return ToolRun.objects.create(
            tool_slug='data_risk', status='done',
            odoo_url='https://x.example.com', odoo_db='x', result_json=result)

    def test_low_risk_is_eligible(self):
        from tools_core.services.badges import badge_eligibility
        self.assertEqual(badge_eligibility(self._run(_low_risk_result())),
                         'low_data_risk')

    def test_other_bands_are_not_eligible(self):
        from tools_core.services.badges import badge_eligibility
        for level in ('moderate', 'high', 'critical'):
            result = _real_result()
            result['risk'] = dict(result['risk'], level=level)
            self.assertIsNone(badge_eligibility(self._run(result)), level)

    def test_offer_appears_on_low_risk_report_only(self):
        low = self._run(_low_risk_result())
        response = self.client.get(
            f'/en/tools/data-risk-profiler/report/{low.pk}/')
        self.assertContains(response, 'Health Snapshot badge')
        self.assertTrue(ToolEvent.objects.filter(
            tool='health_badge', event='healthy_badge_offered').exists())
        risky = self._run(_real_result())  # demo profile is 'moderate'
        response = self.client.get(
            f'/en/tools/data-risk-profiler/report/{risky.pk}/')
        self.assertNotContains(response, 'Health Snapshot badge')

    def test_badge_page_shows_safe_wording_only(self):
        from tools_core.services.badges import get_or_create_badge
        run = self._run(_low_risk_result())
        badge, created = get_or_create_badge(run, 'Acme S.L.')
        self.assertTrue(created)
        self.assertEqual(badge.level_code, 'low_data_risk')
        response = self.client.get(f'/en/tools/badge/{badge.pk}/')
        self.assertContains(response, 'Low data migration risk')
        self.assertContains(response, 'Data Risk Profiler')
        self.assertContains(response, 'not a security certification')
        content = response.content.decode()
        for forbidden in ('certified', 'guaranteed', 'official audit'):
            self.assertNotIn(forbidden, content.lower())
        # nothing from the report leaks
        self.assertNotIn('blocker', content.lower())


# ── v2 foundation ─────────────────────────────────────────────────────────────

class StratifiedSamplingTests(SimpleTestCase):
    def test_small_dataset_is_full_coverage(self):
        connector = FakeConnector(
            count_rules=[('res.partner', "'active', '=', True", 50)],
            samples={'res.partner': [
                {'id': i, 'name': f'P{i}', 'email': '', 'vat': '',
                 'phone': '', 'is_company': False} for i in range(50)]})
        partners = collect(connector)['sections']['partners']
        self.assertTrue(partners['sample_full'])
        self.assertEqual(partners['sample_coverage_pct'], 100)

    def test_large_dataset_samples_three_ranges(self):
        def rows(start, n):
            return [{'id': i, 'name': f'P{i}', 'email': '', 'vat': '',
                     'phone': '', 'is_company': False}
                    for i in range(start, start + n)]

        connector = FakeConnector(
            count_rules=[('res.partner', "'active', '=', True", 9000)],
            sample_batches={'res.partner': [
                rows(1, 666),       # oldest segment
                rows(8000, 666),    # newest segment
                rows(4000, 668),    # middle band
            ]})
        partners = collect(connector)['sections']['partners']
        self.assertFalse(partners['sample_full'])
        self.assertEqual(partners['sample_size'], 2000)
        self.assertEqual(partners['sample_coverage_pct'], 22)  # 2000/9000
        # all three id ranges represented
        reads = [c for c in connector.calls
                 if c == ('search_read', 'res.partner')]
        self.assertEqual(len(reads), 3)

    def test_duplicates_remain_deterministic_across_segments(self):
        batch = [{'id': 1, 'name': 'Acme', 'email': 'a@a.com', 'vat': '',
                  'phone': '', 'is_company': False},
                 {'id': 2, 'name': 'Acme', 'email': 'a@a.com', 'vat': '',
                  'phone': '', 'is_company': False}]
        connector = FakeConnector(
            count_rules=[('res.partner', "'active', '=', True", 9000)],
            sample_batches={'res.partner': [batch, [], []]})
        partners = collect(connector)['sections']['partners']
        self.assertEqual(partners['dup_email']['clusters'], 1)
        self.assertEqual(partners['dup_email']['affected'], 2)


class CleanupActionListTests(SimpleTestCase):
    def test_actions_built_sorted_and_translated_shape(self):
        from .views import _cleanup_plan
        risk = analyze(build_collected())
        plan = _cleanup_plan(risk)
        before = plan['before']
        self.assertTrue(before)
        # sorted high → low (generic consultant line appended last)
        ranks = {'high': 0, 'medium': 1, 'low': 2}
        priorities = [ranks[a['priority']] for a in before[:-1]]
        self.assertEqual(priorities, sorted(priorities))
        for action in before:
            self.assertIn('title', action)
            self.assertIn('owner_label', action)
            self.assertIn('priority_label', action)
        # no raw PII anywhere in the actions
        self.assertNotIn('@meridian', json.dumps(
            [str(a) for stage in plan.values() for a in stage]))

    def test_actions_render_in_report(self):
        run = ToolRun.objects.create  # noqa: F841 — view test below covers it


@override_settings(ALLOWED_HOSTS=['testserver'])
class ActionListRenderTests(TestCase):
    def test_report_shows_priority_and_owner_chips(self):
        response = self.client.get('/en/tools/data-risk-profiler/demo/',
                                   follow=True)
        self.assertContains(response, 'Cleanup plan')
        self.assertContains(response, 'Odoo consultant')
        self.assertContains(response, 'Accounting team')
        # stratified-coverage note shows the demo percentages
        self.assertContains(response, '11%')


class AiAdvisorTests(TestCase):
    def test_payload_is_sanitized(self):
        from .insights import build_payload
        risk = analyze(build_collected())
        payload = json.dumps(build_payload(risk, {'server_version': '16.0'},
                                           'en'))
        self.assertNotIn('@meridian', payload)
        self.assertNotIn('api_key', payload)
        self.assertNotIn('login', payload)
        # masked examples may appear — only masked
        self.assertIn('***', payload)

    def test_validation_rejects_garbage_and_caps_lengths(self):
        from .insights import _validated
        self.assertIsNone(_validated('not json at all'))
        self.assertIsNone(_validated('{"board_summary": ""}'))
        valid = _validated(json.dumps({
            'board_summary': 'word ' * 500,
            'cleanup_priorities': ['a' * 500] * 9,
            'management_questions': ['q1', 'q2', 'q3', 'q4'],
            'migration_risks_plain_language': 'risk',
        }))
        self.assertLessEqual(len(valid['board_summary']), 900)
        self.assertLessEqual(len(valid['cleanup_priorities']), 4)
        self.assertLessEqual(len(valid['management_questions']), 3)
        self.assertLessEqual(len(valid['cleanup_priorities'][0]), 220)

    @override_settings(TOOLS_AI_MODEL='test-model')
    def test_task_stores_advisor_and_tracks_completed(self):
        from .tasks import run_data_risk_scan
        run = ToolRun.objects.create(tool_slug='data_risk',
                                     odoo_url='https://x.example.com',
                                     odoo_db='x')
        connector = mock.MagicMock()
        connector.test_connection.return_value = mock.MagicMock(
            server_version='17.0', edition='', db_name='x')
        advice = {'board_summary': 'Summary.', 'cleanup_priorities': ['Do X'],
                  'management_questions': [], 'migration_risks_plain_language': '',
                  'language': 'en'}
        with mock.patch('tool_data_risk.tasks.OdooXmlRpcConnector',
                        return_value=connector), \
                mock.patch('tool_data_risk.tasks.collect',
                           return_value=build_collected()), \
                mock.patch('tool_data_risk.insights.generate_advice',
                           return_value=advice) as gen:
            run_data_risk_scan(str(run.pk), 'https://x.example.com', 'x',
                               'login', 'key')
        run.refresh_from_db()
        self.assertEqual(run.result_json['advisor']['board_summary'], 'Summary.')
        gen.assert_called_once()
        self.assertTrue(ToolEvent.objects.filter(
            event='data_risk_ai_advisor_completed').exists())
        # the deterministic score is untouched by the advisor
        self.assertEqual(run.result_json['risk']['score'],
                         analyze(build_collected())['score'])

    @override_settings(TOOLS_AI_MODEL='test-model')
    def test_ai_failure_never_breaks_the_report(self):
        from .tasks import run_data_risk_scan
        run = ToolRun.objects.create(tool_slug='data_risk',
                                     odoo_url='https://x.example.com',
                                     odoo_db='x')
        connector = mock.MagicMock()
        connector.test_connection.return_value = mock.MagicMock(
            server_version='17.0', edition='', db_name='x')
        with mock.patch('tool_data_risk.tasks.OdooXmlRpcConnector',
                        return_value=connector), \
                mock.patch('tool_data_risk.tasks.collect',
                           return_value=build_collected()), \
                mock.patch('tool_data_risk.insights.generate_advice',
                           side_effect=RuntimeError('model down')):
            run_data_risk_scan(str(run.pk), 'https://x.example.com', 'x',
                               'login', 'key')
        run.refresh_from_db()
        self.assertEqual(run.status, 'done')
        self.assertIsNone(run.result_json['advisor'])
        self.assertTrue(ToolEvent.objects.filter(
            event='data_risk_ai_advisor_failed').exists())

    def test_report_renders_with_and_without_advisor(self):
        base = _real_result()
        with_ai = dict(base, advisor={
            'board_summary': 'AI says hello.', 'cleanup_priorities': ['Do X'],
            'management_questions': ['Who owns data?'],
            'migration_risks_plain_language': 'Risks.'})
        for payload, marker, present in ((with_ai, 'AI advisor notes', True),
                                         (base, 'AI advisor notes', False)):
            run = ToolRun.objects.create(
                tool_slug='data_risk', status='done',
                odoo_url='https://x.example.com', odoo_db='x',
                result_json=payload)
            response = self.client.get(
                f'/en/tools/data-risk-profiler/report/{run.pk}/')
            if present:
                self.assertContains(response, marker)
            else:
                self.assertNotContains(response, marker)


@override_settings(ALLOWED_HOSTS=['testserver'])
class SnapshotDeltaTests(TestCase):
    def _scan(self, save_snapshot, url='https://x.example.com', db='x'):
        from .tasks import run_data_risk_scan
        run = ToolRun.objects.create(tool_slug='data_risk',
                                     odoo_url=url, odoo_db=db)
        connector = mock.MagicMock()
        connector.test_connection.return_value = mock.MagicMock(
            server_version='17.0', edition='', db_name=db)
        with mock.patch('tool_data_risk.tasks.OdooXmlRpcConnector',
                        return_value=connector), \
                mock.patch('tool_data_risk.tasks.collect',
                           return_value=build_collected()):
            run_data_risk_scan(str(run.pk), url, db, 'login', 'key',
                               'en', save_snapshot)
        run.refresh_from_db()
        return run

    def test_no_snapshot_without_opt_in(self):
        from .models import DataRiskSnapshot
        run = self._scan(save_snapshot=False)
        self.assertEqual(DataRiskSnapshot.objects.count(), 0)
        self.assertIsNone(run.result_json['delta'])

    def test_snapshot_stores_aggregates_only(self):
        from .models import DataRiskSnapshot
        self._scan(save_snapshot=True)
        snapshot = DataRiskSnapshot.objects.get()
        payload = json.dumps({'scores': snapshot.category_scores,
                              'counts': snapshot.key_counts,
                              'level': snapshot.level})
        self.assertNotIn('@', payload)
        self.assertNotIn('***', payload)   # not even masked examples
        self.assertIn('duplicates', snapshot.category_scores)
        self.assertEqual(snapshot.key_counts['partners'], 18420)
        self.assertEqual(len(snapshot.fingerprint), 32)

    def test_second_scan_shows_delta(self):
        self._scan(save_snapshot=True)
        second = self._scan(save_snapshot=False)
        delta = second.result_json['delta']
        self.assertIsNotNone(delta)
        self.assertEqual(delta['prev_score'],
                         second.result_json['risk']['score'])
        response = self.client.get(
            f'/en/tools/data-risk-profiler/report/{second.pk}/')
        self.assertContains(response, 'Progress since your last scan')
        self.assertContains(response, 'No significant change')

    def test_different_database_gets_no_delta(self):
        self._scan(save_snapshot=True)
        other = self._scan(save_snapshot=False,
                           url='https://other.example.com', db='other')
        self.assertIsNone(other.result_json['delta'])

    def test_wipe_lifecycle_untouched_by_snapshots(self):
        from datetime import timedelta

        from django.utils import timezone

        from tools_core.tasks import wipe_expired_tool_results

        from .models import DataRiskSnapshot
        run = self._scan(save_snapshot=True)
        ToolRun.objects.filter(pk=run.pk).update(
            expires_at=timezone.now() - timedelta(hours=1))
        wipe_expired_tool_results()
        run.refresh_from_db()
        self.assertIsNone(run.result_json)
        self.assertEqual(DataRiskSnapshot.objects.count(), 1)  # survives

    def test_opt_in_copy_renders_on_landing(self):
        response = self.client.get('/en/tools/data-risk-profiler/')
        self.assertContains(response, 'anonymous aggregated snapshot')


@override_settings(ALLOWED_HOSTS=['testserver'])
class QualityMapTests(TestCase):
    def test_map_builds_from_demo_and_renders(self):
        response = self.client.get('/en/tools/data-risk-profiler/demo/',
                                   follow=True)
        self.assertContains(response, 'Your Data Quality Map')
        self.assertContains(response, '<svg')
        self.assertContains(response, 'polygon')
        self.assertTrue(ToolEvent.objects.filter(
            event='data_risk_quality_map_viewed').exists())

    def test_too_few_categories_hides_map(self):
        from .quality_map import build_quality_map
        risk = {'categories': [
            {'code': 'duplicates', 'score': 10, 'severity': 'ok'},
            {'code': 'orphans', 'score': None, 'severity': 'ok'}],
            'score': 10, 'level': 'low'}
        self.assertIsNone(build_quality_map(risk, {}))

    def test_coordinates_survive_decimal_comma_locales(self):
        import xml.etree.ElementTree as ET

        from django.template.loader import render_to_string
        from django.utils import translation

        from .quality_map import build_quality_map
        from .views import CATEGORY_SHORT
        risk = analyze(build_collected())
        for lang in ('en', 'es', 'ar'):
            with self.subTest(lang=lang), translation.override(lang):
                qmap = build_quality_map(
                    risk, {c: str(l) for c, l in CATEGORY_SHORT.items()})
                svg = render_to_string('tool_data_risk/_quality_map.html',
                                       {'qmap': qmap})
                root = ET.fromstring(svg)
                checked = 0
                for element in root.iter():
                    for attr in ('cx', 'cy', 'r', 'x', 'y', 'x1', 'y1',
                                 'x2', 'y2', 'width', 'height'):
                        value = element.get(attr)
                        if value is not None:
                            float(value)
                            checked += 1
                    if element.tag.endswith('polygon'):
                        for pair in element.get('points', '').split():
                            for token in pair.split(','):
                                float(token)
                                checked += 1
                self.assertGreater(checked, 40)


class DistinctXidCoverageTests(SimpleTestCase):
    def test_distinct_res_id_counts_once(self):
        connector = FakeConnector(
            counts={'res.partner': 100, 'product.template': 0,
                    'product.product': 0, 'product.category': 0,
                    'account.tax': 0},
            # 80 ir.model.data ROWS would say 80% — distinct says 40 records
            count_rules=[('ir.model.data', "'res.partner'", 80)],
            xid_distinct={'res.partner': 40})
        section = collect(connector)['sections']['import_ids']
        row = section['models']['res.partner']
        self.assertEqual(row['xids'], 40)
        self.assertEqual(row['coverage_pct'], 40)
        self.assertFalse(row['approximate'])

    def test_fallback_to_row_count_marked_approximate(self):
        connector = FakeConnector(
            counts={'res.partner': 100, 'product.template': 0,
                    'product.product': 0, 'product.category': 0,
                    'account.tax': 0},
            count_rules=[('ir.model.data', "'res.partner'", 80)],
            xid_distinct=None)  # aggregate unsupported
        row = collect(connector)['sections']['import_ids']['models']['res.partner']
        self.assertEqual(row['xids'], 80)
        self.assertTrue(row['approximate'])
