"""Threaded task execution."""

import logging
from threading import Thread

from django.db import close_old_connections

from .base import BaseTaskBackend

logger = logging.getLogger(__name__)


def _run(func, args, kwargs):
    close_old_connections()
    try:
        func(*args, **kwargs)
    except Exception:
        logger.exception('Thread task failed: %s', func)
        raise
    finally:
        close_old_connections()


class ThreadBackend(BaseTaskBackend):
    def enqueue(self, func, *args, **kwargs):
        thread = Thread(target=_run, args=(func, args, kwargs), daemon=True)
        thread.start()
        return thread
