from django import forms
from django.utils.translation import gettext_lazy as _

from core.form_styles import CHECKBOX_CLASSES, TEXT_INPUT_CLASSES

# Connection fields hold technical LTR content (URLs, logins, API keys) — keep
# them LTR even on the Arabic RTL page.
LTR_INPUT = TEXT_INPUT_CLASSES + ' force-ltr'


class StudioXrayRunForm(forms.Form):
    """Connection + lead form for a Studio X-Ray run.

    The API key is used to start the background task and is never stored:
    it is not part of any model and must never be written to logs.
    """

    odoo_url = forms.CharField(
        label=_('Odoo URL'),
        widget=forms.TextInput(attrs={
            'class': LTR_INPUT, 'placeholder': 'https://mycompany.odoo.com',
            'autocomplete': 'url',
            '@change': 'detectDb()',  # auto-suggest the database name
        }),
    )
    database = forms.CharField(
        label=_('Database name'),
        widget=forms.TextInput(attrs={
            'class': LTR_INPUT, 'placeholder': 'mycompany',
            'autocomplete': 'off',
            'list': 'xray-db-options',          # filled by detectDb()
            '@input': 'dbAutoFilled = false',   # manual typing wins
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

    SCOPE_CHOICES = [
        ('studio', _('Studio customizations only — what was built through the Odoo UI')),
        ('full', _('Comprehensive — Studio plus the footprint of custom Python modules')),
    ]
    scan_scope = forms.ChoiceField(
        label=_('Scan scope'), choices=SCOPE_CHOICES, initial='studio',
        required=False, widget=forms.RadioSelect,
    )

    def clean_scan_scope(self):
        return self.cleaned_data.get('scan_scope') or 'studio'

    email = forms.EmailField(
        label=_('Your email'),
        help_text=_('Where should we send your full report?'),
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

    consent = forms.BooleanField(
        label=_('Email me the report and contact me about the results. I agree to the processing of the data I submitted for this purpose.'),
        widget=forms.CheckboxInput(attrs={'class': CHECKBOX_CLASSES}),
    )

    # Honeypot — hidden from humans by CSS; bots fill it.
    website = forms.CharField(required=False, widget=forms.HiddenInput())

    def is_bot(self):
        return bool(self.data.get('website'))
