from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from unfold.admin import ModelAdmin

from .models import BackgroundTask


@admin.register(BackgroundTask)
class BackgroundTaskAdmin(ModelAdmin):
    list_display = ('title', 'task_type', 'status', 'progress',
                    'created_at', 'finished_at')
    list_filter = ('status', 'task_type', 'created_at')
    search_fields = ('id', 'task_type', 'title')
    date_hierarchy = 'created_at'
    ordering = ('-created_at',)
    # Everything here is written by the system — read-only in the admin.
    readonly_fields = ('id', 'task_type', 'title', 'status', 'progress',
                       'message', 'result_url', 'error_message', 'session_key',
                       'created_at', 'started_at', 'finished_at')
    fieldsets = (
        (None, {'fields': ('id', 'task_type', 'title', 'status', 'progress', 'message')}),
        (_('Result'), {'fields': ('result_url', 'error_message')}),
        (_('Ownership & timing'), {
            'fields': ('session_key', 'created_at', 'started_at', 'finished_at')}),
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
