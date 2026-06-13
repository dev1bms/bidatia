import uuid
from datetime import timedelta

from django.db import models
from django.utils import timezone


def default_expires_at():
    """Tool run payloads are kept for 72 hours, then wiped by a cleanup task."""
    return timezone.now() + timedelta(hours=72)


class Lead(models.Model):
    """A person who used (or joined the waitlist for) one of the free tools.

    Kept separate from leads.Lead on purpose: tool leads carry GDPR consent,
    auto-detected Odoo metadata and per-tool attribution, and are created by
    automated tool flows rather than the contact form.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(db_index=True)
    full_name = models.CharField(max_length=120, blank=True)
    company = models.CharField(max_length=150, blank=True)
    role = models.CharField(max_length=120, blank=True)

    # Filled automatically by the connector once a tool run succeeds.
    odoo_version_detected = models.CharField(max_length=20, blank=True)
    odoo_edition_detected = models.CharField(max_length=20, blank=True)

    # GDPR: marketing consent is an explicit opt-in checkbox, never default-on.
    consent_marketing = models.BooleanField(default=False)
    consent_timestamp = models.DateTimeField(null=True, blank=True)

    source_tool = models.CharField(max_length=60)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'tool lead'

    def __str__(self):
        return f'{self.email} ({self.source_tool})'


class ToolRun(models.Model):
    """One execution of a diagnostic tool against a client Odoo.

    Credentials are NEVER stored here (or anywhere): they are passed to the
    task as arguments, used, and go out of scope. result_json holds only the
    analyzed report payload — no raw record data beyond what the report shows.
    """

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('connecting', 'Connecting'),
        ('collecting', 'Collecting'),
        ('analyzing', 'Analyzing'),
        ('ai_insights', 'AI insights'),
        ('done', 'Done'),
        ('failed', 'Failed'),
    ]

    # UUID pk is used in public URLs — never sequential ints.
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    lead = models.ForeignKey(Lead, null=True, blank=True, on_delete=models.SET_NULL, related_name='runs')
    tool_slug = models.CharField(max_length=60)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')

    odoo_url = models.URLField()
    odoo_db = models.CharField(max_length=120)
    odoo_version = models.CharField(max_length=20, blank=True)

    result_json = models.JSONField(null=True, blank=True)
    # Sanitized before saving — must never contain credentials or internal paths.
    error_message = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(default=default_expires_at)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.tool_slug} · {self.status} · {self.id}'

    @property
    def is_expired(self):
        return timezone.now() >= self.expires_at


class ToolEvent(models.Model):
    """One funnel event in the tools journey (internal analytics).

    Written by tools_core.services.analytics.track() — always best-effort,
    never blocks a request. `visitor_key` is a salted-free short hash of
    ip+user-agent (or the session) so journeys can be stitched in the admin
    WITHOUT storing the raw IP. `metadata` must never contain secrets.
    """

    tool = models.CharField(max_length=40, db_index=True)
    event = models.CharField(max_length=60, db_index=True)
    run = models.ForeignKey('ToolRun', null=True, blank=True,
                            on_delete=models.SET_NULL, related_name='events')
    email = models.EmailField(blank=True)
    visitor_key = models.CharField(max_length=16, blank=True, db_index=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.tool} · {self.event} · {self.created_at:%Y-%m-%d %H:%M}'


class HealthBadge(models.Model):
    """Opt-in public "ERP Health Snapshot" badge for excellent results.

    Privacy contract: stores ONLY the broad level code, tool type, an
    optional visitor-provided company name and the creation date — never
    report content, scores, emails or pain text. The facts are snapshotted
    here at creation (the visitor's explicit opt-in), so the badge stays
    verifiable after the run's 72h result wipe. Deliberately NOT a
    certification — wording everywhere is "snapshot", never "certified".
    """

    LEVEL_CHOICES = [
        ('stable', 'Stable result (ERP Rescue Check)'),
        ('low_complexity', 'Low-risk result (Studio X-Ray)'),
        ('low_data_risk', 'Low data migration risk (Data Risk Profiler)'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    run = models.ForeignKey(ToolRun, null=True, blank=True,
                            on_delete=models.SET_NULL, related_name='badges')
    tool_slug = models.CharField(max_length=60)
    level_code = models.CharField(max_length=30, choices=LEVEL_CHOICES)
    # Opt-in free text typed by the visitor; never auto-filled from leads.
    company_name = models.CharField(max_length=150, blank=True)
    # Revocation switch: a disabled badge keeps its URL but shows nothing.
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'health badge'

    def __str__(self):
        return f'{self.tool_slug} · {self.level_code} · {self.id}'


class ReportQuestion(models.Model):
    """One visitor question to the report AI chat, with its answer.

    Question/answer TEXT is wiped together with the run's result payload by
    the 72h cleanup task (same privacy promise as the report itself); the
    rows survive for analytics. Reading fresh questions in the admin is a
    direct sales signal — they show what the prospect worries about.
    """

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('answering', 'Answering'),
        ('done', 'Done'),
        ('failed', 'Failed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    run = models.ForeignKey(ToolRun, on_delete=models.CASCADE, related_name='questions')
    question = models.TextField()
    answer = models.TextField(blank=True)
    language = models.CharField(max_length=8, default='en')
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f'{self.run_id} · {self.status} · {self.question[:40]}'
