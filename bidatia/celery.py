"""Celery application for bidatia.

Worker:  celery -A bidatia worker -l info
Beat:    celery -A bidatia beat -l info

Run workers at INFO log level (not DEBUG) in production: DEBUG-level task
logging can include task arguments, and tool-run tasks receive Odoo
credentials as arguments.
"""
import os

from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'bidatia.settings')

app = Celery('bidatia')

# All Celery settings live in Django settings under the CELERY_ prefix.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Find tasks.py modules in all installed apps (tools_core.tasks, ...).
app.autodiscover_tasks()
