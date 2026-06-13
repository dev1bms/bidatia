"""Lead creation/update helpers shared by all tool apps."""
from django.utils import timezone

from tools_core.models import Lead


def capture_lead(email, source_tool, *, full_name='', company='', role='', consent_marketing=False):
    """Create (or update) a tool lead, keyed by email + source tool.

    Re-submitting the same email for the same tool updates the existing lead
    instead of duplicating it. Consent is only ever turned ON here (with a
    timestamp); revoking consent is a manual/GDPR process, not a form side effect.
    """
    email = email.strip().lower()
    lead, created = Lead.objects.get_or_create(
        email=email,
        source_tool=source_tool,
        defaults={
            'full_name': full_name,
            'company': company,
            'role': role,
        },
    )

    changed = False
    if not created:
        for field, value in (('full_name', full_name), ('company', company), ('role', role)):
            if value and getattr(lead, field) != value:
                setattr(lead, field, value)
                changed = True

    if consent_marketing and not lead.consent_marketing:
        lead.consent_marketing = True
        lead.consent_timestamp = timezone.now()
        changed = True

    if changed:
        lead.save()
    return lead
