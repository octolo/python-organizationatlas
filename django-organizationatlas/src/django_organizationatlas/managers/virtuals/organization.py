from typing import Any

from organizationatlas.helpers import search_organization, search_organization_by_reference
from django_providerkit.managers import BaseServiceProviderManager


class OrganizationAtlasVirtualOrganizationManager(BaseServiceProviderManager):
    """Manager for organization search from organizationatlas."""

    _commands = {
        'search_organization': search_organization,
        'search_organization_by_reference': search_organization_by_reference,
    }

    _args_available = ['query', 'code', 'first', 'backend']

    def search_organization(self, query: str, first: bool = False, **kwargs: Any) -> Any:
        return self.get_queryset_command('search_organization', query=query, first=first, **kwargs)

    def search_organization_by_reference(self, code: str, **kwargs: Any) -> Any:
        code_parts = code.split("_")
        reference = code_parts[-1]
        backend = "_".join(code_parts[:-1])
        return self.get_queryset_command(
            'search_organization_by_reference',
            code=reference,
            attribute_search={"name": backend},
            **kwargs)

    def get_data(self) -> Any:
        if not self.query and not self.code:
            return []
        command = self._command
        kwargs = {
            "first": self.first,
            "attribute_search": self.attribute_search,
        }
        if self.backend:
            kwargs["attribute_search"] = {"name": self.backend}
        if command == "search_organization_by_reference":
            if not self.code:
                return self.queryset_class(model=self.model, data=[])
            kwargs["code"] = self.code
        else:
            if not self.query:
                return self.queryset_class(model=self.model, data=[])
            kwargs["query"] = self.query
        return self.get_queryset_command(command, **kwargs)
