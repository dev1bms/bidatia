"""Tests for the unified email layer: core.email_service + EmailLog archive."""
from unittest import mock

from django.core import mail
from django.test import TestCase, override_settings

from core.email_service import send_email
from core.models import EmailLog


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class SendEmailServiceTests(TestCase):
    def test_successful_send_is_archived(self):
        log = send_email(
            to='client@example.com', recipient_name='Cliff',
            subject='Hello there', category='system',
            heading='A heading', paragraphs=['First paragraph.'],
            cta_label='Open it', cta_url='https://bidatia.xyz/x/',
            metadata={'kind': 'unit-test'},
        )
        self.assertEqual(log.status, 'sent')
        self.assertIsNotNone(log.sent_at)
        self.assertEqual(log.recipient_email, 'client@example.com')
        self.assertEqual(log.category, 'system')
        self.assertEqual(log.metadata, {'kind': 'unit-test'})
        self.assertEqual(EmailLog.objects.count(), 1)

        # The actual message carries both bodies.
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ['client@example.com'])
        self.assertIn('First paragraph.', message.body)
        self.assertIn('https://bidatia.xyz/x/', message.body)
        html = message.alternatives[0][0]
        self.assertEqual(message.alternatives[0][1], 'text/html')
        self.assertIn('First paragraph.', html)
        self.assertIn('https://bidatia.xyz/x/', html)

    def test_failed_send_is_archived_with_error_and_never_raises(self):
        with mock.patch('core.email_service.EmailMultiAlternatives.send',
                        side_effect=OSError('smtp down')):
            log = send_email(to='client@example.com', subject='s',
                             category='system', paragraphs=['p'])
        self.assertEqual(log.status, 'failed')
        self.assertIn('OSError', log.error_message)
        self.assertIsNone(log.sent_at)
        # The archive keeps the full content even for failures.
        self.assertIn('p', log.text_body)

    def test_unified_template_used_for_html(self):
        log = send_email(to='x@example.com', subject='s', category='system',
                         heading='H', paragraphs=['P'])
        self.assertIn('BidERP', log.html_body)                  # header brand
        self.assertIn('ERP · Odoo · Django', log.html_body)     # header tagline
        self.assertIn('role="presentation"', log.html_body)     # email-safe tables
        self.assertIn('mailto:', log.html_body)                 # footer contact

    def test_text_and_html_both_present(self):
        log = send_email(to='x@example.com', subject='s', category='system',
                         heading='Heading text', paragraphs=['Body text'],
                         rows=[('Label', 'Value')],
                         panel={'label': 'Box', 'text': 'Panel text'})
        for body in (log.text_body, log.html_body):
            self.assertIn('Heading text', body)
            self.assertIn('Body text', body)
            self.assertIn('Label', body)
            self.assertIn('Value', body)
            self.assertIn('Panel text', body)

    def test_arabic_email_is_rtl(self):
        log = send_email(to='x@example.com', subject='s', category='system',
                         heading='مرحبا', paragraphs=['فقرة'], language='ar')
        self.assertIn('dir="rtl"', log.html_body)
        self.assertIn('lang="ar"', log.html_body)
        self.assertIn('text-align:right', log.html_body)
        # English stays LTR.
        log_en = send_email(to='x@example.com', subject='s', category='system',
                            heading='Hi', language='en')
        self.assertIn('dir="ltr"', log_en.html_body)

    def test_related_object_reference_stored(self):
        from tools_core.models import ToolRun
        run = ToolRun.objects.create(tool_slug='studio_xray',
                                     odoo_url='https://x.odoo.com', odoo_db='x')
        log = send_email(to='x@example.com', subject='s', category='tool_report',
                         related=run)
        self.assertEqual(log.related_type, 'tools_core.toolrun')
        self.assertEqual(log.related_id, str(run.pk))

    def test_no_cta_renders_without_button(self):
        log = send_email(to='x@example.com', subject='s', category='system',
                         paragraphs=['Just text'])
        self.assertNotIn('display:inline-block', log.html_body)


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class NotificationHelpersTests(TestCase):
    def test_contact_notification_goes_through_unified_service(self):
        from core.notifications import notify_lead
        from leads.models import Lead
        lead = Lead.objects.create(name='Visitor', email='v@example.com',
                                   message='I need help with Odoo.')
        self.assertTrue(notify_lead(lead))

        log = EmailLog.objects.get()
        self.assertEqual(log.category, 'contact_notification')
        self.assertEqual(log.status, 'sent')
        self.assertEqual(log.related_type, 'leads.lead')
        self.assertIn('I need help with Odoo.', log.html_body)

        message = mail.outbox[0]
        self.assertEqual(message.reply_to, ['v@example.com'])
        self.assertIn('New contact message: Visitor', message.subject)

    def test_notification_failure_returns_false_and_is_archived(self):
        from core.notifications import notify_lead
        from leads.models import Lead
        lead = Lead.objects.create(name='V', email='v@example.com', message='m')
        with mock.patch('core.email_service.EmailMultiAlternatives.send',
                        side_effect=OSError('down')):
            self.assertFalse(notify_lead(lead))
        self.assertEqual(EmailLog.objects.get().status, 'failed')


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class ReportEmailTests(TestCase):
    def _run(self):
        from tools_core.models import Lead as ToolLead, ToolRun
        lead = ToolLead.objects.create(email='cto@example.com',
                                       full_name='CTO', source_tool='studio_xray')
        return ToolRun.objects.create(lead=lead, tool_slug='studio_xray',
                                      odoo_url='https://x.odoo.com', odoo_db='x')

    def test_report_email_uses_service_and_keeps_content(self):
        from tools_core.services.report_service import send_report_email
        run = self._run()
        ok = send_report_email(run, f'/en/tools/studio-xray/report/{run.pk}/',
                               'Studio X-Ray', ai_summary='Your scan summary.')
        self.assertTrue(ok)

        log = EmailLog.objects.get()
        self.assertEqual(log.category, 'tool_report')
        self.assertEqual(log.related_id, str(run.pk))
        self.assertEqual(log.metadata, {'tool_slug': 'studio_xray'})

        message = mail.outbox[0]
        self.assertIn('Studio X-Ray', message.subject)
        # The tokenized link and the AI summary survive in BOTH bodies.
        for body in (message.body, message.alternatives[0][0]):
            self.assertIn(f'/tools/studio-xray/report/{run.pk}/', body)
            self.assertIn('Your scan summary.', body)

    def test_arabic_report_email_is_rtl_and_localized(self):
        from tools_core.services.report_service import send_report_email
        run = self._run()
        send_report_email(run, f'/en/tools/studio-xray/report/{run.pk}/',
                          'Studio X-Ray', language='ar')
        log = EmailLog.objects.get()
        self.assertIn('dir="rtl"', log.html_body)
        self.assertIn('جاهز', log.html_body)        # localized heading
        self.assertIn('عرض تقريري', log.html_body)  # localized CTA

    def test_no_lead_means_no_email_and_no_archive(self):
        from tools_core.models import ToolRun
        from tools_core.services.report_service import send_report_email
        run = ToolRun.objects.create(tool_slug='studio_xray',
                                     odoo_url='https://x.odoo.com', odoo_db='x')
        self.assertFalse(send_report_email(run, '/x/', 'Studio X-Ray'))
        self.assertEqual(EmailLog.objects.count(), 0)
        self.assertEqual(len(mail.outbox), 0)


@override_settings(ALLOWED_HOSTS=['testserver'])
class LaunchHardeningTests(TestCase):
    def test_healthz_ok(self):
        data = self.client.get('/healthz/')
        self.assertEqual(data.status_code, 200)
        self.assertEqual(data.json(), {'status': 'ok'})

    def test_analytics_snippet_gated(self):
        # The GA snippet only renders when analytics is on AND a measurement id
        # is configured (the id is env-driven, never committed).
        with override_settings(ENABLE_ANALYTICS=False, GA_MEASUREMENT_ID='G-TEST123'):
            self.assertNotIn(b'googletagmanager',
                             self.client.get('/en/').content)
        with override_settings(ENABLE_ANALYTICS=True, GA_MEASUREMENT_ID=''):
            self.assertNotIn(b'googletagmanager',
                             self.client.get('/en/').content)
        with override_settings(ENABLE_ANALYTICS=True, GA_MEASUREMENT_ID='G-TEST123'):
            content = self.client.get('/en/').content
            self.assertIn(b'googletagmanager', content)
            self.assertIn(b'G-TEST123', content)

    def test_tool_pages_have_custom_og_images(self):
        for url, image in [('/en/tools/', 'og-tools-hub.png'),
                           ('/en/tools/studio-xray/', 'og-studio-xray.png'),
                           ('/en/tools/erp-rescue/', 'og-erp-rescue.png')]:
            self.assertIn(image.encode(), self.client.get(url).content)

    def test_admin_email_handler_configured(self):
        from django.conf import settings
        self.assertTrue(settings.ADMINS)
        handlers = settings.LOGGING['loggers']['django.request']['handlers']
        self.assertIn('mail_admins', handlers)
