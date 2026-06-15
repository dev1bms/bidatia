"""Generic background-job tracking.

A ``BackgroundTask`` row is the single, reusable record behind the
"your request is being processed" UX. Any slow operation (sending a
notification email, generating an export, …) can create one, hand the
public UUID to the browser, and update it from a Celery worker.

Security / privacy contract:
* The UUID pk is what appears in public URLs — never a sequential int.
* ``error_message`` is for the admin only; the status API never returns it
  raw. Public callers get a fixed, translated, user-safe message instead.
  Never store a traceback, credential, SMTP detail or API key here.
* ``session_key`` scopes a task to the browser that created it: the status
  API refuses tasks owned by a different session (see jobs.views).
"""
import uuid

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class BackgroundTask(models.Model):
    STATUS_QUEUED = 'queued'
    STATUS_RUNNING = 'running'
    STATUS_SUCCESS = 'success'
    STATUS_FAILED = 'failed'
    STATUS_CANCELLED = 'cancelled'
    STATUS_CHOICES = [
        (STATUS_QUEUED, _('Queued')),
        (STATUS_RUNNING, _('Processing')),
        (STATUS_SUCCESS, _('Completed')),
        (STATUS_FAILED, _('Failed')),
        (STATUS_CANCELLED, _('Cancelled')),
    ]
    # Statuses the browser should keep polling on.
    ACTIVE_STATUSES = (STATUS_QUEUED, STATUS_RUNNING)

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    task_type = models.CharField(
        max_length=50, db_index=True,
        help_text=_('Machine code for the kind of job, e.g. "contact_email".'))
    title = models.CharField(
        max_length=150,
        help_text=_('Short human title shown to the user, already translated.'))
    status = models.CharField(
        max_length=12, choices=STATUS_CHOICES, default=STATUS_QUEUED, db_index=True)
    # 0–100, or NULL when the job has no measurable progress (indeterminate).
    progress = models.PositiveSmallIntegerField(null=True, blank=True)
    # Optional human step note, already translated; safe to show to the user.
    message = models.CharField(max_length=255, blank=True)
    # Where to send the user once the job succeeds (relative URL).
    result_url = models.CharField(max_length=300, blank=True)
    # Admin-only diagnostic detail. NEVER returned raw by the status API.
    error_message = models.TextField(blank=True)
    # Owning browser session (blank = not access-restricted).
    session_key = models.CharField(max_length=40, blank=True, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = _('background task')
        verbose_name_plural = _('background tasks')

    def __str__(self):
        return f'{self.task_type} · {self.status} · {self.id}'

    @property
    def is_active(self):
        """True while the browser should keep polling."""
        return self.status in self.ACTIVE_STATUSES

    # ── State transitions (called from the worker) ───────────────────────────
    def mark_running(self, message='', progress=None):
        self.status = self.STATUS_RUNNING
        if message:
            self.message = message[:255]
        if progress is not None:
            self.progress = max(0, min(100, int(progress)))
        if self.started_at is None:
            self.started_at = timezone.now()
        self.save(update_fields=['status', 'message', 'progress', 'started_at'])

    def mark_success(self, message='', result_url=''):
        self.status = self.STATUS_SUCCESS
        self.progress = 100
        if message:
            self.message = message[:255]
        if result_url:
            self.result_url = result_url[:300]
        self.finished_at = timezone.now()
        self.save(update_fields=['status', 'progress', 'message',
                                 'result_url', 'finished_at'])

    def mark_failed(self, error_message='', message=''):
        """Record a failure. ``error_message`` is admin-only; ``message`` is the
        already-translated, user-safe line."""
        self.status = self.STATUS_FAILED
        if error_message:
            self.error_message = str(error_message)[:2000]
        if message:
            self.message = message[:255]
        self.finished_at = timezone.now()
        self.save(update_fields=['status', 'error_message',
                                 'message', 'finished_at'])
