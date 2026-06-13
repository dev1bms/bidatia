"""Internal funnel analytics for the free tools.

One call per funnel moment: track(request, tool, event, ...). Always
best-effort — analytics must NEVER break or slow a user-facing flow, so
every failure is swallowed and logged. No raw IPs, no secrets in metadata.
"""
import hashlib
import logging

logger = logging.getLogger('bidatia.tools')


def track(request, tool, event, run=None, email='', **metadata):
    """Record one ToolEvent. `request` may be None (Celery tasks)."""
    from tools_core.models import ToolEvent
    try:
        ToolEvent.objects.create(
            tool=tool[:40],
            event=event[:60],
            run=run,
            email=(email or '').strip().lower()[:254],
            visitor_key=visitor_fingerprint(request),
            metadata=metadata or {},
        )
    except Exception:  # noqa: BLE001 — analytics never breaks a flow
        logger.warning('analytics: failed to record %s/%s', tool, event)


def visitor_fingerprint(request):
    """Short pseudonymous key for journey stitching — never the raw IP."""
    if request is None:
        return ''
    from tools_core.utils import client_ip
    raw = f"{client_ip(request)}|{request.META.get('HTTP_USER_AGENT', '')}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]
