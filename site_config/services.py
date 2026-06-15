"""Centralized, cached access to runtime configuration.

Read order is always **database first, environment/``settings.py`` fallback**, so
nothing breaks before an admin has filled anything in (or if a row is missing).

Caching: each singleton is cached in the in-process ``default`` cache for a
short TTL. ``clear_config_cache()`` is called on every save so the editing
worker is immediately fresh; other gunicorn workers converge within the TTL.
Every getter tolerates a missing table/row (e.g. before migrations) and returns
the environment fallback instead of raising.
"""
from django.conf import settings
from django.core.cache import cache

from .models import (
    AIConfiguration,
    EmailConfiguration,
    OperationalConfiguration,
    SiteConfiguration,
)

_TTL = 30  # seconds — bounds cross-worker staleness for config values
_MODELS = {
    'site_config:site': SiteConfiguration,
    'site_config:email': EmailConfiguration,
    'site_config:ai': AIConfiguration,
    'site_config:ops': OperationalConfiguration,
}


def clear_config_cache():
    cache.delete_many(list(_MODELS))


def _load(key):
    cached = cache.get(key)
    if cached is not None:
        return cached
    try:
        obj = _MODELS[key].load()
    except Exception:  # noqa: BLE001 — table missing (pre-migrate) etc. → fallbacks
        return None
    cache.set(key, obj, _TTL)
    return obj


def get_site_config():
    return _load('site_config:site')


def get_email_config():
    return _load('site_config:email')


def get_ai_config():
    return _load('site_config:ai')


def get_operational_config():
    return _load('site_config:ops')


# ── Effective values (DB value, else environment/settings) ──────────────────
def _v(obj, attr, fallback):
    val = getattr(obj, attr, None) if obj is not None else None
    return val if val not in (None, '') else fallback


def site_name():
    return _v(get_site_config(), 'site_name', settings.SITE_NAME)


def site_base_url():
    return _v(get_site_config(), 'canonical_base_url', settings.SITE_BASE_URL)


def public_contact_email():
    return _v(get_site_config(), 'public_contact_email', settings.CONTACT_EMAIL)


def admin_recipient_email():
    return _v(get_site_config(), 'admin_recipient_email',
              settings.CONTACT_NOTIFICATION_EMAIL)


def default_from_email():
    return _v(get_email_config(), 'default_from_email', settings.DEFAULT_FROM_EMAIL)


def reply_to_default():
    cfg = get_email_config()
    return [cfg.reply_to_email] if (cfg and cfg.reply_to_email) else []


def email_connection_kwargs():
    """Connection overrides for django.core.mail.get_connection().

    Returns {} when the admin email override is off or incomplete, so the
    environment EMAIL_* settings are used unchanged (the safe default, and what
    the test backend expects).
    """
    cfg = get_email_config()
    if not (cfg and cfg.enabled and cfg.smtp_host):
        return {}
    kwargs = {
        'host': cfg.smtp_host,
        'use_ssl': cfg.use_ssl,
        'use_tls': cfg.use_tls,
    }
    if cfg.smtp_port:
        kwargs['port'] = cfg.smtp_port
    if cfg.smtp_username:
        kwargs['username'] = cfg.smtp_username
    if cfg.smtp_password:
        kwargs['password'] = cfg.smtp_password
    return kwargs


def ai_settings():
    """Effective AI parameters as a plain dict (DB over settings)."""
    cfg = get_ai_config()
    model = _v(cfg, 'model_name', settings.TOOLS_AI_MODEL)
    # DB master switch wins; otherwise AI is "enabled" iff a model is configured.
    if cfg is not None:
        enabled = bool(cfg.enabled and model)
    else:
        enabled = bool(model)
    return {
        'enabled': enabled,
        'provider': _v(cfg, 'provider', 'ollama'),
        'model': model,
        'timeout': _v(cfg, 'request_timeout', settings.TOOLS_AI_TIMEOUT),
        'thinking_budget': _v(cfg, 'thinking_budget',
                              getattr(settings, 'TOOLS_AI_THINKING_BUDGET', 60)),
        'max_output_tokens': getattr(cfg, 'max_output_tokens', None) if cfg else None,
        'temperature': getattr(cfg, 'temperature', None) if cfg else None,
        'system_instructions': getattr(cfg, 'system_instructions', '') if cfg else '',
    }
