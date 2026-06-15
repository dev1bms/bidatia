"""Template helpers for the Bidatia admin grid dashboard.

The admin index renders every app as a card with an icon. Icons are
**Material Symbols** — already bundled locally by django-unfold
(static/unfold/fonts/material-symbols/), so there is no external CDN.

To give a new app its own icon, add one line to ``APP_ICONS`` below using any
Material Symbols name (https://fonts.google.com/icons). Any app not listed
falls back to ``DEFAULT_APP_ICON``.
"""
from django import template

register = template.Library()

# app_label -> Material Symbols icon name.  ← extend this dict for new apps.
APP_ICONS = {
    'auth': 'shield_person',
    'authtoken': 'key',
    'blog': 'article',
    'booking': 'event_available',
    'core': 'mail',
    'jobs': 'sync',
    'leads': 'contacts',
    'services': 'design_services',
    'site_config': 'tune',
    'tools_core': 'construction',
    'sites': 'public',
    'sitemaps': 'travel_explore',
}
DEFAULT_APP_ICON = 'category'


@register.simple_tag
def app_icon(app_label):
    """Material Symbols name for an app, or the default if unmapped."""
    return APP_ICONS.get(app_label, DEFAULT_APP_ICON)
