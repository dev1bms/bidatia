from django.test import SimpleTestCase

from tool_studio_xray.collector import SCHEMA_VERSION, collect
from tools_core.connectors.base import ConnectionInfo, ConnectorError


class FakeConnector:
    """Implements the read-only connector interface with canned data.
    Having ONLY read methods also proves the collector never needs writes."""

    def __init__(self, fail_models=()):
        self.fail_models = set(fail_models)
        self.calls = []
        self._uid = 2  # the collector reads the connected user for identity

    def _maybe_fail(self, model):
        if model in self.fail_models:
            raise ConnectorError('Database name not found or access denied.')

    def search_read(self, model, domain, fields, limit=None, order=None):
        self.calls.append(('search_read', model))
        self._maybe_fail(model)
        assert limit is not None, 'collector must always pass a limit'
        if model == 'ir.model.fields':
            return [
                {'name': 'x_studio_margin', 'model': 'sale.order',
                 'field_description': 'Margin', 'ttype': 'float', 'relation': False,
                 'required': False, 'store': True, 'related': False,
                 'compute': 'for rec in self:\n    rec.x_studio_margin = ' + 'x' * 200},
                {'name': 'x_studio_ref', 'model': 'res.partner',
                 'field_description': 'Ref', 'ttype': 'char', 'relation': False,
                 'required': True, 'store': True, 'related': False, 'compute': False},
            ]
        if model == 'ir.model':
            if any(c[0] == 'id' for c in domain if isinstance(c, (list, tuple))):
                return [{'model': 'acme.shipment', 'name': 'Shipment'}]
            return [{'model': 'x_studio_fleet', 'name': 'Fleet'}]
        if model == 'res.users':
            return [{'id': 2, 'name': 'Audit User', 'login': 'audit@example.com',
                     'company_id': [1, 'Boss Continental']}]
        if model == 'res.company':
            if 'logo_web' in fields:
                return [{'id': 1, 'logo_web': 'aGVsbG8='}]
            return [{'id': 1, 'name': 'Boss Continental', 'street': 'Calle 1',
                     'city': 'Madrid', 'country_id': [68, 'Spain']}]
        if model == 'ir.ui.view':
            return [{'name': 'Odoo Studio: sale form', 'model': 'sale.order',
                     'type': 'form', 'inherit_id': [42, 'sale.order.form'],
                     'key': 'studio_customization.sale_form'}]
        if model == 'base.automation':
            return [{'id': 31, 'name': 'Notify on create', 'model_id': [5, 'Sales Order'],
                     'trigger': 'on_create', 'active': True, 'model_name': 'sale.order'}]
        if model == 'ir.actions.server':
            return [{'id': 71, 'name': 'Recompute totals', 'model_id': [5, 'Sales Order'],
                     'state': 'code', 'usage': 'ir_actions_server'},
                    {'id': 72, 'name': 'Send an email', 'model_id': [5, 'Sales Order'],
                     'state': 'code', 'usage': 'ir_actions_server'}]
        if model == 'ir.model.data':
            if ('model', '=', 'ir.model') in [tuple(c) for c in domain
                                              if isinstance(c, (list, tuple))]:
                return [{'res_id': 99}]
            # id 72 ships with a module; 71 and 31 are hand-made
            return [{'res_id': 72, 'module': 'account'}]
        if model == 'ir.actions.act_window':
            return [{'id': 9, 'name': 'Fleet'}]
        if model == 'ir.ui.menu':
            return [{'name': 'Fleet'}]
        if model == 'ir.module.module':
            return [
                {'name': 'sale', 'shortdesc': 'Sales', 'author': 'Odoo S.A.'},
                {'name': 'partner_firstname', 'shortdesc': 'Partner first name',
                 'author': 'Camptocamp, Odoo Community Association (OCA)'},
                {'name': 'acme_connector', 'shortdesc': 'Acme Connector', 'author': 'Acme Corp'},
                {'name': 'x_internal_tweaks', 'shortdesc': 'Internal Tweaks', 'author': False},
            ]
        raise AssertionError('unexpected model %s' % model)

    def search_count(self, model, domain):
        self.calls.append(('search_count', model))
        self._maybe_fail(model)
        if model == 'ir.model.fields':
            return 2500  # more than returned items -> truncated
        if model == 'ir.ui.view':
            return 1
        if model == 'ir.module.module':
            return 87 if len(domain) == 1 else 1  # installed total vs web_studio
        if model == 'res.company':
            return 3
        if model == 'res.users':
            if ('share', '=', True) in [tuple(c) for c in domain]:
                return 7
            if any(c[0] == 'login_date' for c in domain if isinstance(c, (list, tuple))):
                return 34
            return 41
        if model == 'x_studio_fleet':
            return 12400
        if model == 'acme.shipment':
            return 7300
        if model == 'res.partner':
            return 5200
        if model == 'ir.cron':
            return 3 if ('active', '=', False) in [tuple(c) for c in domain] else 14
        if model == 'mail.mail':
            return 12
        return 0

    def read_group(self, model, domain, fields, groupby):
        self.calls.append(('read_group', model))
        self._maybe_fail(model)
        if model == 'ir.attachment':
            return [{'__count': 3400, 'file_size': 1234567}]
        if model == 'ir.model.data':
            tracked = next((c[2] for c in domain
                            if isinstance(c, (list, tuple)) and c[0] == 'model'), None)
            rows = {'ir.model': [{'module': 'x_internal_tweaks', '__count': 1}],
                    'ir.model.fields': [{'module': 'acme_connector', '__count': 9}],
                    'ir.ui.view': [{'module': 'acme_connector', '__count': 4}]}
            return rows.get(tracked, [])
        return [{'model': 'x_studio_fleet', '__count': 12}]

    def fields_get(self, model, attributes=None):
        return {}


INFO = ConnectionInfo(server_version='17.0', edition='enterprise',
                      user_name='Audit', db_name='example')


class CollectorTests(SimpleTestCase):
    def test_normalized_output_shape_and_meta(self):
        result = collect(FakeConnector(), INFO)
        self.assertEqual(result['meta']['schema_version'], SCHEMA_VERSION)
        self.assertEqual(result['meta']['tool'], 'studio_xray')
        self.assertEqual(result['meta']['server_version'], '17.0')
        self.assertEqual(result['meta']['edition'], 'enterprise')
        self.assertEqual(
            set(result['sections']),
            {'studio_fields', 'custom_models', 'studio_views', 'automated_actions',
             'server_actions', 'studio_menus', 'module_context', 'installed_modules',
             'identity', 'usage', 'users_pulse', 'storage', 'ops_flags'})

    def test_field_normalization_compute_preview_truncated(self):
        fields = collect(FakeConnector(), INFO)['sections']['studio_fields']
        margin = fields['items'][0]
        self.assertTrue(margin['has_compute'])
        self.assertLessEqual(len(margin['compute_preview']), 80)
        self.assertEqual(margin['label'], 'Margin')
        ref = fields['items'][1]
        self.assertFalse(ref['has_compute'])
        self.assertEqual(ref['compute_preview'], '')
        # search_count said 2500 > 2 items returned
        self.assertEqual(fields['total'], 2500)
        self.assertTrue(fields['truncated'])

    def test_view_and_m2o_normalization(self):
        sections = collect(FakeConnector(), INFO)['sections']
        view = sections['studio_views']['items'][0]
        self.assertTrue(view['inherits'])
        self.assertEqual(view['inherit_of'], 'sale.order.form')
        auto = sections['automated_actions']['items'][0]
        self.assertEqual(auto['model'], 'sale.order')
        self.assertEqual(auto['model_label'], 'Sales Order')

    def test_custom_models_field_counts_via_read_group(self):
        models = collect(FakeConnector(), INFO)['sections']['custom_models']
        self.assertEqual(models['items'][0]['field_count'], 12)

    def test_menus_resolved_through_custom_model_actions(self):
        menus = collect(FakeConnector(), INFO)['sections']['studio_menus']
        self.assertEqual(menus['total'], 1)
        self.assertEqual(menus['items'][0]['name'], 'Fleet')

    def test_module_context(self):
        ctx = collect(FakeConnector(), INFO)['sections']['module_context']
        self.assertEqual(ctx['installed_modules'], 87)
        self.assertTrue(ctx['studio_installed'])

    def test_server_action_module_provenance(self):
        actions = collect(FakeConnector(), INFO)['sections']['server_actions']['items']
        by_name = {a['name']: a for a in actions}
        self.assertFalse(by_name['Recompute totals']['from_module'])  # hand-made
        self.assertTrue(by_name['Send an email']['from_module'])      # shipped
        autos = collect(FakeConnector(), INFO)['sections']['automated_actions']['items']
        self.assertFalse(autos[0]['from_module'])

    def test_provenance_lookup_failure_keeps_previous_behavior(self):
        connector = FakeConnector(fail_models={'ir.model.data'})
        actions = collect(connector, INFO)['sections']['server_actions']['items']
        # lookup unavailable -> nothing marked as shipped (same as before v2.1)
        self.assertTrue(all(not a['from_module'] for a in actions))

    def test_installed_modules_normalization(self):
        modules = collect(FakeConnector(), INFO)['sections']['installed_modules']
        self.assertEqual(modules['total'], 4)
        sale = modules['items'][0]
        self.assertEqual(sale, {'name': 'sale', 'display_name': 'Sales', 'author': 'Odoo S.A.'})
        # missing author (False over XML-RPC) normalizes to empty string
        self.assertEqual(modules['items'][3]['author'], '')

    def test_failing_section_records_error_and_collection_continues(self):
        connector = FakeConnector(fail_models={'base.automation'})
        sections = collect(connector, INFO)['sections']
        self.assertIn('error', sections['automated_actions'])
        # error text is the sanitized connector message, and other sections survive
        self.assertNotIn('items', sections['automated_actions'])
        self.assertEqual(sections['studio_views']['total'], 1)
        self.assertEqual(sections['module_context']['installed_modules'], 87)

    def test_no_connection_info_still_collects(self):
        result = collect(FakeConnector(), None)
        self.assertEqual(result['meta']['server_version'], '')
        self.assertIn('studio_fields', result['sections'])
