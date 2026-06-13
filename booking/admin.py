import calendar as pycalendar
from collections import defaultdict
from datetime import date as date_cls
from datetime import timedelta

from django.contrib import admin, messages
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils import timezone
from django.utils.formats import date_format
from django.utils.html import format_html
from unfold.admin import ModelAdmin
from unfold.decorators import action, display

from .forms import SlotGeneratorForm
from .models import CONSULTATION_TYPE_CHOICES, AvailabilitySlot, ConsultationRequest


def _slot_status(slot):
    """Status keyword used to colour-code a slot in the calendar."""
    if slot.is_booked:
        return 'booked'
    if not slot.is_active:
        return 'inactive'
    if slot.is_past:
        return 'past'
    return 'available'


@admin.register(AvailabilitySlot)
class AvailabilitySlotAdmin(ModelAdmin):
    # Cleaner changelist: one row per slot, but each row scannable at a glance —
    # date + weekday, a single time range, the readable type name, and one
    # colour-coded status pill instead of separate is_active / is_booked columns.
    list_display = ('slot_when', 'slot_time', 'type_label', 'status_label', 'booked_by')
    list_display_links = ('slot_when',)
    list_filter = ('consultation_type', 'is_active', 'is_booked', 'date')
    list_filter_submit = True
    list_per_page = 50
    search_fields = ('notes',)
    date_hierarchy = 'date'
    ordering = ('date', 'start_time')
    readonly_fields = ('created_at', 'updated_at', 'booked_by')
    actions = ('mark_available', 'mark_unavailable', 'delete_unbooked_future')
    # Unfold: buttons at the top of the changelist.
    actions_list = ('calendar_view', 'generate_slots_view')
    fieldsets = (
        ('Slot', {
            'fields': ('consultation_type', 'date', 'start_time', 'end_time', 'timezone'),
        }),
        ('Status', {
            'fields': ('is_active', 'is_booked', 'booked_by', 'notes'),
        }),
        ('Timestamps', {
            'classes': ('collapse',),
            'fields': ('created_at', 'updated_at'),
        }),
    )

    @display(description='When', header=True, ordering='date')
    def slot_when(self, obj):
        # Two-line cell: date on top, weekday underneath.
        return [date_format(obj.date, 'j M Y'), date_format(obj.date, 'l')]

    @display(description='Time', ordering='start_time')
    def slot_time(self, obj):
        return format_html(
            '<span dir="ltr">{}–{}</span>',
            obj.start_time.strftime('%H:%M'), obj.end_time.strftime('%H:%M'),
        )

    @display(description='Type', ordering='consultation_type')
    def type_label(self, obj):
        return obj.get_consultation_type_display()

    @display(description='Status', label={
        'Available': 'success',
        'Booked': 'info',
        'Past': 'warning',
    })
    def status_label(self, obj):
        if obj.is_booked:
            return 'Booked'
        if not obj.is_active:
            return 'Inactive'   # not in label map -> neutral/grey pill
        if obj.is_past:
            return 'Past'
        return 'Available'

    @admin.display(description='Booked by')
    def booked_by(self, obj):
        request = obj.requests.order_by('created_at').first()
        if not request:
            return '—'
        url = reverse('admin:booking_consultationrequest_change', args=[request.pk])
        return format_html('<a href="{}">{}</a>', url, request.full_name)

    # ── Bulk slot generator (Unfold actions_list button) ──────────────────────
    @action(description='Generate slots', url_path='generate-slots', permissions=['add'])
    def generate_slots_view(self, request):
        """Staff view to bulk-create AvailabilitySlot rows across a date range,
        weekdays and a daily time window. Skips existing slots automatically."""
        if request.method == 'POST':
            form = SlotGeneratorForm(request.POST)
            if form.is_valid():
                created, skipped = form.generate()
                self.message_user(
                    request,
                    f'{created} slot(s) created, {skipped} skipped because they already existed.',
                    level=messages.SUCCESS,
                )
                return redirect('admin:booking_availabilityslot_changelist')
        else:
            # Pre-fill from query params (e.g. the "+ add" link in the calendar).
            initial = {}
            for key in ('consultation_type', 'start_date', 'end_date', 'start_time', 'end_time'):
                if request.GET.get(key):
                    initial[key] = request.GET[key]
            weekdays = request.GET.getlist('weekdays')
            if weekdays:
                initial['weekdays'] = weekdays
            form = SlotGeneratorForm(initial=initial)
        context = {
            **self.admin_site.each_context(request),
            'title': 'Generate availability slots',
            'form': form,
            'opts': self.model._meta,
        }
        return TemplateResponse(request, 'admin/booking/generate_slots.html', context)

    @action(description='Calendar view', url_path='calendar', permissions=['view'])
    def calendar_view(self, request):
        """Read-only month/week calendar of slots, colour-coded by status.
        Server-rendered (no JS dependency); each slot links to its edit page."""
        from urllib.parse import urlencode

        today = timezone.localdate()
        view = request.GET.get('view', 'month')
        if view not in ('month', 'week'):
            view = 'month'
        type_filter = request.GET.get('type') or ''
        type_labels = dict(CONSULTATION_TYPE_CHOICES)
        counts = {'total': 0, 'available': 0, 'booked': 0, 'past': 0, 'inactive': 0}
        changelist_url = reverse('admin:booking_availabilityslot_changelist')

        def card(slot):
            return {
                'status': _slot_status(slot),
                'time': f'{slot.start_time:%H:%M}',
                'end': f'{slot.end_time:%H:%M}',
                'type': type_labels.get(slot.consultation_type, slot.consultation_type),
                'url': reverse('admin:booking_availabilityslot_change', args=[slot.pk]),
            }

        def q(**params):
            return '?' + urlencode({k: v for k, v in params.items() if v not in (None, '')})

        context = {
            **self.admin_site.each_context(request),
            'title': 'Availability calendar',
            'opts': self.model._meta,
            'view': view,
            'type_filter': type_filter,
            'type_choices': CONSULTATION_TYPE_CHOICES,
            'changelist_url': changelist_url,
            'generate_url': changelist_url + 'generate-slots/',
        }

        if view == 'week':
            try:
                ref = date_cls.fromisoformat(request.GET.get('date', ''))
            except ValueError:
                ref = today
            week_start = ref - timedelta(days=ref.weekday())
            week_end = week_start + timedelta(days=6)
            slots = AvailabilitySlot.objects.filter(date__range=(week_start, week_end))
            if type_filter:
                slots = slots.filter(consultation_type=type_filter)

            by_day_hour = defaultdict(list)
            min_h, max_h = 23, 0
            for slot in slots.order_by('start_time'):
                counts[_slot_status(slot)] += 1
                counts['total'] += 1
                by_day_hour[(slot.date, slot.start_time.hour)].append(card(slot))
                min_h = min(min_h, slot.start_time.hour)
                max_h = max(max_h, slot.end_time.hour + (1 if slot.end_time.minute else 0))
            if counts['total'] == 0:
                min_h, max_h = 8, 20
            max_h = min(24, max(max_h, min_h + 1))

            week_days = [
                {
                    'label': date_format(week_start + timedelta(days=i), 'D j'),
                    'iso': (week_start + timedelta(days=i)).isoformat(),
                    'weekday': (week_start + timedelta(days=i)).weekday(),
                    'is_today': (week_start + timedelta(days=i)) == today,
                }
                for i in range(7)
            ]
            rows = [
                {
                    'hour': f'{h:02d}:00',
                    'cells': [by_day_hour.get((week_start + timedelta(days=i), h), []) for i in range(7)],
                }
                for h in range(min_h, max_h)
            ]
            context.update({
                'week_days': week_days,
                'rows': rows,
                'counts': counts,
                'label': f'{date_format(week_start, "j M")} – {date_format(week_end, "j M Y")}',
                'filter_params': {'view': 'week', 'date': week_start.isoformat()},
                'nav': {
                    'prev': q(view='week', date=(week_start - timedelta(days=7)).isoformat(), type=type_filter),
                    'next': q(view='week', date=(week_start + timedelta(days=7)).isoformat(), type=type_filter),
                    'today': q(view='week', date=today.isoformat(), type=type_filter),
                },
                'toggle': {
                    'month': q(view='month', year=week_start.year, month=week_start.month, type=type_filter),
                    'week': q(view='week', date=week_start.isoformat(), type=type_filter),
                },
            })
            return TemplateResponse(request, 'admin/booking/slots_calendar.html', context)

        # ── month view ──
        try:
            year = int(request.GET.get('year', today.year))
            month = int(request.GET.get('month', today.month))
            date_cls(year, month, 1)  # validate
        except (TypeError, ValueError):
            year, month = today.year, today.month

        slots = AvailabilitySlot.objects.filter(date__year=year, date__month=month)
        if type_filter:
            slots = slots.filter(consultation_type=type_filter)
        by_day = defaultdict(list)
        for slot in slots.order_by('start_time'):
            counts[_slot_status(slot)] += 1
            counts['total'] += 1
            by_day[slot.date.day].append(card(slot))

        weeks = [
            [
                {
                    'day': d.day,
                    'iso': d.isoformat(),
                    'weekday': d.weekday(),
                    'in_month': d.month == month,
                    'is_today': d == today,
                    'slots': by_day.get(d.day, []) if d.month == month else [],
                }
                for d in week
            ]
            for week in pycalendar.Calendar(firstweekday=0).monthdatescalendar(year, month)
        ]
        monday = date_cls(2024, 1, 1)  # a Monday
        weekday_headers = [date_format(monday + timedelta(days=i), 'D') for i in range(7)]
        first = date_cls(year, month, 1)
        prev_m = first - timedelta(days=1)
        next_m = (first + timedelta(days=32)).replace(day=1)
        context.update({
            'weeks': weeks,
            'weekday_headers': weekday_headers,
            'label': date_format(first, 'F Y'),
            'counts': counts,
            'filter_params': {'view': 'month', 'year': year, 'month': month},
            'nav': {
                'prev': q(view='month', year=prev_m.year, month=prev_m.month, type=type_filter),
                'next': q(view='month', year=next_m.year, month=next_m.month, type=type_filter),
                'today': q(view='month', year=today.year, month=today.month, type=type_filter),
            },
            'toggle': {
                'month': q(view='month', year=year, month=month, type=type_filter),
                'week': q(view='week', date=first.isoformat(), type=type_filter),
            },
        })
        return TemplateResponse(request, 'admin/booking/slots_calendar.html', context)

    # ── Bulk admin actions ────────────────────────────────────────────────────
    @admin.action(description='Mark selected slots as available (active)')
    def mark_available(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f'{updated} slot(s) marked as available.')

    @admin.action(description='Mark selected slots as unavailable (inactive)')
    def mark_unavailable(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f'{updated} slot(s) marked as unavailable.')

    @admin.action(description='Delete selected unbooked future slots')
    def delete_unbooked_future(self, request, queryset):
        # Safety: never delete booked slots or past slots.
        today = timezone.localdate()
        deletable = queryset.filter(is_booked=False, date__gte=today)
        count = deletable.count()
        deletable.delete()
        self.message_user(
            request,
            f'{count} unbooked future slot(s) deleted. Booked or past slots were left untouched.',
        )


@admin.register(ConsultationRequest)
class ConsultationRequestAdmin(ModelAdmin):
    list_display = (
        'full_name', 'company_name', 'email', 'consultation_type',
        'slot', 'preferred_language', 'is_paid_badge', 'status', 'created_at',
    )
    list_display_links = ('full_name',)
    list_editable = ('status',)
    list_filter = ('status', 'consultation_type', 'preferred_language', 'created_at')
    search_fields = ('full_name', 'company_name', 'email', 'phone', 'problem_summary')
    list_select_related = ('slot',)
    raw_id_fields = ('slot',)
    date_hierarchy = 'created_at'
    ordering = ('-created_at',)
    readonly_fields = ('created_at', 'updated_at')
    actions = ('mark_contacted', 'mark_scheduled', 'mark_completed')
    fieldsets = (
        ('Contact', {
            'fields': ('full_name', 'company_name', 'email', 'phone', 'country', 'preferred_language'),
        }),
        ('Request details', {
            'fields': ('consultation_type', 'slot', 'odoo_version', 'problem_summary',
                       'preferred_datetime', 'consent'),
        }),
        ('Internal', {
            'fields': ('status', 'internal_notes', 'created_at', 'updated_at'),
        }),
    )

    @admin.display(description='Paid', boolean=True)
    def is_paid_badge(self, obj):
        return obj.is_paid

    @admin.action(description='Mark selected as contacted')
    def mark_contacted(self, request, queryset):
        updated = queryset.update(status='contacted')
        self.message_user(request, f'{updated} request(s) marked as contacted.')

    @admin.action(description='Mark selected as scheduled')
    def mark_scheduled(self, request, queryset):
        updated = queryset.update(status='scheduled')
        self.message_user(request, f'{updated} request(s) marked as scheduled.')

    @admin.action(description='Mark selected as completed')
    def mark_completed(self, request, queryset):
        updated = queryset.update(status='completed')
        self.message_user(request, f'{updated} request(s) marked as completed.')
