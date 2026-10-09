from .address import OrganizationAtlasAddressAdmin
from .organization import OrganizationAtlasOrganizationAdmin
from .data import OrganizationAtlasDataAdmin, OrganizationAtlasDataTypeAdmin
from .document import OrganizationDocumentAdmin
from .event import OrganizationEventAdmin
from .person import OrganizationAtlasPersonAdmin
from .reference import OrganizationAtlasReferenceAdmin, OrganizationAtlasReferenceCategoryAdmin
from .related_object import OrganizationAtlasRelatedObjectAdmin
from .virtuals.organization import OrganizationAtlasVirtualOrganizationAdmin
from .virtuals.document import OrganizationAtlasVirtualDocumentAdmin
from .virtuals.event import OrganizationAtlasVirtualEventAdmin
from .virtuals.provider import OrganizationAtlasProviderModel

__all__ = [
    "OrganizationAtlasOrganizationAdmin",
    "OrganizationAtlasDataAdmin",
    "OrganizationAtlasDataTypeAdmin",
    "OrganizationAtlasAddressAdmin",
    "OrganizationDocumentAdmin",
    "OrganizationEventAdmin",
    "OrganizationAtlasPersonAdmin",
    "OrganizationAtlasReferenceAdmin",
    "OrganizationAtlasReferenceCategoryAdmin",
    "OrganizationAtlasRelatedObjectAdmin",
    "OrganizationAtlasProviderModel",
    "OrganizationAtlasVirtualOrganizationAdmin",
    "OrganizationAtlasVirtualDocumentAdmin",
    "OrganizationAtlasVirtualEventAdmin",
]

