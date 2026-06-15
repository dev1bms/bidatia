from django import forms
from django.contrib import admin, messages
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from unfold.admin import ModelAdmin

from . import services
from .models import (
    AIConfiguration,
    EmailConfiguration,
    OperationalConfiguration,
    SiteConfiguration,
)


class SingletonAdmin(ModelAdmin):
    """One editable row, superuser-only, never deletable."""

    def get_queryset(self, request):
        self.model.load()  # make sure the single row exists
        return super().get_queryset(request)

    def has_add_permission(self, request):
        return request.user.is_superuser and not self.model.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_module_permission(self, request):
        return request.user.is_superuser


@admin.register(SiteConfiguration)
class SiteConfigurationAdmin(SingletonAdmin):
    list_display = ('__str__', 'admin_recipient_email', 'maintenance_mode', 'updated_at')
    readonly_fields = ('updated_at',)
    fieldsets = (
        (_('Brand & URLs'), {'fields': ('site_name', 'canonical_base_url')}),
        (_('Contact'), {'fields': ('public_contact_email', 'admin_recipient_email',
                                   'whatsapp_number', 'business_address')}),
        (_('Flags'), {'fields': ('maintenance_mode',)}),
        (None, {'fields': ('updated_at',)}),
    )


class EmailConfigurationForm(forms.ModelForm):
    # Write-only: never rendered back; blank on save keeps the stored value.
    smtp_password = forms.CharField(
        label=_('SMTP password'), required=False,
        widget=forms.PasswordInput(render_value=False),
        help_text=_('Leave blank to keep the current password. Prefer the '
                    'EMAIL_HOST_PASSWORD environment variable in production.'))

    class Meta:
        model = EmailConfiguration
        fields = '__all__'

    def clean_smtp_password(self):
        new = self.cleaned_data.get('smtp_password')
        return new if new else self.instance.smtp_password


@admin.action(description=_('Send a test email with these settings'))
def send_test_email(modeladmin, request, queryset):
    from core.email_service import send_email

    cfg = EmailConfiguration.load()
    to = cfg.test_recipient or services.admin_recipient_email()
    if not to:
        modeladmin.message_user(
            request, _('Set a test recipient first.'), level=messages.WARNING)
        return
    log = send_email(
        to=to, subject=str(_('Bidatia — test email')), category='system',
        heading=str(_('Test email')),
        paragraphs=[str(_('This confirms your email settings are working.'))])
    cfg.last_test_status = log.status
    cfg.last_test_at = timezone.now()
    cfg.last_test_message = (log.error_message or 'OK')[:300]
    cfg.save()
    if log.status == 'sent':
        modeladmin.message_user(request, _('Test email sent to %s.') % to)
    else:
        modeladmin.message_user(
            request, _('Test email failed — see "last test" fields.'),
            level=messages.ERROR)


@admin.register(EmailConfiguration)
class EmailConfigurationAdmin(SingletonAdmin):
    form = EmailConfigurationForm
    actions = [send_test_email]
    list_display = ('__str__', 'enabled', 'smtp_host', 'password_state', 'last_test_status')
    readonly_fields = ('last_test_status', 'last_test_at', 'last_test_message', 'updated_at')
    fieldsets = (
        (None, {'fields': ('enabled',)}),
        (_('SMTP server'), {'fields': ('smtp_host', 'smtp_port', 'use_ssl', 'use_tls',
                                       'smtp_username', 'smtp_password')}),
        (_('Addresses'), {'fields': ('default_from_email', 'reply_to_email', 'test_recipient')}),
        (_('Last test'), {'fields': ('last_test_status', 'last_test_at', 'last_test_message')}),
        (None, {'fields': ('updated_at',)}),
    )

    @admin.display(description=_('Password'), boolean=True)
    def password_state(self, obj):
        return obj.has_password


@admin.register(AIConfiguration)
class AIConfigurationAdmin(SingletonAdmin):
    list_display = ('__str__', 'enabled', 'model_name', 'request_timeout', 'updated_at')
    readonly_fields = ('updated_at', 'updated_by')
    fieldsets = (
        (None, {'fields': ('enabled', 'provider', 'model_name')}),
        (_('Limits'), {'fields': ('request_timeout', 'thinking_budget',
                                  'max_output_tokens', 'temperature')}),
        (_('Skills / system instructions'), {'fields': ('system_instructions',)}),
        (_('Audit'), {'fields': ('updated_at', 'updated_by')}),
    )

    def save_model(self, request, obj, form, change):
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(OperationalConfiguration)
class OperationalConfigurationAdmin(SingletonAdmin):
    list_display = ('__str__', 'bookings_enabled', 'tools_enabled',
                    'show_tool_diagnostics', 'task_poll_interval_ms', 'updated_at')
    readonly_fields = ('updated_at',)
    fieldsets = (
        (_('Feature flags'), {'fields': ('bookings_enabled', 'tools_enabled',
                                         'show_tool_diagnostics')}),
        (_('Background tasks'), {'fields': ('task_poll_interval_ms', 'long_task_timeout_s')}),
        (None, {'fields': ('updated_at',)}),
    )
