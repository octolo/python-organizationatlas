"""Organization models."""

from .address import OrganizationAtlasAddress
from .organization import OrganizationAtlasOrganization
from .data import OrganizationAtlasData, OrganizationAtlasDataType
from .document import OrganizationAtlasDocument
from .event import OrganizationAtlasEvent
from .person import OrganizationAtlasPerson
from .referentiel import OrganizationAtlasReferentiel
from .related_object import OrganizationAtlasRelatedObject
from .relation import OrganizationAtlasOrganizationRelation
from .stakeholder import OrganizationAtlasStakeholderRelation
from .virtuals import (
    OrganizationAtlasProviderModel,
    OrganizationAtlasVirtualOrganization,
    OrganizationAtlasVirtualDocument,
    OrganizationAtlasVirtualEvent,
)

__all__ = [
    "OrganizationAtlasOrganization",
    "OrganizationAtlasData",
    "OrganizationAtlasDataType",
    "OrganizationAtlasDocument",
    "OrganizationAtlasEvent",
    "OrganizationAtlasAddress",
    "OrganizationAtlasPerson",
    "OrganizationAtlasReferentiel",
    "OrganizationAtlasRelatedObject",
    "OrganizationAtlasOrganizationRelation",
    "OrganizationAtlasStakeholderRelation",
    "OrganizationAtlasProviderModel",
    "OrganizationAtlasVirtualOrganization",
    "OrganizationAtlasVirtualDocument",
    "OrganizationAtlasVirtualEvent",
]
