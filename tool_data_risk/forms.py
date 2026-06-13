from django import forms
from django.utils.translation import gettext_lazy as _

from core.form_styles import CHECKBOX_CLASSES, TEXT_INPUT_CLASSES

# Connection fields hold technical LTR content — keep them LTR on RTL pages.
LTR_INPUT = TEXT_INPUT_CLASSES + ' force-ltr'


class DataRiskRunForm(forms.Form):
    """Connection form for a Data Risk Profiler scan.

    Same security contract as Studio X-Ray: the API key starts the
    background task and is never stored or logged. Email is OPTIONAL —
    the report link works without it; consent is only required when an
    email is actually provided.
    """

    odoo_url = forms.CharField(
        label=_('Odoo URL'),
        widget=forms.TextInput(attrs={
            'class': LTR_INPUT, 'placeholder': 'https://mycompany.odoo.com',
            'autocomplete': 'url',
        }),
    )
    database = forms.CharField(
        label=_('Database name'),
        widget=forms.TextInput(attrs={
            'class': LTR_INPUT, 'placeholder': 'mycompany',
            'autocomplete': 'off',
        }),
    )
    login = forms.CharField(
        label=_('Login (user email)'),
        widget=forms.TextInput(attrs={
            'class': LTR_INPUT, 'placeholder': 'audit@mycompany.com',
            'autocomplete': 'off',
        }),
    )
    api_key = forms.CharField(
        label=_('API key'),
        help_text=_('Created under My Profile → Account Security → New API Key. Used once for this scan — never stored.'),
        widget=forms.PasswordInput(attrs={
            'class': LTR_INPUT, 'placeholder': '••••••••••••',
            'autocomplete': 'off',
        }),
    )

    email = forms.EmailField(
        label=_('Your email'), required=False,
        help_text=_('Optional — to receive the report link by email.'),
        widget=forms.EmailInput(attrs={
            'class': LTR_INPUT, 'placeholder': 'you@company.com',
            'autocomplete': 'email',
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
    save_snapshot = forms.BooleanField(
        label=_('Save an anonymous aggregated snapshot so future scans can '
                'show progress. We store only scores and counts, never '
                'names, emails, VAT numbers, or examples.'),
        required=False,
        widget=forms.CheckboxInput(attrs={'class': CHECKBOX_CLASSES}),
    )
    consent = forms.BooleanField(
        label=_('Email me the report and contact me about the results. I agree to the processing of the data I submitted for this purpose.'),
        required=False,
        widget=forms.CheckboxInput(attrs={'class': CHECKBOX_CLASSES}),
    )

    # Honeypot — hidden from humans by CSS; bots fill it.
    website = forms.CharField(required=False, widget=forms.HiddenInput())

    def is_bot(self):
        return bool(self.data.get('website'))

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('email') and not cleaned.get('consent'):
            self.add_error('consent', _(
                'Please accept so we can email you the report — or leave '
                'the email field empty.'))
        return cleaned
