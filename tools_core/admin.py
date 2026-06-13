from django.contrib import admin
from django.utils.html import format_html

from .models import HealthBadge, Lead, ReportQuestion, ToolEvent, ToolRun


@admin.register(Lead)
class ToolLeadAdmin(admin.ModelAdmin):
    # Lead-quality signals up front: company + detected Odoo metadata tell us
    # who is worth a manual follow-up.
    list_display = (
        'email', 'company', 'source_tool',
        'odoo_version_detected', 'odoo_edition_detected',
        'consent_marketing', 'created_at',
    )
    list_filter = ('source_tool', 'consent_marketing', 'odoo_edition_detected')
    search_fields = ('email', 'full_name', 'company')
    readonly_fields = ('id', 'created_at', 'updated_at', 'consent_timestamp')
    date_hierarchy = 'created_at'


@admin.register(ToolRun)
class ToolRunAdmin(admin.ModelAdmin):
    list_display = (
        'tool_slug', 'status', 'odoo_url', 'odoo_version',
        'lead', 'created_at', 'finished_at', 'expires_at',
    )
    list_filter = ('tool_slug', 'status')
    search_fields = ('odoo_url', 'odoo_db', 'lead__email')
    readonly_fields = ('id', 'result_json', 'created_at', 'finished_at', 'expires_at')
    date_hierarchy = 'created_at'


@admin.register(HealthBadge)
class HealthBadgeAdmin(admin.ModelAdmin):
    """Public badges. Revoking (action below) keeps the URL but blanks the
    page and the SVG — the privacy promise made on the offer form."""
    list_display = ('created_at', 'tool_slug', 'level_code', 'company_name',
                    'is_active', 'run')
    list_filter = ('tool_slug', 'level_code', 'is_active')
    search_fields = ('company_name', 'run__id')
    readonly_fields = ('id', 'run', 'tool_slug', 'level_code', 'created_at')
    actions = ('revoke_badges',)

    @admin.action(description='Revoke selected badges (disable public page)')
    def revoke_badges(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f'{updated} badge(s) revoked.')


@admin.register(ToolEvent)
class ToolEventAdmin(admin.ModelAdmin):
    """The funnel, event by event. Click a visitor key to see that person's
    whole journey across tools."""
    list_display = ('created_at', 'tool', 'event', 'email', 'run', 'journey')
    list_filter = ('tool', 'event', 'created_at')
    search_fields = ('email', 'visitor_key', 'run__id')
    date_hierarchy = 'created_at'
    readonly_fields = ('tool', 'event', 'run', 'email', 'visitor_key',
                       'metadata', 'created_at')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def lookup_allowed(self, lookup, value, request=None):
        # Allow the journey link's ?visitor_key= filter.
        return lookup == 'visitor_key' or super().lookup_allowed(lookup, value, request)

    @admin.display(description='journey')
    def journey(self, obj):
        if not obj.visitor_key:
            return '—'
        return format_html('<a href="?visitor_key={}">{}…</a>',
                           obj.visitor_key, obj.visitor_key[:8])


@admin.register(ReportQuestion)
class ReportQuestionAdmin(admin.ModelAdmin):
    """What prospects ask the report AI — read it like a sales signal."""
    list_display = ('created_at', 'short_question', 'status', 'language', 'run')
    list_filter = ('status', 'language')
    search_fields = ('question', 'answer')
    readonly_fields = ('id', 'run', 'question', 'answer', 'language', 'status', 'created_at')
    date_hierarchy = 'created_at'

    @admin.display(description='question')
    def short_question(self, obj):
        return (obj.question[:80] + '…') if len(obj.question) > 80 else obj.question
