"""Helpers for creating and reading background-task records.

Kept separate from models so views, Celery tasks and request handlers all
share one safe way to build a task and one safe way to serialise it for the
status API (no raw error details ever leak to the browser).
"""
from django.utils.translation import gettext as _

from .models import BackgroundTask


def create_task(*, task_type, title, session_key='', message='', progress=None):
    """Create a queued BackgroundTask. ``title``/``message`` should already be
    translated strings (str() any lazy proxies before calling)."""
    return BackgroundTask.objects.create(
        task_type=task_type,
        title=str(title)[:150],
        message=str(message)[:255],
        progress=progress,
        session_key=session_key or '',
    )


# Default, user-safe line per status — translated in the CURRENT request
# language at serialise time, so a worker that ran under a different locale
# never pins the wording the visitor sees.
def status_message(task):
    if task.message:
        return task.message
    return {
        BackgroundTask.STATUS_QUEUED: _('Queued — this will start in a moment.'),
        BackgroundTask.STATUS_RUNNING: _('Working on it…'),
        BackgroundTask.STATUS_SUCCESS: _('Completed successfully.'),
        BackgroundTask.STATUS_FAILED: _('Something went wrong.'),
        BackgroundTask.STATUS_CANCELLED: _('This task was cancelled.'),
    }.get(task.status, '')


def serialize_status(task):
    """Build the public JSON payload for the status API.

    Deliberately omits ``error_message`` (admin-only) and any internal field;
    failures surface a fixed, translated, user-safe message instead.
    """
    payload = {
        'id': str(task.id),
        'status': task.status,
        'progress': task.progress,
        'message': status_message(task),
        'poll': task.is_active,
        'result_url': '',
        'error': '',
    }
    if task.status == BackgroundTask.STATUS_SUCCESS and task.result_url:
        payload['result_url'] = task.result_url
    if task.status == BackgroundTask.STATUS_FAILED:
        payload['error'] = _('Something went wrong. Please try again.')
    return payload
