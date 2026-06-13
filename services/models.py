from django.db import models
from django.urls import reverse


class Service(models.Model):
    title = models.CharField(max_length=120)
    slug = models.SlugField(unique=True)
    short_description = models.CharField(
        max_length=240,
        help_text='Shown on cards and listing pages.',
    )
    description = models.TextField(
        help_text='Full description for the service detail page. One paragraph per line.',
    )
    outcome = models.CharField(
        max_length=240,
        blank=True,
        help_text='One-line outcome the client gets, e.g. "A clear, prioritized fix list within 5 days".',
    )
    icon = models.CharField(
        max_length=50,
        blank=True,
        help_text='Icon keyword used by the template, e.g. "audit", "module", "integration", "support".',
    )
    price_label = models.CharField(
        max_length=80,
        help_text='e.g. "From €350" or "€49 per session"',
    )
    delivery_time = models.CharField(
        max_length=120,
        blank=True,
        help_text='e.g. "3-5 business days" or "Scope-based"',
    )
    is_featured = models.BooleanField(
        default=False,
        help_text='Featured services are highlighted on the homepage.',
    )
    order = models.PositiveIntegerField(default=0, help_text='Lower numbers appear first.')
    is_published = models.BooleanField(default=True)

    meta_description = models.CharField(max_length=300, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['order', 'title']

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse('services:service_detail', kwargs={'slug': self.slug})

    @property
    def description_paragraphs(self):
        return [p.strip() for p in self.description.splitlines() if p.strip()]


class ServiceFeature(models.Model):
    service = models.ForeignKey(Service, related_name='features', on_delete=models.CASCADE)
    text = models.CharField(max_length=240)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order', 'id']

    def __str__(self):
        return f'{self.service.title} — {self.text}'


class ServiceFAQ(models.Model):
    service = models.ForeignKey(Service, related_name='faqs', on_delete=models.CASCADE)
    question = models.CharField(max_length=255)
    answer = models.TextField()
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order', 'id']
        verbose_name = 'FAQ'
        verbose_name_plural = 'FAQs'

    def __str__(self):
        return self.question
