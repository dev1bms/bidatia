"""Reusable email notifications for customer submissions.

Design goals:
* One small helper per submission type; all sending and archiving goes
  through core.email_service (the project-wide unified email layer).
* Notifications go To CONTACT_NOTIFICATION_EMAIL and Cc CONTACT_NOTIFICATION_CC.
* `Reply-To` is set to the customer so you can reply directly from your inbox.
* Sending never raises: if email fails, the failure is archived in EmailLog
  and we return False so the form submission is still saved and the visitor
  still sees a success page.

These are internal (owner-facing) messages and stay in English on purpose.
"""
from django.conf import settings
from django.urls import NoReverseMatch, reverse
from django.utils import timezone

from core.email_service import send_email


def _admin_url(obj):
    """Absolute admin change-URL for a saved object, or '' if unavailable."""
    try:
        path = reverse(
            f'admin:{obj._meta.app_label}_{obj._meta.model_name}_change',
            args=[obj.pk],
        )
    except (NoReverseMatch, Exception):  # pragma: no cover - defensive
        return ''
    return f"{settings.SITE_BASE_URL.rstrip('/')}{path}"


def _submitted_at(obj):
    if not getattr(obj, 'created_at', None):
        return timezone.localtime().strftime('%Y-%m-%d %H:%M %Z')
    return timezone.localtime(obj.created_at).strftime('%Y-%m-%d %H:%M %Z')


def _notify(subject, category, obj, heading, rows, panel=None, reply_to=None):
    """Send one internal notification through the unified email service."""
    log = send_email(
        to=settings.CONTACT_NOTIFICATION_EMAIL,
        subject=subject,
        category=category,
        heading=heading,
        rows=rows,
        panel=panel,
        cta_label='Open in admin',
        cta_url=_admin_url(obj),
        footnotes=[f'Submitted: {_submitted_at(obj)}'],
        cc=list(settings.CONTACT_NOTIFICATION_CC or []),
        reply_to=reply_to,
        language='en',
        related=obj,
    )
    return log.status == 'sent'


def notify_consultation_request(obj):
    """Email notification for a ConsultationRequest (booking)."""
    if getattr(obj, 'slot', None):
        slot = obj.slot
        slot_line = (
            f'{slot.date:%Y-%m-%d} {slot.start_time:%H:%M}–{slot.end_time:%H:%M} '
            f'({slot.timezone})'
        )
    else:
        slot_line = obj.preferred_datetime or '—'
    rows = [
        ('Full name', obj.full_name),
        ('Company', obj.company_name or '—'),
        ('Email', obj.email),
        ('Phone / WhatsApp', obj.phone),
        ('Country', obj.country),
        ('Preferred lang', obj.get_preferred_language_display()),
        ('Service / type', obj.get_consultation_type_display()),
        ('Payment needed', 'Yes' if obj.is_paid else 'No'),
        ('Odoo version', obj.odoo_version or '—'),
        ('Selected slot', slot_line),
        ('Preferred time', obj.preferred_datetime or '—'),
    ]
    subject = f'New consultation request: {obj.full_name} — {obj.get_consultation_type_display()}'
    return _notify(
        subject, 'booking_notification', obj,
        heading='New consultation / booking request',
        rows=rows,
        panel={'label': 'Problem summary', 'text': obj.problem_summary},
        reply_to=[obj.email],
    )


def notify_lead(obj):
    """Email notification for a Lead (contact form)."""
    rows = [
        ('Name', obj.name),
        ('Company', obj.company_name or '—'),
        ('Email', obj.email),
    ]
    return _notify(
        f'New contact message: {obj.name}', 'contact_notification', obj,
        heading='New contact message',
        rows=rows,
        panel={'label': 'Message', 'text': obj.message or '—'},
        reply_to=[obj.email],
    )
