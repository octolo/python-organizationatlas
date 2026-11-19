from typing import Any

from virtualqueryset.managers import VirtualManager


class OrganizationAtlasVirtualCommandManager(VirtualManager):
    """Base manager for single-command virtual querysets pulled from organizationatlas providers."""

    _command: str
    _commands: dict

    def __init__(self, code: str | None = None, **kwargs: Any):
        super().__init__()
        self.code = code
        self.first = kwargs.get("first", False)
        self.backend = kwargs.get("backend")
        self.attribute_search = kwargs.get("attribute_search")
        self._cached_providers: dict = {}
        setattr(self, f"_cached_data_{self._command}", {})

    def _clear_cached_command(self, command: str) -> None:
        setattr(self, f"_cached_data_{command}", {})

    def set_cached_command(self, command: str, cache: Any, **kwargs: Any) -> Any:
        cache = self.queryset_class(model=self.model, data=cache)
        setattr(self, f"_cached_data_{command}", {"kwargs": kwargs, "data": cache})
        return self.get_cached_command(command, **kwargs)

    def get_cached_command(self, command: str, **kwargs: Any) -> Any:
        cache = getattr(self, f"_cached_data_{command}", {})
        if kwargs == cache.get("kwargs", {}) and cache.get("data") is not None:
            return cache.get("data")
        return None

    def get_command_data_list(self, results: Any, command: str) -> list[Any]:
        data_list = []
        for result in results:
            if isinstance(result, dict) and "provider" in result:
                if "error" in result:
                    continue
                provider_obj = result["provider"]
                normalize_data = provider_obj.get_service_normalize(command)  # type: ignore[attr-defined]
                if isinstance(normalize_data, list):
                    data_list.extend(normalize_data)
                else:
                    data_list.append(normalize_data)
        return data_list

    def get_queryset_command(self, command: str, **kwargs: Any) -> Any:
        cached = self.get_cached_command(command)
        if not cached or kwargs.get("ignore_cache", False):
            self._clear_cached_command(command)
            command_func = self._commands[command]
            results = command_func(**kwargs)
            self._cached_providers[command] = results
            data_list = self.get_command_data_list(results, command)
            cached = self.set_cached_command(command, data_list, **kwargs)
        return cached

    def get_data(self) -> Any:
        if not self.code:
            return self.queryset_class(model=self.model, data=[])
        kwargs: dict[str, Any] = {
            "code": self.code,
            "first": self.first,
            "attribute_search": self.attribute_search,
        }
        if self.backend:
            kwargs["attribute_search"] = {"name": self.backend}
        return self.get_queryset_command(self._command, **kwargs)
