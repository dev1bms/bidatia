"""Opt-in aggregated snapshots for before/after scan comparisons.

Privacy contract (docs/data_risk_profiler/PRIVACY_MODEL.md): a snapshot is
created ONLY when the visitor ticks the opt-in box, and contains nothing
but a hashed database identity, scores and counts — no names, no emails,
no VAT numbers, no examples, no credentials. It deliberately has no FK to
ToolRun so the 72h report lifecycle stays untouched.
"""
import hashlib

from django.db import models


def db_fingerprint(odoo_url, odoo_db):
    """Pseudonymous identity for "same database scanned again": a one-way
    hash of host + db name. No reverse lookup is stored anywhere."""
    from urllib.parse import urlsplit
    host = (urlsplit(odoo_url or '').netloc or odoo_url or '').strip().lower()
    raw = f'{host}|{(odoo_db or "").strip().lower()}'
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


class DataRiskSnapshot(models.Model):
    fingerprint = models.CharField(max_length=32, db_index=True)
    score = models.PositiveSmallIntegerField()
    level = models.CharField(max_length=12)
    # {category_code: score} — scored categories only.
    category_scores = models.JSONField(default=dict)
    # A handful of headline counts (partners/products/attachments totals).
    key_counts = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'data risk snapshot'

    def __str__(self):
        return f'{self.fingerprint[:8]}… · {self.score} · {self.created_at:%Y-%m-%d}'
