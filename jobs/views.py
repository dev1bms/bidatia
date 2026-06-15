"""Public, read-only status endpoints for background tasks.

* The browser polls ``status_json`` and updates the progress component.
* ``status_page`` is a standalone human page (handy for links/bookmarks).

Access rule: a task with a ``session_key`` may only be read by the browser
session that owns it — this stops anyone from probing arbitrary UUIDs. Tasks
created without ownership (e.g. internal jobs surfaced by a signed link) stay
readable. Either way the payload never includes raw errors or internals.
"""
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, render

from .models import BackgroundTask
from .services import serialize_status


def _get_owned_task(request, pk):
    task = get_object_or_404(BackgroundTask, pk=pk)
    if task.session_key:
        # Ensure the session exists, then compare keys.
        if not request.session.session_key:
            request.session.save()
        if request.session.session_key != task.session_key:
            raise Http404('task not found')
    return task


def status_json(request, pk):
    task = _get_owned_task(request, pk)
    response = JsonResponse(serialize_status(task))
    # Status is volatile and per-session — never cache it.
    response['Cache-Control'] = 'no-store'
    return response


def status_page(request, pk):
    task = _get_owned_task(request, pk)
    return render(request, 'jobs/status_page.html', {'task': task})
