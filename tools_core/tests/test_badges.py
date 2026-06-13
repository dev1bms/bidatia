import uuid
from datetime import timedelta

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone

from tools_core.models import HealthBadge, ToolEvent, ToolRun
from tools_core.services.badges import badge_eligibility, get_or_create_badge


def make_run(tool_slug='erp_rescue', result_json=None, expired=False, status='done'):
    return ToolRun.objects.create(
        id=uuid.uuid4(), tool_slug=tool_slug, status=status,
        odoo_url='https://x.example.com', odoo_db='x',
        finished_at=timezone.now(),
        expires_at=timezone.now() + (timedelta(hours=-1) if expired
                                     else timedelta(hours=72)),
        result_json=result_json,
    )


STABLE_RESCUE = {'meta': {'tool': 'erp_rescue'},
                 'rescue': {'score': 10, 'level': 'stable', 'sections': {},
                            'top_risks': []}}
RISKY_RESCUE = {'meta': {'tool': 'erp_rescue'},
                'rescue': {'score': 80, 'level': 'rescue_urgent',
                           'sections': {}, 'top_risks': []}}
LOW_XRAY = {'meta': {}, 'scoring': {'score': 12, 'level': 'low'},
            'analysis': {'findings': [], 'totals': {}, 'model_breakdown': []}}
HIGH_XRAY = {'meta': {}, 'scoring': {'score': 70, 'level': 'high'},
             'analysis': {'findings': [], 'totals': {}, 'model_breakdown': []}}


@override_settings(ALLOWED_HOSTS=['testserver'])
class EligibilityTests(TestCase):
    def test_stable_rescue_is_eligible(self):
        self.assertEqual(badge_eligibility(make_run(result_json=STABLE_RESCUE)),
                         'stable')

    def test_risky_rescue_is_not(self):
        self.assertIsNone(badge_eligibility(make_run(result_json=RISKY_RESCUE)))

    def test_low_xray_is_eligible(self):
        run = make_run('studio_xray', LOW_XRAY)
        self.assertEqual(badge_eligibility(run), 'low_complexity')

    def test_high_xray_is_not(self):
        self.assertIsNone(badge_eligibility(make_run('studio_xray', HIGH_XRAY)))

    def test_expired_demo_or_unknown_never_eligible(self):
        self.assertIsNone(badge_eligibility(
            make_run(result_json=STABLE_RESCUE, expired=True)))
        demo = dict(STABLE_RESCUE, meta={'demo': True})
        self.assertIsNone(badge_eligibility(make_run(result_json=demo)))
        self.assertIsNone(badge_eligibility(make_run('other_tool', STABLE_RESCUE)))

    def test_one_badge_per_run(self):
        run = make_run(result_json=STABLE_RESCUE)
        badge1, created1 = get_or_create_badge(run, 'Acme')
        badge2, created2 = get_or_create_badge(run, 'Other Name')
        self.assertTrue(created1)
        self.assertFalse(created2)
        self.assertEqual(badge1.pk, badge2.pk)
        self.assertEqual(badge2.company_name, 'Acme')


@override_settings(ALLOWED_HOSTS=['testserver'])
class BadgeFlowTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_offer_appears_only_on_eligible_result(self):
        eligible = make_run(result_json=STABLE_RESCUE)
        response = self.client.get(f'/en/tools/erp-rescue/result/{eligible.pk}/')
        self.assertContains(response, 'Health Snapshot badge')
        self.assertTrue(ToolEvent.objects.filter(
            tool='health_badge', event='healthy_badge_offered').exists())

        risky = make_run(result_json=RISKY_RESCUE)
        response = self.client.get(f'/en/tools/erp-rescue/result/{risky.pk}/')
        self.assertNotContains(response, 'Health Snapshot badge')

    def test_create_badge_redirects_to_public_page(self):
        run = make_run(result_json=STABLE_RESCUE)
        response = self.client.post(f'/en/tools/badge/create/{run.pk}/',
                                    {'company_name': 'Acme S.L.'})
        badge = HealthBadge.objects.get(run=run)
        self.assertEqual(response.status_code, 302)
        self.assertIn(str(badge.pk), response['Location'])
        self.assertEqual(badge.company_name, 'Acme S.L.')
        self.assertTrue(ToolEvent.objects.filter(
            event='healthy_badge_created').exists())

    def test_create_rejected_for_ineligible_run(self):
        run = make_run(result_json=RISKY_RESCUE)
        response = self.client.post(f'/en/tools/badge/create/{run.pk}/')
        self.assertEqual(response.status_code, 404)
        self.assertFalse(HealthBadge.objects.exists())

    def test_public_page_shows_minimal_info_only(self):
        run = make_run(result_json=STABLE_RESCUE)
        badge, _ = get_or_create_badge(run, 'Acme S.L.')
        response = self.client.get(f'/en/tools/badge/{badge.pk}/')
        self.assertContains(response, 'Stable result')
        self.assertContains(response, 'Acme S.L.')
        self.assertContains(response, 'not a security certification')
        # privacy boundary: nothing from the report leaks
        self.assertNotContains(response, 'rescue_urgent')
        self.assertNotContains(response, '10 / 100')
        self.assertNotContains(response, 'top_risks')
        self.assertTrue(ToolEvent.objects.filter(
            event='healthy_badge_viewed').exists())

    def test_company_name_omitted_when_not_provided(self):
        run = make_run(result_json=STABLE_RESCUE)
        badge, _ = get_or_create_badge(run)
        response = self.client.get(f'/en/tools/badge/{badge.pk}/')
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Acme')

    def test_revoked_badge_shows_nothing(self):
        run = make_run(result_json=STABLE_RESCUE)
        badge, _ = get_or_create_badge(run, 'Acme S.L.')
        badge.is_active = False
        badge.save(update_fields=['is_active'])
        response = self.client.get(f'/en/tools/badge/{badge.pk}/')
        self.assertEqual(response.status_code, 410)
        self.assertContains(response, 'disabled', status_code=410)
        self.assertNotContains(response, 'Acme', status_code=410)
        # SVG also disappears
        self.assertEqual(self.client.get(
            f'/en/tools/badge/{badge.pk}/badge.svg').status_code, 404)

    def test_badge_svg_serves_svg(self):
        run = make_run(result_json=STABLE_RESCUE)
        badge, _ = get_or_create_badge(run)
        response = self.client.get(f'/en/tools/badge/{badge.pk}/badge.svg')
        self.assertEqual(response['Content-Type'], 'image/svg+xml')
        self.assertIn(b'ERP HEALTH SNAPSHOT', response.content)
        # short edge cache: a revoked badge must vanish within the hour
        self.assertIn('max-age=3600', response['Cache-Control'])

    def test_badge_survives_result_wipe(self):
        run = make_run(result_json=STABLE_RESCUE)
        badge, _ = get_or_create_badge(run)
        run.result_json = None  # 72h cleanup wipes the payload
        run.save(update_fields=['result_json'])
        response = self.client.get(f'/en/tools/badge/{badge.pk}/')
        self.assertContains(response, 'Stable result')

    def test_xray_low_report_shows_offer(self):
        run = make_run('studio_xray', LOW_XRAY)
        response = self.client.get(f'/en/tools/studio-xray/report/{run.pk}/')
        self.assertContains(response, 'Health Snapshot badge')

    def test_demo_report_never_shows_offer(self):
        from tool_studio_xray.demo import get_or_create_demo_run
        run = get_or_create_demo_run()
        response = self.client.get(f'/en/tools/studio-xray/report/{run.pk}/')
        self.assertNotContains(response, 'Health Snapshot badge')

    def test_copied_beacon_pair_is_whitelisted(self):
        response = self.client.post(
            '/en/tools/api/track/',
            '{"tool": "health_badge", "event": "healthy_badge_copied"}',
            content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(ToolEvent.objects.filter(
            event='healthy_badge_copied').exists())
