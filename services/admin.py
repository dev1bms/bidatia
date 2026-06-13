from django.contrib import admin
from django.utils.html import format_html
from modeltranslation.admin import TabbedTranslationAdmin, TranslationTabularInline
from unfold.admin import ModelAdmin, TabularInline

from .models import Service, ServiceFAQ, ServiceFeature


class ServiceFeatureInline(TabularInline, TranslationTabularInline):
    model = ServiceFeature
    extra = 0


class ServiceFAQInline(TabularInline, TranslationTabularInline):
    model = ServiceFAQ
    extra = 0


@admin.register(Service)
class ServiceAdmin(ModelAdmin, TabbedTranslationAdmin):
    list_display = (
        'title', 'slug', 'price_label', 'is_featured', 'is_published', 'order', 'updated_at',
    )
    list_display_links = ('title',)
    list_editable = ('is_featured', 'is_published', 'order')
    list_filter = ('is_published', 'is_featured')
    search_fields = ('title', 'short_description', 'description')
    prepopulated_fields = {'slug': ('title',)}
    ordering = ('order', 'title')
    readonly_fields = ('created_at', 'updated_at', 'public_url')
    inlines = (ServiceFeatureInline, ServiceFAQInline)

    @admin.display(description='Public URL')
    def public_url(self, obj):
        if not obj.pk:
            return '—'
        url = obj.get_absolute_url()
        return format_html('<a href="{}" target="_blank" rel="noopener noreferrer">{}</a>', url, url)
