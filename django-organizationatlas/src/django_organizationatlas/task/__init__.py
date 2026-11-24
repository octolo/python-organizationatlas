"""Configurable backends for organization tasks."""

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


def get_task_backend():
    """Return the configured task backend."""
    backend = getattr(settings, 'ORGANIZATIONATLAS_TASK_BACKEND', 'sync')
    if backend == 'sync':
        from .sync import SyncBackend

        return SyncBackend()
    if backend == 'thread':
        from .thread import ThreadBackend

        return ThreadBackend()
    if backend == 'celery':
        from .celery import CeleryBackend

        return CeleryBackend()
    if backend == 'rq':
        from .django_rq import RQBackend

        return RQBackend()
    raise ImproperlyConfigured(
        f'Unknown ORGANIZATIONATLAS_TASK_BACKEND: {backend!r}'
    )
