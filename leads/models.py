from django.db import models


class Lead(models.Model):
    SOURCE_CHOICES = [
        ('contact_form', 'Contact form'),
        ('newsletter', 'Newsletter signup'),
        ('resource_download', 'Resource download'),
        ('other', 'Other'),
    ]

    name = models.CharField(max_length=120)
    email = models.EmailField()
    company_name = models.CharField(max_length=150, blank=True)
    message = models.TextField(blank=True)
    source = models.CharField(max_length=30, choices=SOURCE_CHOICES, default='contact_form')

    is_handled = models.BooleanField(default=False)
    internal_notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.name} <{self.email}>'
