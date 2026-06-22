from django.shortcuts import redirect, render
from django.utils.translation import gettext as _

from jobs.services import create_task

from .forms import ContactForm


def _dispatch_lead_notification(request, lead):
    """Queue the notification email off the request path and return a
    BackgroundTask the success page can poll. Falls back to running inline if
    the broker is unavailable, so the email still goes out and nothing blocks
    longer than the (fast) send itself."""
    from core.tasks import send_lead_notification

    if not request.session.session_key:
        request.session.save()  # materialize a session so the task is owned
    task = create_task(
        task_type='contact_email',
        title=_('Sending your message…'),
        session_key=request.session.session_key,
    )
    lang = getattr(request, 'LANGUAGE_CODE', 'en') or 'en'
    try:
        send_lead_notification.delay(lead.pk, str(task.pk), lang)
    except Exception:  # noqa: BLE001 — broker down: deliver inline, still non-fatal
        send_lead_notification(lead.pk, str(task.pk), lang)
    return task


def contact(request):
    if request.method == 'POST':
        form = ContactForm(request.POST)
        if form.is_valid():
            lead = form.save()
            # Lead is saved; the notification email is delivered in the
            # background so the browser gets an instant response.
            task = _dispatch_lead_notification(request, lead)
            request.session['contact_task_id'] = str(task.pk)
            return redirect('leads:contact_success')
    else:
        form = ContactForm()

    context = {
        'form': form,
        'meta_description': _(
            'Get in touch with BidERP for Odoo and ERP technical support, custom development '
            'or integration projects. Based in Madrid, working with clients worldwide.'
        ),
    }
    return render(request, 'core/contact.html', context)


def contact_success(request):
    # One-shot: the task id is consumed so a refresh doesn't re-poll forever.
    task_id = request.session.pop('contact_task_id', None)
    return render(request, 'core/contact_success.html', {
        'meta_description': _('Thank you for contacting BidERP — we will get back to you shortly.'),
        'task_id': task_id,
    })
