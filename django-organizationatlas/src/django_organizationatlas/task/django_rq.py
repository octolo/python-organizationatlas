"""Django RQ task execution."""

import django_rq

from .base import BaseTaskBackend


class RQBackend(BaseTaskBackend):
    def enqueue(self, func, *args, **kwargs):
        return django_rq.get_queue('default').enqueue(func, *args, **kwargs)
