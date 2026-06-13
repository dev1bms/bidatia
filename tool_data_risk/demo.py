"""Public demo report: a FICTIONAL distribution company with realistic
data-quality problems, run through the REAL analyzer so the demo always
matches what the report template expects. No credentials, never expires,
meta.demo=True (DEMO badge, its own analytics event)."""
import uuid
from datetime import timedelta

from django.utils import timezone

from .analyzer import analyze

DEMO_RUN_ID = uuid.uuid5(uuid.NAMESPACE_URL,
                         'https://bidatia.xyz/tools/data-risk-profiler/demo')

# Bump whenever the demo payload/schema gains new fields: the stored demo
# run rebuilds itself on first open instead of serving a stale payload.
DEMO_VERSION = 2


def build_collected():
    """Synthetic collector output (already masked, like the real thing)."""
    return {
        'meta': {'schema_version': 1, 'tool': 'data_risk',
                 'collected_at': timezone.now().isoformat(timespec='seconds'),
                 'server_version': '16.0', 'edition': 'enterprise',
                 'db_name': 'meridian-supply', 'demo': True},
        'sections': {
            'partners': {
                'total_active': 18420, 'archived': 2210, 'companies': 4180,
                'sample_size': 2000, 'sample_full': False,
                'sample_coverage_pct': 11,
                'dup_email': {'clusters': 64, 'affected': 152,
                              'examples': ['i***@m***.com', 's***@g***.com', 'o***@m***.es']},
                'dup_vat': {'clusters': 9, 'affected': 21,
                            'examples': ['ES***41', 'ES***18', 'FR***92']},
                'dup_name': {'clusters': 37, 'affected': 86,
                             'examples': ['Me***', 'Tr***', 'Lo***']},
                'dup_phone': {'clusters': 48, 'affected': 109, 'examples': []},
                'missing_contact': 3110, 'missing_country': 720,
                'companies_missing_vat': 1490, 'placeholder_names': 23,
            },
            'products': {
                'total_templates': 6240, 'total_variants': 11830,
                'archived_templates': 940, 'sample_size': 2000,
                'sample_full': False, 'sample_coverage_pct': 17,
                'dup_default_code': {'clusters': 41, 'affected': 96,
                                     'examples': ['ME***12', 'PL***07', 'CB***3A']},
                'dup_barcode': {'clusters': 12, 'affected': 25,
                                'examples': ['84***90', '84***27']},
                'missing_default_code': 1870, 'missing_barcode': 5230,
                'zero_priced': 410, 'categories': 38,
            },
            'orphans': {
                'open_sales': 1320, 'sales_archived_partner': 47,
                'old_quotations': 286, 'so_lines_archived_product': 121,
                'open_purchases': 410, 'purchases_archived_vendor': 18,
                'open_leads': 940, 'leads_no_partner_no_email': 173,
            },
            'import_ids': {'models': {
                'res.partner': {'records': 20630, 'xids': 1860, 'coverage_pct': 9},
                'product.template': {'records': 7180, 'xids': 2010, 'coverage_pct': 28},
                'product.product': {'records': 12770, 'xids': 2010, 'coverage_pct': 16},
                'product.category': {'records': 38, 'xids': 31, 'coverage_pct': 82},
                'account.tax': {'records': 64, 'xids': 64, 'coverage_pct': 100},
            }},
            'attachments': {
                'total': 48200, 'total_bytes': 10523222016,  # ~9.8 GB
                'top_models': [
                    {'model': 'account.move', 'count': 21400, 'bytes': 5100000000},
                    {'model': 'sale.order', 'count': 9300, 'bytes': 2200000000},
                    {'model': 'res.partner', 'count': 4100, 'bytes': 900000000},
                ],
            },
            'accounting': {'old_draft_moves': 134, 'companies': 2,
                           'active_currencies': 3, 'fiscal_positions': 5},
            'ownership': {
                'inactive_users': 14, 'active_users': 52,
                'sales_inactive_owner': 96, 'leads_inactive_owner': 210,
                'partners_inactive_salesperson': 1340,
            },
            'custom_data': {'total_custom_models': 4, 'models': [
                {'model': 'x_route_plan', 'records': 8420, 'xids': 0},
                {'model': 'x_carrier_rate', 'records': 3160, 'xids': 12},
                {'model': 'x_old_price_import', 'records': 0, 'xids': 0},
            ]},
        },
    }


def build_result_json():
    collected = build_collected()
    meta = dict(collected['meta'], demo_version=DEMO_VERSION)
    return {'meta': meta, 'risk': analyze(collected)}


def get_or_create_demo_run():
    from tools_core.models import ToolRun
    run = ToolRun.objects.filter(pk=DEMO_RUN_ID).first()
    if run is None:
        return ToolRun.objects.create(
            id=DEMO_RUN_ID, lead=None, tool_slug='data_risk', status='done',
            odoo_url='https://demo.bidatia.example', odoo_db='meridian-supply',
            odoo_version='16.0', finished_at=timezone.now(),
            expires_at=timezone.now() + timedelta(days=3650),
            result_json=build_result_json(),
        )
    stored_version = (((run.result_json or {}).get('meta') or {})
                      .get('demo_version'))
    if stored_version != DEMO_VERSION:
        # The demo outlives deploys by design — refresh its stored payload
        # whenever the report schema moved on.
        run.result_json = build_result_json()
        run.save(update_fields=['result_json'])
    return run
