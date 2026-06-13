"""Template helpers for switching the active language while preserving the
current URL path and query string.

The project uses ``i18n_patterns`` with ``prefix_default_language=True``, so
every localized URL starts with a two-letter language code: ``/en/...``,
``/es/...`` or ``/ar/...``. Django's ``set_language`` view only updates the
session/cookie and redirects to ``next`` — it does NOT rewrite a
language-prefixed path, so POSTing to it with ``next=request.path`` simply
redirects back to the same (still old-language) URL because the prefix in the
URL takes precedence over the cookie for ``i18n_patterns``.

To make the language switcher actually navigate to the translated URL, we
build the target href ourselves: replace the leading ``/xx/`` segment (if it
matches one of the configured language codes) with the requested language
code, keeping the rest of the path and the query string intact.
"""
import re

from django import template
from django.conf import settings

register = template.Library()

_LANG_CODES = {code for code, _name in settings.LANGUAGES}
_PREFIX_RE = re.compile(r'^/(?P<lang>[a-zA-Z-]+)(?P<rest>/.*|)$')


def build_language_url(path, query_string, lang_code):
    """Return ``path`` (with optional ``query_string``) rewritten so its
    leading language segment is ``lang_code``.

    - ``/en/services/`` + lang ``ar``  -> ``/ar/services/``
    - ``/es/contact/``  + lang ``en``  -> ``/en/contact/``
    - ``/``             + lang ``ar``  -> ``/ar/``
    - Unknown/missing prefixes are treated as if there is no prefix, so the
      new language code is simply prepended.
    - The query string, if present, is preserved as-is.
    """
    match = _PREFIX_RE.match(path or '/')
    if match and match.group('lang') in _LANG_CODES:
        rest = match.group('rest') or '/'
        new_path = '/%s%s' % (lang_code, rest)
    else:
        # No recognizable language prefix (e.g. just "/"): prefix it.
        rest = path or '/'
        if not rest.startswith('/'):
            rest = '/' + rest
        new_path = '/%s%s' % (lang_code, rest if rest != '/' else '/')

    if query_string:
        return '%s?%s' % (new_path, query_string)
    return new_path


@register.simple_tag(takes_context=True)
def language_url(context, lang_code):
    """Usage: {% language_url 'es' %}

    Returns the current page's URL translated to ``lang_code``, preserving
    the path and query string.
    """
    request = context.get('request')
    if request is None:
        return '/%s/' % lang_code

    return build_language_url(request.path, request.META.get('QUERY_STRING', ''), lang_code)
