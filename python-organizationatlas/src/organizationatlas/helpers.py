from typing import Any, cast

from providerkit.helpers import call_providers, get_providers

from .providers import OrganizationAtlasProvider

ADD_FIELDS = {
    "geo_data": {
        "label": "Data source",
        "description": "Data source",
        "format": "str",
    },
}


def get_organizationatlas_providers(*args: Any, **kwargs: Any) -> dict[str, Any] | str:
    """Get organizationatlas providers."""
    lib_name = kwargs.pop("lib_name", "organizationatlas")
    return cast("dict[str, Any] | str", get_providers(*args, lib_name=lib_name, add_fields=ADD_FIELDS, **kwargs))


def get_organizationatlas_provider(attribute_search: dict[str, Any], *args: Any, **kwargs: Any) -> OrganizationAtlasProvider:
    """Get a single organizationatlas provider by attribute search."""
    lib_name = kwargs.pop("lib_name", "organizationatlas")
    providers = get_providers(*args, attribute_search=attribute_search, format="python", lib_name=lib_name, add_fields=ADD_FIELDS, **kwargs)
    if not providers:
        raise ValueError("No providers found")
    if len(providers) > 1:
        raise ValueError(f"Expected 1 provider, got {len(providers)}")
    return cast("OrganizationAtlasProvider", providers[0])


def _make_provider_call(command: str, arg_name: str):
    def _fn(*args: Any, **kwargs: Any) -> Any:
        if args:
            value, rest = args[0], args[1:]
        else:
            value = kwargs.pop(arg_name)
            rest = ()
        return call_providers(*rest, command=command, lib_name="organizationatlas", **{arg_name: value}, **kwargs)
    _fn.__name__ = command
    _fn.__qualname__ = command
    return _fn


search_organization = _make_provider_call("search_organization", "query")
search_organization_by_reference = _make_provider_call("search_organization_by_reference", "code")
get_organization_documents = _make_provider_call("get_organization_documents", "code")
get_organization_events = _make_provider_call("get_organization_events", "code")
get_organization_officers = _make_provider_call("get_organization_officers", "code")
get_ultimate_beneficial_owners = _make_provider_call("get_ultimate_beneficial_owners", "code")
get_organization_history = _make_provider_call("get_organization_history", "code")
