import json
from collections import OrderedDict, defaultdict

from django.db import transaction
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.formats import date_format
from django.utils.translation import gettext as _

from jobs.services import create_task

from .forms import ConsultationRequestForm
from .models import (
    BOOKABLE_CONSULTATION_TYPES,
    CONSULTATION_TYPE_CHOICES,
    DEFAULT_TIMEZONE,
    PAID_CONSULTATION_TYPES,
    AvailabilitySlot,
)

def _dispatch_consultation_notification(request, consultation):
    """Queue the booking notification email off the request path; return a
    BackgroundTask the success page can poll. Inline fallback if broker is down."""
    from core.tasks import send_consultation_notification

    if not request.session.session_key:
        request.session.save()
    task = create_task(
        task_type='booking_email',
        title=_('Submitting your booking request…'),
        session_key=request.session.session_key,
    )
    lang = getattr(request, 'LANGUAGE_CODE', 'en') or 'en'
    try:
        send_consultation_notification.delay(consultation.pk, str(task.pk), lang)
    except Exception:  # noqa: BLE001 — broker down: deliver inline, still non-fatal
        send_consultation_notification(consultation.pk, str(task.pk), lang)
    return task


# Maps service detail-page slugs to a consultation type, so links like
# /book-consultation/?service=odoo-health-check pre-select the right option.
SERVICE_SLUG_TO_TYPE = {
    'paid-odoo-consultation': 'paid_consultation',
    'odoo-health-check': 'health_check',
    'odoo-studio-cleanup': 'studio_cleanup',
    'odoo-migration-assessment': 'migration_assessment',
    'custom-odoo-module-development': 'custom_module',
    'django-odoo-integration': 'integration',
    'monthly-odoo-support': 'monthly_support',
}


class _SlotUnavailable(Exception):
    """Raised when a slot can no longer be claimed (already booked)."""


def _type_meta():
    """Short, translatable marketing metadata for each bookable type.

    Built per request so strings are translated in the active language.
    """
    return {
        'intro_call': {
            'price': _('Free'),
            'duration': _('20 minutes'),
            'desc': _('A quick introductory call to understand your needs and see if we are a good fit.'),
        },
        'paid_consultation': {
            'price': _('From €49'),
            'duration': _('45 minutes'),
            'desc': _('A focused, paid technical session to get expert answers on your Odoo questions.'),
        },
        'health_check': {
            'price': _('Discovery'),
            'duration': _('45 minutes'),
            'desc': _('A discovery call to scope a full technical audit of your Odoo system.'),
        },
        'monthly_support': {
            'price': _('Free'),
            'duration': _('30 minutes'),
            'desc': _('A call to discuss an ongoing monthly support arrangement for your Odoo setup.'),
        },
    }


def _build_types_payload():
    """Return a JSON-serializable list describing each bookable consultation
    type and its available, future, unbooked slots (grouped by day)."""
    type_labels = dict(CONSULTATION_TYPE_CHOICES)
    meta = _type_meta()

    today = timezone.localdate()
    slots = AvailabilitySlot.objects.filter(
        is_active=True,
        is_booked=False,
        date__gte=today,
        consultation_type__in=BOOKABLE_CONSULTATION_TYPES,
    ).order_by('date', 'start_time')

    by_type = defaultdict(OrderedDict)
    for slot in slots:
        by_type[slot.consultation_type].setdefault(slot.date, []).append(slot)

    payload = []
    for ct in BOOKABLE_CONSULTATION_TYPES:
        days = []
        slot_count = 0
        for day, day_slots in by_type.get(ct, {}).items():
            slot_count += len(day_slots)
            days.append({
                'date': day.isoformat(),
                'label': date_format(day, 'l, j F'),
                'slots': [
                    {
                        'id': s.id,
                        'label': f'{s.start_time:%H:%M}\u2013{s.end_time:%H:%M}',
                        'start': f'{s.start_time:%H:%M}',
                    }
                    for s in day_slots
                ],
            })
        type_meta = meta.get(ct, {})
        payload.append({
            'key': ct,
            'label': str(type_labels.get(ct, ct)),
            'price': str(type_meta.get('price', '')),
            'duration': str(type_meta.get('duration', '')),
            'desc': str(type_meta.get('desc', '')),
            'paid': ct in PAID_CONSULTATION_TYPES,
            'slot_count': slot_count,
            'days': days,
        })
    return payload


def book_consultation(request):
    initial = {}
    # Generic one-shot prefill handoff from the free tools (e.g. the Studio
    # X-Ray report's "book this review" flow): identity, Odoo version and a
    # suggested agenda arrive via the session and are consumed here.
    prefill = request.session.pop('booking_prefill', None)
    if isinstance(prefill, dict):
        initial.update(prefill)
    service_slug = request.GET.get('service')
    preselect_type = SERVICE_SLUG_TO_TYPE.get(service_slug, '')
    if preselect_type:
        initial['consultation_type'] = preselect_type

    if request.method == 'POST':
        form = ConsultationRequestForm(request.POST)
        if form.is_valid():
            slot = form.cleaned_data.get('slot')
            try:
                with transaction.atomic():
                    consultation = form.save(commit=False)
                    if slot is not None:
                        # Atomically claim the slot: the conditional UPDATE only
                        # succeeds for one request, so the same active slot can
                        # never be booked twice even under concurrency.
                        claimed = AvailabilitySlot.objects.filter(
                            pk=slot.pk, is_active=True, is_booked=False,
                        ).update(is_booked=True, updated_at=timezone.now())
                        if not claimed:
                            raise _SlotUnavailable
                        consultation.slot = slot
                    consultation.save()
            except _SlotUnavailable:
                form.add_error(
                    'slot',
                    _('Sorry, that time slot was just booked by someone else. Please choose another one.'),
                )
            else:
                # Request is safely saved; the notification email is delivered
                # in the background so the browser gets an instant response.
                task = _dispatch_consultation_notification(request, consultation)
                request.session['booking_is_paid'] = bool(consultation.is_paid)
                request.session['booking_task_id'] = str(task.pk)
                return redirect('booking:booking_success')
    else:
        form = ConsultationRequestForm(initial=initial)

    types_payload = _build_types_payload()
    # Auto-detect the visitor's country for the phone field from Cloudflare's
    # CF-IPCountry header (set at the edge / forwarded by the tunnel). Falls back
    # to Spain when the header is absent or not a real country (XX, T1).
    cf_country = (request.META.get('HTTP_CF_IPCOUNTRY') or '').lower()
    phone_country = cf_country if (
        len(cf_country) == 2 and cf_country.isalpha() and cf_country not in ('xx', 't1')
    ) else 'es'
    context = {
        'form': form,
        'phone_country': phone_country,
        'types_payload': types_payload,
        'types_json': json.dumps(types_payload),
        'has_slots': any(t['days'] for t in types_payload),
        'preselect_type': preselect_type if preselect_type in BOOKABLE_CONSULTATION_TYPES else '',
        'booking_timezone': DEFAULT_TIMEZONE,
        'meta_description': _(
            'Book an Odoo consultation with BidERP in Madrid: choose a consultation type, '
            'pick an available time slot (Madrid time), and tell us about your ERP challenge.'
        ),
    }
    return render(request, 'booking/book_consultation.html', context)


def booking_success(request):
    is_paid = request.session.pop('booking_is_paid', False)
    task_id = request.session.pop('booking_task_id', None)
    return render(request, 'booking/booking_success.html', {
        'is_paid': is_paid,
        'task_id': task_id,
        'meta_description': _('Your consultation request has been received by BidERP.'),
    })
