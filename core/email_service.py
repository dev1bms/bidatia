"""The single place every outgoing email passes through.

Rules for ALL project email:
* Build messages from content pieces (heading, paragraphs, rows, panel,
  CTA, footnotes) — the unified template in templates/emails/ renders them
  into one consistent, email-safe design with both HTML and plain text.
* Every send is archived as a core.EmailLog row, written BEFORE the SMTP
  attempt so failures are recorded with their error, never lost silently.
* `metadata` and message content must never contain secrets, tokens,
  credentials or API keys.
* Sending never raises: callers check the returned log's status.

Usage:
    from core.email_service import send_email
    log = send_email(
        to='someone@example.com', subject='...', category='tool_report',
        heading='...', paragraphs=['...'], cta_label='Open', cta_url='https://…',
        language='ar', related=run, metadata={'tool': 'studio_xray'},
    )
    if log.status == 'sent': ...
"""
import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives, get_connection
from django.template.loader import render_to_string
from django.utils import timezone, translation

from core.models import EmailLog

logger = logging.getLogger('bidatia')

RTL_LANGUAGES = ('ar', 'he', 'fa', 'ur')


def send_email(*, to, subject, category, recipient_name='',
               heading='', paragraphs=(), rows=(), panel=None,
               cta_label='', cta_url='', footnotes=(), footer_note='',
               cc=(), reply_to=(), language=None,
               related=None, metadata=None):
    """Render the unified template, archive the message, then send it.

    Returns the EmailLog row (status 'sent' or 'failed'); never raises.
    `rows` is a sequence of (label, value) pairs rendered as a detail table;
    `panel` is an optional {'label': ..., 'text': ...} highlight box;
    `related` is any model instance, stored as a loose string reference.
    """
    language = (language or translation.get_language() or 'en').lower()
    rtl = language.split('-')[0] in RTL_LANGUAGES

    with translation.override(language):
        context = {
            'heading': heading,
            'paragraphs': [p for p in paragraphs if p],
            'rows': list(rows),
            'panel': panel if (panel and panel.get('text')) else None,
            'cta_label': cta_label,
            'cta_url': cta_url,
            'footnotes': [n for n in footnotes if n],
            'footer_note': footer_note,
            'language': language,
            'direction': 'rtl' if rtl else 'ltr',
            'align': 'right' if rtl else 'left',
            'site_name': settings.SITE_NAME,
            'site_url': settings.SITE_BASE_URL,
            'contact_email': settings.CONTACT_EMAIL,
        }
        html_body = render_to_string('emails/base_email.html', context)
        text_body = _text_body(context)

    log = EmailLog.objects.create(
        recipient_email=to,
        recipient_name=recipient_name or '',
        subject=subject[:255],
        category=category,
        text_body=text_body,
        html_body=html_body,
        related_type=(f'{related._meta.app_label}.{related._meta.model_name}'
                      if related is not None else ''),
        related_id=str(related.pk) if related is not None else '',
        metadata={**(metadata or {}), **({'cc': list(cc)} if cc else {})},
    )

    try:
        # Admin-managed Email Settings (site_config) override the environment
        # EMAIL_* / from address when configured; otherwise these fall back to
        # the settings defaults. email_connection_kwargs() returns {} when no
        # override is active, so get_connection() uses the env backend as-is.
        from site_config import services as config

        connection = get_connection(**config.email_connection_kwargs())
        message = EmailMultiAlternatives(
            subject=subject,
            body=text_body,
            from_email=config.default_from_email(),
            to=[to],
            cc=list(cc) or None,
            reply_to=list(reply_to) or None,
            connection=connection,
        )
        message.attach_alternative(html_body, 'text/html')
        message.send()
    except Exception as exc:  # noqa: BLE001 — mail outages must never break flows
        log.status = 'failed'
        log.error_message = f'{type(exc).__name__}: {exc}'[:300]
        log.save(update_fields=['status', 'error_message'])
        logger.warning('email send failed (category=%s, log=%s, error=%s)',
                       category, log.pk, type(exc).__name__)
        return log

    log.status = 'sent'
    log.sent_at = timezone.now()
    log.save(update_fields=['status', 'sent_at'])
    return log


def _text_body(context):
    """Plain-text twin of the HTML message, built from the same pieces.
    str() everywhere: callers may pass lazy translation proxies."""
    lines = []
    if context['heading']:
        lines += [str(context['heading']), '']
    for paragraph in context['paragraphs']:
        lines += [str(paragraph), '']
    if context['rows']:
        lines += [f'{label}: {value}' for label, value in context['rows']]
        lines.append('')
    if context['panel']:
        if context['panel'].get('label'):
            lines.append(f"{context['panel']['label']}:")
        lines += [str(context['panel']['text']), '']
    if context['cta_url']:
        label = context['cta_label'] or context['cta_url']
        lines += [f"{label}:", context['cta_url'], '']
    for note in context['footnotes']:
        lines += [str(note), '']
    lines.append(f"— {context['site_name']}")
    return '\n'.join(lines)
