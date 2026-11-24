"""Synchronous task execution."""

from .base import BaseTaskBackend


class SyncBackend(BaseTaskBackend):
    def enqueue(self, func, *args, **kwargs):
        return func(*args, **kwargs)
