"""Database-content translation registration for the blog app.

Only customer-facing text fields are translated. Structural fields (slug,
cover_image, order, booleans, timestamps) are left untranslated.
"""
from modeltranslation.translator import TranslationOptions, register

from .models import BlogPost, CaseStudy


@register(BlogPost)
class BlogPostTranslationOptions(TranslationOptions):
    fields = ('title', 'excerpt', 'content', 'meta_description')


@register(CaseStudy)
class CaseStudyTranslationOptions(TranslationOptions):
    fields = (
        'title',
        'client_summary',
        'challenge',
        'approach',
        'results',
        'meta_description',
    )
