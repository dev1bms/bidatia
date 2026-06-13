from django.contrib import admin
from unfold.admin import ModelAdmin

from .models import Lead


@admin.register(Lead)
class LeadAdmin(ModelAdmin):
    list_display = ('name', 'email', 'company_name', 'source', 'is_handled', 'created_at')
    list_display_links = ('name',)
    list_editable = ('is_handled',)
    list_filter = ('source', 'is_handled', 'created_at')
    search_fields = ('name', 'email', 'company_name', 'message')
    date_hierarchy = 'created_at'
    ordering = ('-created_at',)
    readonly_fields = ('created_at',)
    actions = ('mark_handled', 'mark_unhandled')
    fieldsets = (
        ('Contact', {
            'fields': ('name', 'email', 'company_name'),
        }),
        ('Message', {
            'fields': ('source', 'message'),
        }),
        ('Internal', {
            'fields': ('is_handled', 'internal_notes', 'created_at'),
        }),
    )

    @admin.action(description='Mark selected as handled')
    def mark_handled(self, request, queryset):
        updated = queryset.update(is_handled=True)
        self.message_user(request, f'{updated} lead(s) marked as handled.')

    @admin.action(description='Mark selected as not handled')
    def mark_unhandled(self, request, queryset):
        updated = queryset.update(is_handled=False)
        self.message_user(request, f'{updated} lead(s) marked as not handled.')
