from django.shortcuts import redirect, render
from django.utils.translation import gettext as _

from core.notifications import notify_lead

from .forms import ContactForm


def contact(request):
    if request.method == 'POST':
        form = ContactForm(request.POST)
        if form.is_valid():
            lead = form.save()
            # Saved to DB above; email is best-effort and never blocks the user.
            notify_lead(lead)
            return redirect('leads:contact_success')
    else:
        form = ContactForm()

    context = {
        'form': form,
        'meta_description': _(
            'Get in touch with Bidatia for Odoo and ERP technical support, custom development '
            'or integration projects. Based in Madrid, working with clients worldwide.'
        ),
    }
    return render(request, 'core/contact.html', context)


def contact_success(request):
    return render(request, 'core/contact_success.html', {
        'meta_description': 'Thank you for contacting Bidatia — we will get back to you shortly.',
    })
