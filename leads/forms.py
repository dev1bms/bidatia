from django import forms
from django.utils.translation import gettext_lazy as _

from core.form_styles import TEXT_INPUT_CLASSES

from .models import Lead

# Contact messages get a slightly taller textarea than the shared default.
TEXTAREA_CLASSES = TEXT_INPUT_CLASSES + ' min-h-[140px] resize-y'


class ContactForm(forms.ModelForm):
    class Meta:
        model = Lead
        fields = ['name', 'email', 'company_name', 'message']
        widgets = {
            'name': forms.TextInput(attrs={'class': TEXT_INPUT_CLASSES, 'placeholder': _('Your name')}),
            'email': forms.EmailInput(attrs={'class': TEXT_INPUT_CLASSES, 'placeholder': 'you@company.com'}),
            'company_name': forms.TextInput(attrs={'class': TEXT_INPUT_CLASSES, 'placeholder': _('Company (optional)')}),
            'message': forms.Textarea(attrs={
                'class': TEXTAREA_CLASSES,
                'placeholder': _('Tell me a bit about your Odoo setup and what you need help with.'),
            }),
        }
        labels = {
            'name': _('Full name'),
            'company_name': _('Company name'),
        }

    def save(self, commit=True):
        lead = super().save(commit=False)
        lead.source = 'contact_form'
        if commit:
            lead.save()
        return lead
