"""Celery tasks that move request-path email sending into a worker.

The visitor's submission (a Lead / ConsultationRequest) is already saved to the
database in the view, so the request can return instantly. These tasks then
deliver the internal notification email off the request path and report a
user-safe status through a jobs.BackgroundTask the browser can poll.

Email delivery is best-effort: a Lead/booking is never "lost" if SMTP is down
(the failure is archived in EmailLog for the admin), so the user-facing task is
reported as success once the submission is on file — we never alarm the visitor
about an internal email hiccup.
"""
import logging

from celery import shared_task
from django.utils import translation

logger = logging.getLogger('bidatia')


def _load_task(task_id):
    if not task_id:
        return None
    from jobs.models import BackgroundTask
    return BackgroundTask.objects.filter(pk=task_id).first()


@shared_task(ignore_result=True)
def send_lead_notification(lead_id, task_id=None, lang=None):
    from leads.models import Lead
    from core.notifications import notify_lead

    task = _load_task(task_id)
    if task:
        task.mark_running()
    lead = Lead.objects.filter(pk=lead_id).first()
    if lead is None:
        if task:
            task.mark_failed(error_message=f'Lead {lead_id} not found')
        return

    try:
        notify_lead(lead)  # synchronous SMTP — fine, we are in a worker
    except Exception as exc:  # noqa: BLE001 — never let a mail issue crash the worker
        logger.warning('lead notification task error: %s', type(exc).__name__)

    if task:
        with translation.override(lang or 'en'):
            task.mark_success(message=str(translation.gettext(
                'Your message has been received. We will reply within one business day.')))


@shared_task(ignore_result=True)
def send_consultation_notification(consultation_id, task_id=None, lang=None):
    from booking.models import ConsultationRequest
    from core.notifications import notify_consultation_request

    task = _load_task(task_id)
    if task:
        task.mark_running()
    obj = ConsultationRequest.objects.filter(pk=consultation_id).first()
    if obj is None:
        if task:
            task.mark_failed(error_message=f'ConsultationRequest {consultation_id} not found')
        return

    try:
        notify_consultation_request(obj)
    except Exception as exc:  # noqa: BLE001
        logger.warning('consultation notification task error: %s', type(exc).__name__)

    if task:
        with translation.override(lang or 'en'):
            task.mark_success(message=str(translation.gettext(
                'Your booking request has been received. We confirm every booking by email.')))
