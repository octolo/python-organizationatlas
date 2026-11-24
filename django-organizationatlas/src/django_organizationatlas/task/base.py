"""Task backend interface."""


class BaseTaskBackend:
    def enqueue(self, func, *args, **kwargs):
        raise NotImplementedError
