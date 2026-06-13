"""Resolve the best cover image for a blog article.

Seeded articles ship a bundled, slug-mapped cover at
``static/img/insights/<slug>.png`` (original, brand-consistent, committed and
served by WhiteNoise). An admin-uploaded ``cover_image`` always takes
precedence. A shared ``default.png`` is the fallback, so a card, detail page or
social card never points at a missing file.

Kept out of the model so there is no migration and no import cycle (core.seo and
the views/templates all reuse these helpers).
"""
from django.contrib.staticfiles import finders
from django.templatetags.static import static

DEFAULT_COVER = 'img/insights/default.png'


def cover_static_name(post):
    """Static-relative cover path for ``post`` (slug-mapped), or the shared
    default when no bundled file exists for that slug."""
    name = 'img/insights/%s.png' % post.slug
    return name if finders.find(name) else DEFAULT_COVER


def cover_url(post):
    """Root-relative cover URL: an uploaded ``cover_image`` wins, otherwise the
    bundled slug-mapped static cover (or the default)."""
    uploaded = getattr(post, 'cover_image', None)
    if uploaded:
        try:
            return uploaded.url
        except ValueError:
            pass
    return static(cover_static_name(post))
