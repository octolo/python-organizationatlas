from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from .source import OrganizationAtlasSourceBase
from .temporal import TemporalValidityMixin


class OrganizationAtlasStakeholderRelation(TemporalValidityMixin, OrganizationAtlasSourceBase):
    """Relationship between a stakeholder (person or organization) and a target organization."""

    temporal_key_fields = ("from_person", "from_organization", "to_organization", "relation_type")

    # Stakeholder — exactly one must be set
    from_person = models.ForeignKey(
        "django_organizationatlas.OrganizationAtlasPerson",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="stakeholder_relations",
        verbose_name=_("From Person"),
        help_text=_("Physical person stakeholder (mutually exclusive with From Organization)"),
    )
    from_organization = models.ForeignKey(
        "django_organizationatlas.OrganizationAtlasOrganization",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="stakeholder_relations_as_holder",
        verbose_name=_("From Organization"),
        help_text=_("Organization stakeholder (mutually exclusive with From Person)"),
    )

    # Target — always a organization
    to_organization = models.ForeignKey(
        "django_organizationatlas.OrganizationAtlasOrganization",
        on_delete=models.CASCADE,
        related_name="stakeholder_relations",
        verbose_name=_("To Organization"),
        help_text=_("Organization targeted by this stakeholder relation"),
    )

    relation_type = models.ForeignKey(
        "django_organizationatlas.OrganizationAtlasReference",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="stakeholder_relations",
        limit_choices_to={"category__name": "stakeholder_relation"},
        verbose_name=_("Relation Type"),
        help_text=_("Nature of the stakeholder relationship"),
    )
    other = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name=_("Other"),
        help_text=_("Free description when relation type is 'Other'"),
    )

    class Meta:
        verbose_name = _("Stakeholder Relation")
        verbose_name_plural = _("Stakeholder Relations")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["to_organization"]),
            models.Index(fields=["from_person", "to_organization"]),
            models.Index(fields=["from_organization", "to_organization"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(from_person__isnull=False, from_organization__isnull=True)
                    | models.Q(from_person__isnull=True, from_organization__isnull=False)
                ),
                name="stakeholder_relation_exactly_one_from",
            ),
            models.UniqueConstraint(
                fields=["from_person", "from_organization", "to_organization", "relation_type"],
                condition=Q(valid_to__isnull=True),
                name="unique_open_stakeholder_relation",
            ),
        ]

    def clean(self):
        super().clean()
        has_person = self.from_person_id is not None
        has_organization = self.from_organization_id is not None
        if has_person == has_organization:
            raise ValidationError(
                _("Exactly one of 'From Person' or 'From Organization' must be set.")
            )
        if self.relation_type_id and self.relation_type.category.name != "stakeholder_relation":
            raise ValidationError(
                {"relation_type": _("Reference must belong to the 'stakeholder_relation' category.")}
            )

    @property
    def stakeholder(self):
        return self.from_person or self.from_organization

    def __str__(self):
        relation_label = (
            self.relation_type.code if self.relation_type else self.other or "?"
        )
        return f"{self.stakeholder} → {relation_label} → {self.to_organization}"
