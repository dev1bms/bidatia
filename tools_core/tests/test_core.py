from datetime import timedelta

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from tools_core.models import Lead, ToolRun
from tools_core.services.lead_service import capture_lead


class ToolRunModelTests(TestCase):
    def test_expires_at_defaults_to_72_hours(self):
        run = ToolRun.objects.create(tool_slug='studio_xray', odoo_url='https://example.odoo.com', odoo_db='example')
        delta = run.expires_at - timezone.now()
        self.assertGreater(delta, timedelta(hours=71))
        self.assertLessEqual(delta, timedelta(hours=72))
        self.assertFalse(run.is_expired)

    def test_uuid_primary_keys(self):
        run = ToolRun.objects.create(tool_slug='studio_xray', odoo_url='https://example.odoo.com', odoo_db='example')
        lead = Lead.objects.create(email='cto@example.com', source_tool='studio_xray')
        # UUIDs, not sequential ints — both are used in public URLs / admin.
        self.assertEqual(len(str(run.pk)), 36)
        self.assertEqual(len(str(lead.pk)), 36)


class CaptureLeadTests(TestCase):
    def test_creates_lead_with_normalized_email(self):
        lead = capture_lead('  CTO@Example.COM ', source_tool='waitlist_studio_xray')
        self.assertEqual(lead.email, 'cto@example.com')
        self.assertFalse(lead.consent_marketing)
        self.assertIsNone(lead.consent_timestamp)

    def test_same_email_same_tool_does_not_duplicate(self):
        capture_lead('cto@example.com', source_tool='waitlist_studio_xray')
        capture_lead('cto@example.com', source_tool='waitlist_studio_xray', company='Acme')
        self.assertEqual(Lead.objects.count(), 1)
        self.assertEqual(Lead.objects.get().company, 'Acme')

    def test_same_email_different_tool_creates_separate_lead(self):
        capture_lead('cto@example.com', source_tool='waitlist_studio_xray')
        capture_lead('cto@example.com', source_tool='waitlist_migration_scanner')
        self.assertEqual(Lead.objects.count(), 2)

    def test_consent_sets_timestamp_once(self):
        lead = capture_lead('cto@example.com', source_tool='studio_xray', consent_marketing=True)
        self.assertTrue(lead.consent_marketing)
        first_ts = lead.consent_timestamp
        self.assertIsNotNone(first_ts)
        lead = capture_lead('cto@example.com', source_tool='studio_xray', consent_marketing=True)
        self.assertEqual(lead.consent_timestamp, first_ts)


@override_settings(ALLOWED_HOSTS=['testserver'])
class HubViewTests(TestCase):
    def test_hub_renders_with_tool_cards(self):
        resp = self.client.get('/en/tools/')
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        self.assertIn('Odoo Studio X-Ray', content)
        self.assertIn('Migration Readiness Scanner', content)
        self.assertIn('COMING SOON', content)

    def test_waitlist_signup_creates_lead(self):
        resp = self.client.post('/en/tools/', {'tool': 'studio_xray', 'email': 'cto@example.com', 'website': ''})
        self.assertRedirects(resp, '/en/tools/')
        lead = Lead.objects.get()
        self.assertEqual(lead.email, 'cto@example.com')
        self.assertEqual(lead.source_tool, 'waitlist_studio_xray')

    def test_honeypot_blocks_bot_but_pretends_success(self):
        resp = self.client.post(
            '/en/tools/',
            {'tool': 'studio_xray', 'email': 'bot@spam.com', 'website': 'http://spam.example'},
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Lead.objects.count(), 0)

    def test_invalid_email_rejected(self):
        self.client.post('/en/tools/', {'tool': 'studio_xray', 'email': 'not-an-email', 'website': ''})
        self.assertEqual(Lead.objects.count(), 0)

    def test_unknown_tool_slug_rejected(self):
        self.client.post('/en/tools/', {'tool': 'evil_slug', 'email': 'cto@example.com', 'website': ''})
        self.assertEqual(Lead.objects.count(), 0)

    def test_hub_reverse_name(self):
        self.assertEqual(reverse('tools_core:hub'), '/en/tools/')
