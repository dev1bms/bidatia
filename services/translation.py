"""Database-content translation registration for the services app.

Only customer-facing text fields are translated. Structural fields (slug, icon,
order, booleans, timestamps) are intentionally left untranslated.
"""
from modeltranslation.translator import TranslationOptions, register

from .models import Service, ServiceFAQ, ServiceFeature


@register(Service)
class ServiceTranslationOptions(TranslationOptions):
    fields = (
        'title',
        'short_description',
        'description',
        'outcome',
        'price_label',
        'delivery_time',
        'meta_description',
    )


@register(ServiceFeature)
class ServiceFeatureTranslationOptions(TranslationOptions):
    fields = ('text',)


@register(ServiceFAQ)
class ServiceFAQTranslationOptions(TranslationOptions):
    fields = ('question', 'answer')
