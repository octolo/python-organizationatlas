from __future__ import annotations

import copy
import json
from typing import Any

from providerkit import ProviderBase

from .. import (
    ORGANIZATIONATLAS_GET_COMPANY_DOCUMENTS_FIELDS,
    ORGANIZATIONATLAS_GET_COMPANY_EVENTS_FIELDS,
    ORGANIZATIONATLAS_GET_COMPANY_OFFICERS_FIELDS,
    ORGANIZATIONATLAS_GET_ULTIMATE_BENEFICIAL_OWNERS_FIELDS,
    ORGANIZATIONATLAS_GET_REFERENTIEL_FIELDS,
    ORGANIZATIONATLAS_SEARCH_COMPANY_FIELDS,
)


class OrganizationAtlasProvider(ProviderBase):
    geo_zone = "world"
    geo_country = "world"
    geo_code = "ww"
    config_prefix = "ORGANIZATIONATLAS"
    provider_key = "key"
    _default_services_cfg = {
        "search_organization": {
            "label": "Search organization",
            "description": "Search organization",
            "format": "str",
            "fields": ORGANIZATIONATLAS_SEARCH_COMPANY_FIELDS,
        },
        "search_organization_by_reference": {
            "label": "Search organization by reference",
            "description": "Search organization by reference",
            "format": "str",
            "fields": ORGANIZATIONATLAS_SEARCH_COMPANY_FIELDS,
        },
        "get_organization_documents": {
            "label": "Get organization documents",
            "description": "Get organization documents",
            "format": "str",
            "fields": ORGANIZATIONATLAS_GET_COMPANY_DOCUMENTS_FIELDS,
        },
        "get_organization_events": {
            "label": "Get organization events",
            "description": "Get organization events",
            "format": "str",
            "fields": ORGANIZATIONATLAS_GET_COMPANY_EVENTS_FIELDS,
        },
        "get_organization_officers": {
            "label": "Get organization officers",
            "description": "Get organization officers",
            "format": "str",
            "fields": ORGANIZATIONATLAS_GET_COMPANY_OFFICERS_FIELDS,
        },
        "get_ultimate_beneficial_owners": {
            "label": "Get ultimate beneficial owners",
            "description": "Get ultimate beneficial owners",
            "format": "str",
            "fields": ORGANIZATIONATLAS_GET_ULTIMATE_BENEFICIAL_OWNERS_FIELDS,
        },
        "get_referentiel": {
            "label": "Get referentiel",
            "description": "Get referentiel data (governance sources, legal frameworks, etc.)",
            "format": "list",
            "fields": ORGANIZATIONATLAS_GET_REFERENTIEL_FIELDS,
        }
    }

    @property
    def geo_data(self) -> str:
        return f"{self.geo_zone}/{self.geo_country} ({self.geo_code})"

    def get_normalize_country(self, data: dict[str, Any]) -> str:
        return self.geo_data

    def get_normalize_country_code(self, data: dict[str, Any]) -> str:
        return self.geo_code

    def get_normalize_data_source(self, data: dict[str, Any]) -> str:
        return json.dumps(data, ensure_ascii=False, default=str)

    def get_insert_normalized_organizationatlas_id(self, data: Any, normalized: dict[str, Any], _config: dict[str, Any]) -> float | None:
        reference = normalized.get("reference")
        return f"{self.name}_{reference}"

    def response(self, *args: Any, **kwargs: Any) -> str:
        readable = kwargs.pop('readable', False)
        command = args[0]
        mode = args[2]
        if readable and mode == 'terminal':
            original_cfg = self.services_cfg
            self.services_cfg = copy.deepcopy(original_cfg)
            self.services_cfg[command]['fields'].pop('organizationatlas_id', None)
            self.services_cfg[command]['fields'].pop('data_source', None)
            self.services_cfg[command]['fields'].pop('address_json', None)
            try:
                return super().response(*args, **kwargs)
            finally:
                self.services_cfg = original_cfg
        return super().response(*args, **kwargs)


__all__ = ['OrganizationAtlasProvider']
