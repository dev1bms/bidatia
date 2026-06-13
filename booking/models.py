from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

# Shared across ConsultationRequest and AvailabilitySlot so a slot is always
# tied to a specific kind of session.
CONSULTATION_TYPE_CHOICES = [
    ('intro_call', _('Free 20-minute Intro Call')),
    ('paid_consultation', _('Paid Odoo Consultation')),
    ('health_check', _('Odoo Health Check')),
    ('monthly_support', _('Monthly Odoo Support')),
    ('studio_cleanup', _('Odoo Studio Cleanup')),
    ('migration_assessment', _('Odoo Migration Assessment')),
    ('custom_module', _('Custom Odoo Module Development')),
    ('integration', _('Django ↔ Odoo Integration')),
    ('other', _('Other / Not sure yet')),
]

# The four consultation types offered as bookable slots in the public flow.
BOOKABLE_CONSULTATION_TYPES = [
    'intro_call', 'paid_consultation', 'health_check', 'monthly_support',
]

# Consultation types that require payment before the booking is confirmed.
PAID_CONSULTATION_TYPES = {'paid_consultation', 'health_check'}

DEFAULT_TIMEZONE = 'Europe/Madrid'


class AvailabilitySlot(models.Model):
    """A bookable date/time window for a given consultation type.

    Times are stored as plain date/time values interpreted in ``timezone``
    (Madrid by default). A slot is offered publicly only while it is active,
    not yet booked, and still in the future.
    """

    consultation_type = models.CharField(max_length=30, choices=CONSULTATION_TYPE_CHOICES)
    date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    timezone = models.CharField(max_length=64, default=DEFAULT_TIMEZONE)
    is_active = models.BooleanField(default=True)
    is_booked = models.BooleanField(default=False)
    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['date', 'start_time']
        verbose_name = 'Availability slot'
        constraints = [
            models.UniqueConstraint(
                fields=['consultation_type', 'date', 'start_time'],
                name='unique_slot_per_type_date_start',
            ),
        ]

    def __str__(self):
        return f'{self.get_consultation_type_display()} — {self.date} {self.start_time:%H:%M}'

    @property
    def is_past(self):
        return self.date < timezone.localdate()

    @property
    def is_available(self):
        return self.is_active and not self.is_booked and not self.is_past


class ConsultationRequest(models.Model):
    CONSULTATION_TYPE_CHOICES = CONSULTATION_TYPE_CHOICES

    LANGUAGE_CHOICES = [
        ('en', _('English')),
        ('es', _('Spanish')),
        ('ar', _('Arabic')),
    ]

    STATUS_CHOICES = [
        ('new', 'New'),
        ('contacted', 'Contacted'),
        ('scheduled', 'Scheduled'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]

    full_name = models.CharField(max_length=120)
    company_name = models.CharField(max_length=150, blank=True)
    email = models.EmailField()
    phone = models.CharField('Phone / WhatsApp', max_length=40)
    country = models.CharField(max_length=80)
    preferred_language = models.CharField(max_length=5, choices=LANGUAGE_CHOICES, default='en')
    consultation_type = models.CharField(max_length=30, choices=CONSULTATION_TYPE_CHOICES)
    odoo_version = models.CharField('Odoo version', max_length=40, blank=True)
    problem_summary = models.TextField('Problem summary')
    preferred_datetime = models.CharField(
        'Preferred date / time',
        max_length=120,
        blank=True,
        help_text='Free text, e.g. "Weekday afternoons (Madrid time)". Optional when a slot is selected.',
    )
    slot = models.ForeignKey(
        AvailabilitySlot,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='requests',
        help_text='The availability slot the customer reserved, if any.',
    )
    consent = models.BooleanField(
        'I agree to be contacted about this request',
        default=False,
    )

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='new')
    internal_notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Consultation request'

    def __str__(self):
        return f'{self.full_name} — {self.get_consultation_type_display()}'

    @property
    def is_paid(self):
        return self.consultation_type in PAID_CONSULTATION_TYPES
