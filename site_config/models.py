"""Admin-managed runtime configuration.

Each model is a *singleton*: there is exactly one row (pk=1), edited in the
Django admin, that overrides the matching environment/``settings.py`` values at
runtime — so email recipients, SMTP credentials, AI model/timeouts, etc. can be
changed without a code deploy. Environment variables remain the bootstrap/
fallback: ``site_config.services`` reads DB first and falls back to settings.

Secret handling (see also the admin): ``EmailConfiguration.smtp_password`` is a
write-only field in the admin — it is never rendered back after saving and the
list view only shows whether a value is set. It is stored in the database in
plain text because this project does not ship a cryptography dependency; the
practical protections are (a) superuser-only admin access, (b) masked display,
and (c) keeping the real password in the environment, which stays the preferred
source. See README/report for the recommended Fernet-at-rest upgrade.
"""
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _


class SingletonModel(models.Model):
    """Base for one-row configuration tables."""

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)
        from .services import clear_config_cache
        clear_config_cache()

    def delete(self, *args, **kwargs):  # pragma: no cover - guarded in admin too
        # Never delete a config row; just blank it by editing instead.
        return

    @classmethod
    def load(cls):
        obj, _created = cls.objects.get_or_create(pk=1)
        return obj


class SiteConfiguration(SingletonModel):
    site_name = models.CharField(
        max_length=120, blank=True,
        help_text=_('Public brand name. Blank uses the SITE_NAME setting.'))
    canonical_base_url = models.URLField(
        blank=True,
        help_text=_('Absolute base URL, e.g. https://bidatia.xyz. Blank uses SITE_BASE_URL.'))
    public_contact_email = models.EmailField(
        blank=True,
        help_text=_('Address shown to visitors. Blank uses CONTACT_EMAIL.'))
    admin_recipient_email = models.EmailField(
        blank=True,
        help_text=_('Where contact/booking notifications are sent. Blank uses '
                    'CONTACT_NOTIFICATION_EMAIL.'))
    whatsapp_number = models.CharField(
        max_length=40, blank=True,
        help_text=_('Public WhatsApp/phone number. Blank uses CONTACT_WHATSAPP.'))
    business_address = models.CharField(
        max_length=200, blank=True,
        help_text=_('City / address line shown publicly.'))
    maintenance_mode = models.BooleanField(
        default=False,
        help_text=_('Reserved flag for a future maintenance banner/page. '
                    'Does not take pages offline on its own.'))

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('site settings')
        verbose_name_plural = _('site settings')

    def __str__(self):
        return str(_('Site settings'))


class EmailConfiguration(SingletonModel):
    enabled = models.BooleanField(
        default=False,
        help_text=_('When on, outgoing mail uses the SMTP details below instead '
                    'of the environment defaults.'))
    smtp_host = models.CharField(max_length=200, blank=True, help_text=_('SMTP server host.'))
    smtp_port = models.PositiveIntegerField(
        null=True, blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(65535)],
        help_text=_('SMTP port, e.g. 465 (SSL) or 587 (TLS).'))
    use_ssl = models.BooleanField(default=True, help_text=_('Use implicit SSL (port 465).'))
    use_tls = models.BooleanField(default=False, help_text=_('Use STARTTLS (port 587). Not with SSL.'))
    smtp_username = models.CharField(max_length=200, blank=True)
    # Write-only in the admin; never rendered back. See module docstring.
    smtp_password = models.CharField(max_length=255, blank=True)
    default_from_email = models.CharField(
        max_length=200, blank=True,
        help_text=_('"From" header. Blank uses DEFAULT_FROM_EMAIL.'))
    reply_to_email = models.EmailField(blank=True, help_text=_('Optional Reply-To address.'))
    test_recipient = models.EmailField(
        blank=True, help_text=_('Address used by the "Send test email" admin action.'))

    last_test_status = models.CharField(max_length=10, blank=True)
    last_test_at = models.DateTimeField(null=True, blank=True)
    last_test_message = models.CharField(max_length=300, blank=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('email settings')
        verbose_name_plural = _('email settings')

    def __str__(self):
        return str(_('Email settings'))

    @property
    def has_password(self):
        return bool(self.smtp_password)


class AIConfiguration(SingletonModel):
    enabled = models.BooleanField(
        default=True,
        help_text=_('Master switch for the AI interpretation layer on tool reports. '
                    'When on, AI still runs only if a model is configured here or via '
                    'the TOOLS_AI_MODEL environment value; turn off to force it off.'))
    provider = models.CharField(
        max_length=40, blank=True, default='ollama',
        help_text=_('AI provider key, e.g. "ollama".'))
    model_name = models.CharField(
        max_length=80, blank=True,
        help_text=_('Model id, e.g. "qwen3.5:9b". Blank uses TOOLS_AI_MODEL.'))
    request_timeout = models.PositiveIntegerField(
        null=True, blank=True, validators=[MinValueValidator(5), MaxValueValidator(900)],
        help_text=_('Overall generation deadline in seconds. Blank uses TOOLS_AI_TIMEOUT.'))
    thinking_budget = models.PositiveIntegerField(
        null=True, blank=True, validators=[MaxValueValidator(600)],
        help_text=_('Seconds of free-form reasoning before the strict-JSON pass. '
                    '0 disables thinking. Blank uses TOOLS_AI_THINKING_BUDGET.'))
    max_output_tokens = models.PositiveIntegerField(
        null=True, blank=True, validators=[MinValueValidator(64), MaxValueValidator(32000)],
        help_text=_('Optional cap on generated tokens.'))
    temperature = models.FloatField(
        null=True, blank=True, validators=[MinValueValidator(0), MaxValueValidator(2)],
        help_text=_('Creativity 0–2. Lower is more deterministic.'))
    system_instructions = models.TextField(
        blank=True,
        help_text=_('Skills / system instructions prepended to the model prompt. '
                    'Internal — never shown to visitors.'))

    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='+')

    class Meta:
        verbose_name = _('AI settings')
        verbose_name_plural = _('AI settings')

    def __str__(self):
        return str(_('AI settings'))


class OperationalConfiguration(SingletonModel):
    bookings_enabled = models.BooleanField(
        default=True, help_text=_('Allow visitors to submit booking requests.'))
    tools_enabled = models.BooleanField(
        default=True, help_text=_('Allow the free diagnostic tools to run.'))
    task_poll_interval_ms = models.PositiveIntegerField(
        default=1500, validators=[MinValueValidator(500), MaxValueValidator(15000)],
        help_text=_('How often the status component polls, in milliseconds.'))
    long_task_timeout_s = models.PositiveIntegerField(
        default=420, validators=[MinValueValidator(30), MaxValueValidator(3600)],
        help_text=_('Reference timeout for long background jobs, in seconds.'))

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('operational settings')
        verbose_name_plural = _('operational settings')

    def __str__(self):
        return str(_('Operational settings'))
