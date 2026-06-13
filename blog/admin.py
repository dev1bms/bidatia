from django.contrib import admin
from django.utils.html import format_html
from modeltranslation.admin import TabbedTranslationAdmin
from unfold.admin import ModelAdmin

from .covers import cover_url
from .models import BlogPost, CaseStudy


@admin.register(BlogPost)
class BlogPostAdmin(ModelAdmin, TabbedTranslationAdmin):
    list_display = ('title', 'is_published', 'published_at', 'updated_at')
    list_display_links = ('title',)
    list_editable = ('is_published',)
    list_filter = ('is_published', 'published_at')
    search_fields = ('title', 'excerpt', 'content')
    prepopulated_fields = {'slug': ('title',)}
    date_hierarchy = 'published_at'
    ordering = ('-published_at',)
    readonly_fields = ('created_at', 'updated_at', 'public_url', 'cover_preview')

    @admin.display(description='Public URL')
    def public_url(self, obj):
        if not obj.pk:
            return '—'
        url = obj.get_absolute_url()
        return format_html('<a href="{}" target="_blank" rel="noopener noreferrer">{}</a>', url, url)

    @admin.display(description='Cover preview')
    def cover_preview(self, obj):
        # Shows the cover the article will actually use: an uploaded image if
        # present, otherwise its bundled slug-mapped static cover (or default).
        if not obj.pk:
            return '—'
        return format_html(
            '<img src="{}" alt="" loading="lazy" '
            'style="max-width:360px;width:100%;height:auto;border-radius:10px;'
            'border:1px solid #e2e8f0">',
            cover_url(obj),
        )


@admin.register(CaseStudy)
class CaseStudyAdmin(ModelAdmin, TabbedTranslationAdmin):
    list_display = ('title', 'client_summary', 'is_published', 'order', 'updated_at')
    list_display_links = ('title',)
    list_editable = ('is_published', 'order')
    list_filter = ('is_published',)
    search_fields = ('title', 'client_summary', 'challenge', 'approach', 'results')
    prepopulated_fields = {'slug': ('title',)}
    ordering = ('order', '-created_at')
    readonly_fields = ('created_at', 'updated_at', 'public_url')

    @admin.display(description='Public URL')
    def public_url(self, obj):
        if not obj.pk:
            return '—'
        url = obj.get_absolute_url()
        return format_html('<a href="{}" target="_blank" rel="noopener noreferrer">{}</a>', url, url)
