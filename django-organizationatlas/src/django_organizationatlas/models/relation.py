from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from .source import OrganizationAtlasSourceBase
from .temporal import TemporalValidityMixin


class OrganizationAtlasOrganizationRelation(TemporalValidityMixin, OrganizationAtlasSourceBase):
    """Directional relationship between two organizations."""

    temporal_key_fields = ("from_organization", "to_organization", "relation_type")

    from_organization = models.ForeignKey(
        "django_organizationatlas.OrganizationAtlasOrganization",
        on_delete=models.CASCADE,
        related_name="relations_from",
        verbose_name=_("From Organization"),
        help_text=_("Organization that holds this relation"),
    )
    to_organization = models.ForeignKey(
        "django_organizationatlas.OrganizationAtlasOrganization",
        on_delete=models.CASCADE,
        related_name="relations_to",
        verbose_name=_("To Organization"),
        help_text=_("Organization targeted by this relation"),
    )
    relation_type = models.ForeignKey(
        "django_organizationatlas.OrganizationAtlasReferentiel",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="organization_relations",
        limit_choices_to={"category": "organization_relation"},
        verbose_name=_("Relation Type"),
        help_text=_("Type of relationship between the two organizations"),
    )
    other = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name=_("Other"),
        help_text=_("Free description when relation type is 'Other'"),
    )

    class Meta:
        verbose_name = _("Relation")
        verbose_name_plural = _("Relations")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["from_organization", "to_organization"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["from_organization", "to_organization", "relation_type"],
                condition=Q(valid_to__isnull=True),
                name="unique_open_organization_relation",
            ),
        ]

    def clean(self):
        super().clean()
        if self.relation_type_id and self.relation_type.category != "organization_relation":
            raise ValidationError(
                {"relation_type": _("Referentiel must belong to the 'organization_relation' category.")}
            )

    def __str__(self):
        relation_label = (
            self.relation_type.code if self.relation_type else self.other or "?"
        )
        return f"{self.from_organization} → {relation_label} → {self.to_organization}"
