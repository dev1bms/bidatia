from django.db import models


class EmailLog(models.Model):
    """Archive of every email the system sends.

    Created by core.email_service.send_email — the single gate all outgoing
    mail passes through. Rows are written BEFORE the SMTP attempt, so a
    failed send is recorded with its error instead of disappearing silently.

    Privacy rules: `metadata` must never contain secrets, tokens or
    credentials; `related_*` are loose string references (no FK) so the log
    survives the referenced object's deletion. Visible in the admin only.
    """

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('sent', 'Sent'),
        ('failed', 'Failed'),
    ]

    recipient_email = models.EmailField(db_index=True)
    recipient_name = models.CharField(max_length=150, blank=True)
    subject = models.CharField(max_length=255)
    category = models.CharField(max_length=40, db_index=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')

    text_body = models.TextField(blank=True)
    html_body = models.TextField(blank=True)

    # e.g. related_type='tools_core.toolrun', related_id='<uuid>'
    related_type = models.CharField(max_length=60, blank=True)
    related_id = models.CharField(max_length=64, blank=True)

    error_message = models.CharField(max_length=300, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'email log'

    def __str__(self):
        return f'{self.category} → {self.recipient_email} · {self.status}'
