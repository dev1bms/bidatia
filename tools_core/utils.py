"""Small shared helpers for the tools apps."""
from django.core.cache import cache


def diagnostics_visible(request):
    """Whether a failed run's technical `diagnostic` may be shown on the progress
    page. Staff always see it; everyone else only when an admin has flipped the
    OperationalConfiguration.show_tool_diagnostics flag on (off by default, so
    it's easy to hide again after debugging). Never raises."""
    if getattr(getattr(request, 'user', None), 'is_staff', False):
        return True
    try:
        from site_config.services import get_operational_config
        cfg = get_operational_config()
        return bool(cfg and cfg.show_tool_diagnostics)
    except Exception:  # noqa: BLE001 — config table missing etc. → hide
        return False


def scrub_secrets(text, *secrets):
    """Redact known credential values from a diagnostic string before it is
    stored or shown. The exception text may quote the login/api_key it was
    given; replace each non-empty secret with '***'. Result is length-capped."""
    out = str(text)
    for secret in secrets:
        if secret and len(str(secret)) >= 4:
            out = out.replace(str(secret), '***')
    return out[:500]


def rate_limit_exceeded(key, limit, window_seconds):
    """Cache-based fixed-window rate limiter.

    Phase 1 uses the default LocMemCache: with multiple gunicorn workers the
    effective limit is per-worker. Good enough at current volume; switches to
    a shared Redis cache transparently once M3 lands.
    """
    full_key = f'tools_core:rl:{key}'
    if cache.add(full_key, 1, timeout=window_seconds):
        return False
    try:
        count = cache.incr(full_key)
    except ValueError:
        # Key expired between add() and incr() — window restarts.
        cache.add(full_key, 1, timeout=window_seconds)
        return False
    return count > limit


def client_ip(request):
    """Best client IP available. Production sits behind Cloudflare Tunnel, so
    CF-Connecting-IP is trustworthy there; locally it falls back to REMOTE_ADDR."""
    return request.META.get('HTTP_CF_CONNECTING_IP') or request.META.get('REMOTE_ADDR') or 'unknown'


# ── Live run notes (AI thinking trace) ────────────────────────────────────────
# Written by the Celery worker, read by the status endpoint — so they must go
# through the SHARED 'tools' (Redis) cache, never the per-process default one.
# All helpers swallow cache failures: a missing note only means the progress
# page falls back to its canned phrases.

_RUN_NOTE_KEY = 'tools_core:run-note:%s'
_RUN_NOTE_TTL = 300


def set_run_note(run_id, text):
    try:
        from django.core.cache import caches
        caches['tools'].set(_RUN_NOTE_KEY % run_id, text, _RUN_NOTE_TTL)
    except Exception:  # noqa: BLE001 — cosmetic feature, never raise
        pass


def get_run_note(run_id):
    try:
        from django.core.cache import caches
        return caches['tools'].get(_RUN_NOTE_KEY % run_id) or ''
    except Exception:  # noqa: BLE001
        return ''


def clear_run_note(run_id):
    try:
        from django.core.cache import caches
        caches['tools'].delete(_RUN_NOTE_KEY % run_id)
    except Exception:  # noqa: BLE001
        pass
