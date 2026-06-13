"""Helpers for the staff-only frontend admin toolbar.

Centralised so detail views and the context processor build admin links the
same way: always permission-checked, always via admin reverse URLs.
"""
from django.urls import NoReverseMatch, reverse


def admin_change_link(request, obj, label):
    """Return ``{'url', 'label'}`` for the admin change page of ``obj`` — but
    only if the request user is active staff with change permission on it.
    Returns ``None`` otherwise (so the template simply shows nothing)."""
    user = getattr(request, 'user', None)
    if not (user and user.is_active and user.is_staff and obj is not None and obj.pk):
        return None

    meta = obj._meta
    if not user.has_perm(f'{meta.app_label}.change_{meta.model_name}'):
        return None
    try:
        url = reverse(f'admin:{meta.app_label}_{meta.model_name}_change', args=[obj.pk])
    except NoReverseMatch:
        return None
    return {'url': url, 'label': label}
