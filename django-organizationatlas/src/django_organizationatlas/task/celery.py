"""Celery task execution."""

from datetime import date, datetime

from celery import shared_task
from django.utils.module_loading import import_string

from .base import BaseTaskBackend


@shared_task
def celery_enqueue_task(func_path, args, kwargs):
    return import_string(func_path)(*args, **kwargs)


class CeleryBackend(BaseTaskBackend):
    def enqueue(self, func, *args, **kwargs):
        path = f'{func.__module__}.{func.__qualname__}'
        if import_string(path) is not func:
            raise ValueError(f'Task function is not importable: {path}')
        return celery_enqueue_task.delay(
            path,
            [_json_safe(value) for value in args],
            {key: _json_safe(value) for key, value in kwargs.items()},
        )


def _json_safe(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value
