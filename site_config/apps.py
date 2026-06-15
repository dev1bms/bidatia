from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class SiteConfigConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'site_config'
    verbose_name = _('Configuration')
