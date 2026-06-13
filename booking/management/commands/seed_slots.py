"""Seed future AvailabilitySlot rows for local testing of the booking flow.

Idempotent: slots are matched on (consultation_type, date, start_time) — the
same unique constraint used by the model — so running the command repeatedly
never creates duplicates.

Usage:
    python manage.py seed_slots               # next ~3 weeks of weekday slots
    python manage.py seed_slots --weeks 4      # customise the horizon
"""
import datetime

from django.core.management.base import BaseCommand
from django.utils import timezone

from booking.models import DEFAULT_TIMEZONE, AvailabilitySlot

# (consultation_type, start_time, end_time, weekdays) where weekdays is a set of
# Python weekday() integers (Mon=0 .. Sun=6). Times are Madrid local time.
SLOT_TEMPLATES = [
    ('intro_call', datetime.time(10, 0), datetime.time(10, 20), {0, 1, 2, 3, 4}),
    ('intro_call', datetime.time(16, 0), datetime.time(16, 20), {0, 2, 4}),
    ('paid_consultation', datetime.time(11, 0), datetime.time(11, 45), {1, 3}),
    ('paid_consultation', datetime.time(15, 0), datetime.time(15, 45), {0, 2}),
    ('health_check', datetime.time(12, 0), datetime.time(12, 45), {1, 3}),
    ('monthly_support', datetime.time(17, 0), datetime.time(17, 30), {2}),
]


class Command(BaseCommand):
    help = 'Create future availability slots for the booking flow (idempotent).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--weeks', type=int, default=3,
            help='How many weeks ahead to generate slots for (default: 3).',
        )

    def handle(self, *args, **options):
        weeks = max(1, options['weeks'])
        start = timezone.localdate() + datetime.timedelta(days=1)
        created = existing = 0

        for offset in range(weeks * 7):
            day = start + datetime.timedelta(days=offset)
            for ctype, start_time, end_time, weekdays in SLOT_TEMPLATES:
                if day.weekday() not in weekdays:
                    continue
                _, was_created = AvailabilitySlot.objects.get_or_create(
                    consultation_type=ctype,
                    date=day,
                    start_time=start_time,
                    defaults={
                        'end_time': end_time,
                        'timezone': DEFAULT_TIMEZONE,
                        'is_active': True,
                        'is_booked': False,
                    },
                )
                if was_created:
                    created += 1
                else:
                    existing += 1

        self.stdout.write(self.style.SUCCESS(
            f'Availability slots ready: {created} created, {existing} already existed '
            f'({DEFAULT_TIMEZONE}, next {weeks} week(s)).'
        ))
