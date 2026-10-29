from django.db import models
from django.db.models import Case, CharField, Value, When

STAKEHOLDER_KINDS = {
    "person": "organizationatlasperson",
    "organization": "organizationatlasorganization",
}


def stakeholder_kind(prefix: str = ""):
    """'person' or 'organization', usable from any queryset reaching the relation through ``prefix``."""
    return Case(
        *(
            When(**{f"{prefix}content_type__model": model}, then=Value(kind))
            for kind, model in STAKEHOLDER_KINDS.items()
        ),
        output_field=CharField(),
    )


class OrganizationAtlasStakeholderRelationQuerySet(models.QuerySet):
    def with_stakeholder_kind(self):
        return self.annotate(sql_stakeholder_kind=stakeholder_kind())


OrganizationAtlasStakeholderRelationManager = models.Manager.from_queryset(
    OrganizationAtlasStakeholderRelationQuerySet,
)
