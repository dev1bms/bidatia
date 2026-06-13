from django import forms
from django.utils.translation import gettext_lazy as _

from core.form_styles import CHECKBOX_CLASSES, TEXT_INPUT_CLASSES

SELECT_CLASSES = TEXT_INPUT_CLASSES


class RescueCheckForm(forms.Form):
    """Lead-capture part of the ERP Rescue Check. The 24 answers travel as
    plain q_<code> radio fields and are validated in the view against the
    checklist catalog (they are not personal data)."""

    ERP_CHOICES = [
        ('odoo', _('Odoo')),
        ('other', _('Another ERP (SAP, Dynamics, NetSuite, custom…)')),
        ('unknown', _("I'm not sure")),
    ]

    email = forms.EmailField(
        label=_('Your email'),
        help_text=_('Your full results and rescue plan will be sent here.'),
        widget=forms.EmailInput(attrs={
            'class': TEXT_INPUT_CLASSES + ' force-ltr',
            'placeholder': 'you@company.com', 'autocomplete': 'email',
        }),
    )
    full_name = forms.CharField(
        label=_('Full name'), required=False,
        widget=forms.TextInput(attrs={'class': TEXT_INPUT_CLASSES, 'autocomplete': 'name'}),
    )
    company = forms.CharField(
        label=_('Company'), required=False,
        widget=forms.TextInput(attrs={'class': TEXT_INPUT_CLASSES, 'autocomplete': 'organization'}),
    )
    erp_type = forms.ChoiceField(
        label=_('Which ERP do you use?'), choices=ERP_CHOICES, initial='odoo',
        widget=forms.Select(attrs={'class': SELECT_CLASSES}),
    )
    pain_text = forms.CharField(
        label=_('What hurts most in your ERP today? Two sentences are enough.'),
        required=False, max_length=400,
        widget=forms.Textarea(attrs={
            'class': TEXT_INPUT_CLASSES, 'rows': 2,
            'placeholder': _('In your own words — this makes your reading sharper.'),
        }),
    )
    consent = forms.BooleanField(
        label=_('Email me my results and contact me about them. I agree to the processing of the data I submitted for this purpose.'),
        widget=forms.CheckboxInput(attrs={'class': CHECKBOX_CLASSES}),
    )

    # Honeypot — hidden from humans by CSS; bots fill it.
    website = forms.CharField(required=False, widget=forms.HiddenInput())

    def is_bot(self):
        return bool(self.data.get('website'))
