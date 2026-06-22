from django import forms
from django.contrib import admin, messages
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html, format_html_join
from django.utils.translation import gettext_lazy as _

from unfold.admin import ModelAdmin
from unfold.decorators import action as unfold_action

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
        to=to, subject=str(_('BidERP — test email')), category='system',
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


class AIConfigurationForm(forms.ModelForm):
    """When the Ollama host is reachable, turn `model_name` into a dropdown of
    the models actually pulled there, so the admin picks instead of typing (and
    can't typo a tag). Falls back to a free-text box if Ollama is unreachable,
    so the form never hangs or breaks."""

    class Meta:
        model = AIConfiguration
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            from tools_core.services.ai_service import list_models
            models = list_models(timeout=3)
        except Exception:  # noqa: BLE001 — unreachable/slow → keep the text box
            models = []
        if models:
            current = (self.instance.model_name or '').strip()
            choices = [('', '— ' + str(_('select an installed model')) + ' —')]
            choices += [(m, m) for m in models]
            if current and current not in models:
                # Don't silently drop a configured-but-not-installed model.
                choices.append((current, f'{current} ({_("not installed")})'))
            self.fields['model_name'] = forms.ChoiceField(
                choices=choices, required=False,
                label=self.fields['model_name'].label,
                help_text=_('Models installed on the Ollama host. Pull more with '
                            '"ollama pull <name>" on the server, then reload this page.'))


def _record_ai_self_test():
    """Run a live AI call and persist the outcome on the config row. Returns
    (ok, detail) so both the changelist action and the change-form button can
    report it."""
    from tools_core.services.ai_service import self_test

    cfg = AIConfiguration.load()
    ok, detail = self_test()
    cfg.last_ai_test_status = 'ok' if ok else 'failed'
    cfg.last_ai_test_at = timezone.now()
    cfg.last_ai_test_message = detail[:300]
    cfg.save()
    return ok, detail


@admin.action(description=_('Run AI self-test (live call to the model)'))
def run_ai_self_test(modeladmin, request, queryset):
    ok, detail = _record_ai_self_test()
    modeladmin.message_user(request, detail,
                            level=messages.SUCCESS if ok else messages.ERROR)


@admin.register(AIConfiguration)
class AIConfigurationAdmin(SingletonAdmin):
    form = AIConfigurationForm
    actions = [run_ai_self_test]
    # A button at the top of the change form itself (not just the list action).
    actions_detail = ['ai_self_test_button']
    list_display = ('__str__', 'enabled', 'model_name', 'last_ai_test_status', 'updated_at')
    readonly_fields = ('ai_health', 'last_ai_test_status', 'last_ai_test_at',
                       'last_ai_test_message', 'updated_at', 'updated_by')
    fieldsets = (
        (_('Status'), {'fields': ('ai_health',)}),
        (None, {'fields': ('enabled', 'provider', 'model_name')}),
        (_('Limits'), {'fields': ('request_timeout', 'thinking_budget',
                                  'max_output_tokens', 'temperature')}),
        (_('Skills / system instructions'), {'fields': ('system_instructions',)}),
        (_('Last self-test'), {'fields': ('last_ai_test_status', 'last_ai_test_at',
                                          'last_ai_test_message')}),
        (_('Audit'), {'fields': ('updated_at', 'updated_by')}),
    )

    def save_model(self, request, obj, form, change):
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)

    @unfold_action(description=_('Test AI now'), url_path='ai-self-test')
    def ai_self_test_button(self, request, object_id):
        """Top-of-page button: runs a live call to the configured model and
        flashes success or the exact error, then reloads the page."""
        ok, detail = _record_ai_self_test()
        messages.success(request, detail) if ok else messages.error(request, detail)
        return redirect(reverse('admin:site_config_aiconfiguration_change',
                                args=[object_id]))

    @admin.display(description=_('AI health'))
    def ai_health(self, obj):
        """Live snapshot: is Ollama reachable, which models are pulled, and is
        the configured model among them — so the owner can see at a glance why
        the AI layer is or isn't working, and copy an exact model name."""
        from tools_core.services.ai_service import health_check

        h = health_check(timeout=3)

        def row(label, value, good=None):
            color = '' if good is None else ('#16a34a' if good else '#dc2626')
            mark = '' if good is None else ('✓ ' if good else '✗ ')
            return format_html(
                '<div style="display:flex;gap:.5rem;padding:.15rem 0">'
                '<b style="min-width:170px">{}</b>'
                '<span style="color:{}">{}{}</span></div>',
                label, color, mark, value)

        rows = [
            row(_('Master switch'), _('On') if h['enabled'] else _('Off'), h['enabled']),
            row(_('Ollama host'), h['url'], None),
            row(_('Reachable'), _('Yes') if h['reachable'] else (h['error'] or _('No')),
                h['reachable']),
            row(_('Configured model'), h['model'] or _('(none)'), bool(h['model'])),
        ]
        if h['reachable']:
            rows.append(row(_('Model installed'),
                            _('Yes') if h['model_present'] else _('NOT found — pull it or pick another'),
                            h['model_present']))
            if h['models']:
                rows.append(row(_('Installed models'), ', '.join(h['models']), None))
            else:
                rows.append(row(_('Installed models'), _('none pulled yet'), False))
        overall_ok = h['enabled'] and h['reachable'] and h['model_present']
        banner = format_html(
            '<div style="font-weight:700;margin-bottom:.5rem;color:{}">{}</div>',
            '#16a34a' if overall_ok else '#dc2626',
            _('AI is ready ✓') if overall_ok else _('AI not ready — see below, then use “Run AI self-test”'))
        return format_html('{}{}', banner,
                           format_html_join('', '{}', ((r,) for r in rows)))


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
