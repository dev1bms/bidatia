from django.db import models
from django.urls import reverse
from django.utils import timezone


class BlogPost(models.Model):
    title = models.CharField(max_length=200)
    slug = models.SlugField(unique=True)
    excerpt = models.CharField(max_length=300, help_text='Short summary shown on the blog list page.')
    content = models.TextField(help_text='Main article body. One paragraph per line.')
    cover_image = models.ImageField(upload_to='blog/', blank=True, null=True)
    is_published = models.BooleanField(default=True)
    published_at = models.DateTimeField(default=timezone.now)

    meta_description = models.CharField(max_length=300, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-published_at']

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse('blog:blog_detail', kwargs={'slug': self.slug})

    @property
    def content_paragraphs(self):
        return [p.strip() for p in self.content.splitlines() if p.strip()]


class CaseStudy(models.Model):
    title = models.CharField(max_length=200)
    slug = models.SlugField(unique=True)
    client_summary = models.CharField(
        max_length=200,
        help_text='e.g. "Mid-size distribution company, Spain" — keep it anonymous if needed.',
    )
    challenge = models.TextField(help_text='What problem the client had. One paragraph per line.')
    approach = models.TextField(help_text='What was done. One paragraph per line.')
    results = models.TextField(help_text='Outcome / measurable results. One paragraph per line.')
    is_published = models.BooleanField(default=True)
    order = models.PositiveIntegerField(default=0)

    meta_description = models.CharField(max_length=300, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['order', '-created_at']
        verbose_name_plural = 'Case studies'

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse('case_studies:case_study_detail', kwargs={'slug': self.slug})

    @property
    def challenge_paragraphs(self):
        return [p.strip() for p in self.challenge.splitlines() if p.strip()]

    @property
    def approach_paragraphs(self):
        return [p.strip() for p in self.approach.splitlines() if p.strip()]

    @property
    def results_paragraphs(self):
        return [p.strip() for p in self.results.splitlines() if p.strip()]
