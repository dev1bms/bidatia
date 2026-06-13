"""Template helpers for the blog/insights templates."""
from django import template

from blog.covers import cover_url as _cover_url

register = template.Library()


@register.simple_tag
def article_cover(post):
    """Best cover URL for an article: an uploaded image wins, else the bundled
    slug-mapped static cover, else a shared default. Usage::

        {% load blog_extras %}
        {% article_cover post as cover %}
        <img src="{{ cover }}" alt="">
    """
    return _cover_url(post)
