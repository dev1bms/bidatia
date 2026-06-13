"""The public demo report: a rich, FICTIONAL company scan for the landing
page's "view a demo report" link. Built through the real analyzer/scoring
pipeline so it always matches what the report template expects.

The demo run: no lead, no email, never expires, flagged meta.demo=True
(the report view shows a DEMO badge, disables chat and logs its own event).
"""
import uuid
from datetime import timedelta

from django.utils import timezone

from .analyzer import analyze
from .scoring import compute_score

# Deterministic id — the demo view get-or-creates exactly one run.
DEMO_RUN_ID = uuid.uuid5(uuid.NAMESPACE_URL, 'https://bidatia.xyz/tools/studio-xray/demo')

_FIELD = {'label': '', 'relation': '', 'required': False, 'store': True,
          'related': '', 'has_compute': False, 'compute_preview': ''}


def _fields():
    rows = []
    for model, name, computed in [
        ('sale.order', 'x_studio_margin_pct', True),
        ('sale.order', 'x_studio_incoterm_note', False),
        ('sale.order.line', 'x_studio_origin_port', False),
        ('res.partner', 'x_studio_credit_rating', True),
        ('res.partner', 'x_studio_customs_id', False),
        ('account.move', 'x_studio_clearance_ref', False),
        ('stock.picking', 'x_studio_vessel_name', False),
        ('stock.picking', 'x_studio_eta_port', False),
        ('product.template', 'x_studio_hs_code', False),
        ('x_air_waybill', 'x_studio_awb_number', False),
        ('x_air_waybill', 'x_studio_chargeable_weight', True),
        ('x_fleet_trip', 'x_studio_route_code', False),
    ]:
        rows.append({**_FIELD, 'name': name, 'model': model,
                     'ttype': 'float' if computed else 'char',
                     'has_compute': computed})
    return rows


def build_inventory():
    return {
        'meta': {'schema_version': 1, 'tool': 'studio_xray',
                 'collected_at': timezone.now().isoformat(timespec='seconds'),
                 'server_version': '16.0', 'edition': 'enterprise',
                 'db_name': 'aurora-trading', 'scan_scope': 'full'},
        'sections': {
            'studio_fields': {'items': _fields(), 'total': 87, 'truncated': True},
            'custom_models': {'items': [
                {'model': 'x_air_waybill', 'name': 'Air Waybill', 'field_count': 23},
                {'model': 'x_fleet_trip', 'name': 'Fleet Trip', 'field_count': 17},
                {'model': 'x_customs_doc', 'name': 'Customs Document', 'field_count': 12},
                {'model': 'x_test_model', 'name': 'Test Model', 'field_count': 4},
                {'model': 'x_old_import', 'name': 'Old Import', 'field_count': 6},
            ], 'total': 5},
            'studio_views': {'items': [
                {'name': 'Odoo Studio: sale form', 'model': 'sale.order',
                 'type': 'form', 'inherits': True, 'inherit_of': 'sale.order.form',
                 'key': 'studio_customization.sale_form'}] * 9,
                'total': 9, 'truncated': False},
            'automated_actions': {'items': [
                {'name': 'Notify ops on urgent shipment', 'model': 'x_air_waybill',
                 'model_label': 'Air Waybill', 'trigger': 'on_create',
                 'active': True, 'from_module': False}] * 6, 'total': 6},
            'server_actions': {'items': [
                {'name': 'Recompute chargeable weight', 'model_label': 'Air Waybill',
                 'state': 'code', 'usage': 'ir_actions_server',
                 'from_module': False}] * 4, 'total': 4},
            'studio_menus': {'items': [{'name': 'Air Waybills'},
                                       {'name': 'Fleet Trips'},
                                       {'name': 'Customs'}], 'total': 3},
            'module_context': {'installed_modules': 92, 'studio_installed': True},
            'installed_modules': {'items': [
                {'name': 'sale', 'display_name': 'Sales', 'author': 'Odoo S.A.'},
                {'name': 'aurora_connector', 'display_name': 'Aurora Carrier Connector',
                 'author': 'Aurora IT'},
                {'name': 'partner_firstname', 'display_name': 'Partner first name',
                 'author': 'Camptocamp, Odoo Community Association (OCA)'},
            ], 'total': 92},
            'identity': {'user_name': 'Demo Auditor', 'user_login': 'audit@aurora-demo.example',
                         'company_name': 'Aurora Trading S.L. (demo)',
                         'company_street': '', 'company_city': 'Valencia',
                         'company_country': 'Spain', 'company_logo': '',
                         'companies_total': 2},
            'usage': {'custom_model_records': [
                {'model': 'x_air_waybill', 'records': 41902},
                {'model': 'x_fleet_trip', 'records': 26114},
                {'model': 'x_customs_doc', 'records': 11348},
                {'model': 'x_test_model', 'records': 0},
                {'model': 'x_old_import', 'records': 0},
            ], 'skipped_models': 0,
                'business_volumes': {'res.partner': 5214, 'sale.order': 7120,
                                     'account.move': 18430, 'stock.picking': 22765,
                                     'mail.message': 96412}},
            'users_pulse': {'internal_users': 41, 'portal_users': 130,
                            'active_users_30d': 34},
            'storage': {'attachments': 38400, 'attachment_bytes': 13287555072},
            'ops_flags': {'crons_active': 14, 'crons_disabled': 3, 'stuck_mails': 12},
            'code_customizations': {'modules': [
                {'module': 'aurora_connector', 'origin': 'custom',
                 'counts': {'ir.model': 1, 'ir.model.fields': 19, 'ir.ui.view': 6,
                            'ir.actions.server': 3, 'base.automation': 1,
                            'ir.cron': 1, 'ir.actions.report': 2}, 'total': 33},
                {'module': 'partner_firstname', 'origin': 'oca',
                 'counts': {'ir.model.fields': 4, 'ir.ui.view': 2}, 'total': 6},
            ], 'code_model_records': [
                {'model': 'aurora.shipment.leg', 'label': 'Shipment Leg',
                 'records': 7300}], 'total_items': 39},
        },
    }


AI_INSIGHTS = {
    'language': 'en',
    'narrative': ('Aurora Trading runs its core logistics on Studio models: the air '
                  'waybills, fleet trips and customs documents — almost 80,000 '
                  'records — live entirely in database-defined models that a '
                  'standard upgrade will not carry over. The two empty test models '
                  'are easy cleanup wins, and the 16 hand-made automations and code '
                  'actions deserve a documented review before the next version jump.'),
    'business_domains': ['Freight & logistics', 'Customs clearance', 'Fleet operations'],
    'priority_hint': 'Package the three business-critical Studio models as proper modules before upgrading.',
    'board_summary': ('Core operations depend on undocumented Studio structures holding '
                      '~80,000 records. Upgrading safely requires converting them to '
                      'maintained modules first — the empty experiments can simply be deleted.'),
    'questions_for_your_team': [
        'Who can explain how the air waybill workflow was built — and is any of it documented?',
        'Which of the 6 automated actions would break silently if a field changed?',
        'Why are reports still corrected manually before month-end?',
    ],
}


def build_result_json():
    inventory = build_inventory()
    analysis = analyze(inventory)
    scoring = compute_score(analysis['totals'], usage=analysis.get('usage_summary'))
    return {
        'meta': {**inventory['meta'], 'demo': True},
        'module_context': inventory['sections']['module_context'],
        'analysis': {
            'findings': analysis['findings'],
            'totals': analysis['totals'],
            'model_breakdown': analysis['model_breakdown'][:15],
            'sections_with_errors': analysis['sections_with_errors'],
        },
        'scoring': scoring,
        'modules': analysis.get('module_summary'),
        'ai_insights': AI_INSIGHTS,
        'identity': analysis.get('identity'),
        'pulse': analysis.get('pulse'),
        'usage': analysis.get('usage_summary'),
        'code': analysis.get('code_summary'),
    }


def get_or_create_demo_run():
    from tools_core.models import ToolRun
    run = ToolRun.objects.filter(pk=DEMO_RUN_ID).first()
    if run is None:
        run = ToolRun.objects.create(
            id=DEMO_RUN_ID, lead=None, tool_slug='studio_xray', status='done',
            odoo_url='https://demo.bidatia.example', odoo_db='aurora-trading',
            odoo_version='16.0', finished_at=timezone.now(),
            expires_at=timezone.now() + timedelta(days=3650),
            result_json=build_result_json(),
        )
    return run
