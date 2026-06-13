from datetime import date as date_cls
from datetime import datetime, timedelta

from django import forms
from django.utils.translation import gettext_lazy as _

from core.form_styles import (
    CHECKBOX_CLASSES,
    SELECT_CLASSES,
    TEXT_INPUT_CLASSES,
    TEXTAREA_CLASSES,
)

from .models import (
    CONSULTATION_TYPE_CHOICES,
    DEFAULT_TIMEZONE,
    AvailabilitySlot,
    ConsultationRequest,
)


class ConsultationRequestForm(forms.ModelForm):
    # The slot is chosen via the visual step-2 picker, which sets this hidden
    # input. ``required=False`` keeps the form usable as a plain enquiry form
    # if no slots are available; availability is validated in ``clean``.
    slot = forms.ModelChoiceField(
        queryset=AvailabilitySlot.objects.all(),
        required=False,
        widget=forms.HiddenInput(),
    )

    class Meta:
        model = ConsultationRequest
        fields = [
            'full_name', 'company_name', 'email', 'phone', 'country',
            'preferred_language', 'consultation_type', 'odoo_version',
            'problem_summary', 'preferred_datetime', 'slot', 'consent',
        ]
        widgets = {
            'full_name': forms.TextInput(attrs={'class': TEXT_INPUT_CLASSES, 'placeholder': _('Jane Doe')}),
            'company_name': forms.TextInput(attrs={'class': TEXT_INPUT_CLASSES, 'placeholder': _('Acme S.L. (optional)')}),
            # email/phone are technical tokens: force LTR so they read correctly on the Arabic (RTL) page.
            'email': forms.EmailInput(attrs={'class': TEXT_INPUT_CLASSES, 'placeholder': 'jane@company.com', 'dir': 'ltr'}),
            'phone': forms.TextInput(attrs={'class': TEXT_INPUT_CLASSES, 'placeholder': '612 345 678', 'dir': 'ltr', 'autocomplete': 'tel'}),
            'country': forms.TextInput(attrs={'class': TEXT_INPUT_CLASSES, 'placeholder': _('Spain')}),
            'preferred_language': forms.Select(attrs={'class': SELECT_CLASSES}),
            'consultation_type': forms.Select(attrs={'class': SELECT_CLASSES}),
            'odoo_version': forms.TextInput(attrs={'class': TEXT_INPUT_CLASSES, 'placeholder': _('e.g. Odoo 17 (or "not sure")')}),
            'problem_summary': forms.Textarea(attrs={
                'class': TEXTAREA_CLASSES,
                'placeholder': _('Briefly describe what is going wrong, what you need, or what you would like to achieve.'),
            }),
            'preferred_datetime': forms.TextInput(attrs={
                'class': TEXT_INPUT_CLASSES,
                'placeholder': _('e.g. Weekday afternoons, Madrid time (CET)'),
            }),
            'consent': forms.CheckboxInput(attrs={'class': CHECKBOX_CLASSES}),
        }
        labels = {
            'full_name': _('Full name'),
            'company_name': _('Company name'),
            'email': _('Email'),
            'phone': _('Phone / WhatsApp'),
            'country': _('Country'),
            'preferred_language': _('Preferred language'),
            'consultation_type': _('Which service are you interested in?'),
            'odoo_version': _('Odoo version'),
            'problem_summary': _('Tell us about your situation'),
            'preferred_datetime': _('Preferred date / time'),
            'consent': _('I agree that Bidatia may contact me about this request by email, phone or WhatsApp.'),
        }

    def clean_consent(self):
        consent = self.cleaned_data.get('consent')
        if not consent:
            raise forms.ValidationError(_('Please confirm you agree to be contacted so we can follow up on your request.'))
        return consent

    def clean_slot(self):
        slot = self.cleaned_data.get('slot')
        if slot and not slot.is_available:
            raise forms.ValidationError(
                _('Sorry, that time slot is no longer available. Please choose another one.')
            )
        return slot

    def clean(self):
        cleaned = super().clean()
        slot = cleaned.get('slot')
        consultation_type = cleaned.get('consultation_type')
        # Keep the chosen slot consistent with the chosen consultation type.
        if slot and consultation_type and slot.consultation_type != consultation_type:
            self.add_error(
                'slot',
                _('The selected time slot does not match the chosen consultation type.'),
            )
        return cleaned


WEEKDAY_CHOICES = [
    ('0', _('Monday')),
    ('1', _('Tuesday')),
    ('2', _('Wednesday')),
    ('3', _('Thursday')),
    ('4', _('Friday')),
    ('5', _('Saturday')),
    ('6', _('Sunday')),
]

_BASE_DAY = date_cls(2000, 1, 1)


class SlotGeneratorForm(forms.Form):
    """Staff form that bulk-generates AvailabilitySlot rows across a date range,
    selected weekdays and a daily time window. Duplicates (same consultation
    type + date + start time) are skipped automatically."""

    consultation_type = forms.ChoiceField(
        choices=CONSULTATION_TYPE_CHOICES,
        label=_('Consultation type'),
    )
    start_date = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date'}),
        label=_('Start date'),
    )
    end_date = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date'}),
        label=_('End date'),
    )
    weekdays = forms.MultipleChoiceField(
        choices=WEEKDAY_CHOICES,
        widget=forms.CheckboxSelectMultiple,
        label=_('Days of the week'),
        help_text=_('Only the selected weekdays in the range get slots.'),
    )
    start_time = forms.TimeField(
        widget=forms.TimeInput(attrs={'type': 'time'}),
        label=_('Start time'),
    )
    end_time = forms.TimeField(
        widget=forms.TimeInput(attrs={'type': 'time'}),
        label=_('End time'),
    )
    slot_minutes = forms.IntegerField(
        min_value=5, initial=30, label=_('Slot duration (minutes)'),
    )
    gap_minutes = forms.IntegerField(
        min_value=0, initial=0, required=False,
        label=_('Break between slots (minutes)'),
    )
    timezone = forms.CharField(
        initial=DEFAULT_TIMEZONE, required=False, label=_('Timezone'),
    )
    is_active = forms.BooleanField(
        initial=True, required=False,
        label=_('Mark generated slots as active'),
    )

    def clean(self):
        cleaned = super().clean()
        start_date = cleaned.get('start_date')
        end_date = cleaned.get('end_date')
        start_time = cleaned.get('start_time')
        end_time = cleaned.get('end_time')
        slot_minutes = cleaned.get('slot_minutes')

        if start_date and end_date and end_date < start_date:
            self.add_error('end_date', _('End date must be on or after the start date.'))
        if start_time and end_time and end_time <= start_time:
            self.add_error('end_time', _('End time must be after the start time.'))
        if start_time and end_time and slot_minutes:
            window = (datetime.combine(_BASE_DAY, end_time)
                      - datetime.combine(_BASE_DAY, start_time))
            if timedelta(minutes=slot_minutes) > window:
                self.add_error(
                    'slot_minutes',
                    _('Slot duration is longer than the daily time window.'),
                )
        return cleaned

    def _time_windows(self):
        """List of (start_time, end_time) slot windows within one day."""
        slot = timedelta(minutes=self.cleaned_data['slot_minutes'])
        gap = timedelta(minutes=self.cleaned_data.get('gap_minutes') or 0)
        cursor = datetime.combine(_BASE_DAY, self.cleaned_data['start_time'])
        day_end = datetime.combine(_BASE_DAY, self.cleaned_data['end_time'])
        windows = []
        while cursor + slot <= day_end:
            windows.append((cursor.time(), (cursor + slot).time()))
            cursor = cursor + slot + gap
        return windows

    def _dates(self):
        """Dates in the range whose weekday is selected."""
        wanted = {int(d) for d in self.cleaned_data['weekdays']}
        dates = []
        current = self.cleaned_data['start_date']
        end = self.cleaned_data['end_date']
        while current <= end:
            if current.weekday() in wanted:
                dates.append(current)
            current += timedelta(days=1)
        return dates

    def generate(self):
        """Create the slots. Returns (created_count, skipped_count)."""
        consultation_type = self.cleaned_data['consultation_type']
        tz = self.cleaned_data.get('timezone') or DEFAULT_TIMEZONE
        is_active = bool(self.cleaned_data.get('is_active'))

        windows = self._time_windows()
        dates = self._dates()
        candidates = [(d, start, end) for d in dates for (start, end) in windows]

        existing = set(
            AvailabilitySlot.objects.filter(
                consultation_type=consultation_type, date__in=dates,
            ).values_list('date', 'start_time')
        )
        new_slots = [
            AvailabilitySlot(
                consultation_type=consultation_type,
                date=d, start_time=start, end_time=end,
                timezone=tz, is_active=is_active,
            )
            for (d, start, end) in candidates if (d, start) not in existing
        ]
        # ignore_conflicts guards against the unique constraint under any race.
        AvailabilitySlot.objects.bulk_create(new_slots, ignore_conflicts=True)
        created = len(new_slots)
        return created, len(candidates) - created
