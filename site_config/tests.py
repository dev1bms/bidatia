from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import RequestFactory, TestCase, override_settings

from . import services
from .admin import EmailConfigurationAdmin, EmailConfigurationForm
from .models import (
    AIConfiguration,
    EmailConfiguration,
    SiteConfiguration,
)


@override_settings(ALLOWED_HOSTS=['testserver'])
class SingletonTests(TestCase):
    def setUp(self):
        cache.clear()  # config is cached per-process; isolate tests

    def test_load_always_returns_single_row(self):
        a = SiteConfiguration.load()
        b = SiteConfiguration.load()
        self.assertEqual(a.pk, 1)
        self.assertEqual(a.pk, b.pk)
        self.assertEqual(SiteConfiguration.objects.count(), 1)

    def test_save_forces_pk_1(self):
        cfg = SiteConfiguration(site_name='X')
        cfg.save()
        self.assertEqual(cfg.pk, 1)
        cfg2 = SiteConfiguration(site_name='Y')
        cfg2.save()
        self.assertEqual(SiteConfiguration.objects.count(), 1)


@override_settings(ALLOWED_HOSTS=['testserver'])
class FallbackTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_recipient_falls_back_to_settings_when_blank(self):
        self.assertEqual(services.admin_recipient_email(),
                         settings.CONTACT_NOTIFICATION_EMAIL)

    def test_recipient_uses_db_value_when_set(self):
        cfg = SiteConfiguration.load()
        cfg.admin_recipient_email = 'ops@bidatia.xyz'
        cfg.save()  # clears the config cache
        self.assertEqual(services.admin_recipient_email(), 'ops@bidatia.xyz')

    def test_missing_row_does_not_crash_getters(self):
        # Even with nothing configured, every getter returns a usable value.
        self.assertTrue(services.default_from_email())
        self.assertTrue(services.site_base_url())
        self.assertIsInstance(services.email_connection_kwargs(), dict)


@override_settings(ALLOWED_HOSTS=['testserver'])
class EmailConfigTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_connection_kwargs_empty_when_disabled(self):
        self.assertEqual(services.email_connection_kwargs(), {})

    def test_connection_kwargs_populated_when_enabled(self):
        cfg = EmailConfiguration.load()
        cfg.enabled = True
        cfg.smtp_host = 'smtp.example.com'
        cfg.smtp_port = 587
        cfg.use_ssl = False
        cfg.use_tls = True
        cfg.smtp_username = 'u'
        cfg.smtp_password = 'secret-pw'
        cfg.save()
        kwargs = services.email_connection_kwargs()
        self.assertEqual(kwargs['host'], 'smtp.example.com')
        self.assertEqual(kwargs['port'], 587)
        self.assertTrue(kwargs['use_tls'])
        self.assertEqual(kwargs['password'], 'secret-pw')

    def test_blank_password_keeps_stored_secret(self):
        cfg = EmailConfiguration.load()
        cfg.smtp_password = 'kept-secret'
        cfg.save()
        form = EmailConfigurationForm(
            data={'enabled': False, 'smtp_host': '', 'use_ssl': True, 'use_tls': False,
                  'smtp_username': '', 'smtp_password': '',
                  'default_from_email': '', 'reply_to_email': '', 'test_recipient': ''},
            instance=cfg)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.clean_smtp_password(), 'kept-secret')

    def test_admin_list_shows_masked_password_boolean(self):
        cfg = EmailConfiguration.load()
        cfg.smtp_password = 'x'
        admin = EmailConfigurationAdmin(EmailConfiguration, None)
        self.assertTrue(admin.password_state(cfg))
        cfg.smtp_password = ''
        self.assertFalse(admin.password_state(cfg))


@override_settings(ALLOWED_HOSTS=['testserver'])
class AISettingsTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_disabled_by_default(self):
        ai = services.ai_settings()
        self.assertFalse(ai['enabled'])
        self.assertEqual(ai['timeout'], settings.TOOLS_AI_TIMEOUT)

    def test_db_model_and_flags_used(self):
        cfg = AIConfiguration.load()
        cfg.enabled = True
        cfg.model_name = 'qwen3.5:9b'
        cfg.request_timeout = 120
        cfg.thinking_budget = 0
        cfg.system_instructions = 'Be concise.'
        cfg.save()
        ai = services.ai_settings()
        self.assertTrue(ai['enabled'])
        self.assertEqual(ai['model'], 'qwen3.5:9b')
        self.assertEqual(ai['timeout'], 120)
        self.assertEqual(ai['thinking_budget'], 0)
        self.assertEqual(ai['system_instructions'], 'Be concise.')


@override_settings(ALLOWED_HOSTS=['testserver'])
class AdminPermissionTests(TestCase):
    def setUp(self):
        cache.clear()
        self.rf = RequestFactory()

    def test_config_admin_is_superuser_only(self):
        User = get_user_model()
        staff = User(username='staff', is_staff=True, is_superuser=False)
        boss = User(username='boss', is_staff=True, is_superuser=True)
        admin = EmailConfigurationAdmin(EmailConfiguration, None)
        req_staff = self.rf.get('/admin/'); req_staff.user = staff
        req_boss = self.rf.get('/admin/'); req_boss.user = boss
        self.assertFalse(admin.has_module_permission(req_staff))
        self.assertTrue(admin.has_module_permission(req_boss))
        self.assertFalse(admin.has_delete_permission(req_boss))


@override_settings(ALLOWED_HOSTS=['testserver'])
class AISelfTestActionTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_action_records_result_on_the_config_row(self):
        from unittest import mock

        from site_config.admin import run_ai_self_test
        from site_config.models import AIConfiguration

        req = RequestFactory().get('/admin/')
        with mock.patch('tools_core.services.ai_service.self_test',
                        return_value=(False, "Ollama HTTP 404: model not pulled")):
            run_ai_self_test(mock.MagicMock(), req, AIConfiguration.objects.all())

        cfg = AIConfiguration.load()
        self.assertEqual(cfg.last_ai_test_status, 'failed')
        self.assertIn('404', cfg.last_ai_test_message)
        self.assertIsNotNone(cfg.last_ai_test_at)
