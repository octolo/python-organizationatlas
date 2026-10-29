from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from ..managers.stakeholder import STAKEHOLDER_KINDS, OrganizationAtlasStakeholderRelationManager
from .source import OrganizationAtlasSourceBase
from .temporal import TemporalValidityMixin

STAKEHOLDER_MODELS = tuple(STAKEHOLDER_KINDS.values())


class OrganizationAtlasStakeholderRelation(TemporalValidityMixin, OrganizationAtlasSourceBase):
    """Relationship between a stakeholder (person or organization) and a target organization."""

    temporal_key_fields = ("content_type", "object_id", "to_organization", "relation_type")

    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        limit_choices_to=Q(app_label="django_organizationatlas", model__in=STAKEHOLDER_MODELS),
        verbose_name=_("Stakeholder Type"),
        help_text=_("Type of the stakeholder (person or organization)"),
    )
    object_id = models.PositiveBigIntegerField(
        verbose_name=_("Stakeholder ID"),
        help_text=_("ID of the stakeholder"),
    )
    stakeholder = GenericForeignKey("content_type", "object_id")

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

    objects = OrganizationAtlasStakeholderRelationManager()

    class Meta:
        verbose_name = _("Stakeholder Relation")
        verbose_name_plural = _("Stakeholder Relations")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["to_organization"]),
            models.Index(fields=["content_type", "object_id"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["content_type", "object_id", "to_organization", "relation_type"],
                condition=Q(valid_to__isnull=True, relation_type__isnull=False),
                name="unique_open_stakeholder_relation",
            ),
            models.UniqueConstraint(
                fields=["content_type", "object_id", "to_organization"],
                condition=Q(valid_to__isnull=True, relation_type__isnull=True),
                name="unique_open_untyped_stakeholder_relation",
            ),
        ]

    def clean(self):
        super().clean()
        if self.content_type_id and (
            self.content_type.app_label != "django_organizationatlas"
            or self.content_type.model not in STAKEHOLDER_MODELS
        ):
            raise ValidationError(
                {"content_type": _("Stakeholder must be a person or an organization.")}
            )
        if self.relation_type_id and self.relation_type.category.name != "stakeholder_relation":
            raise ValidationError(
                {"relation_type": _("Reference must belong to the 'stakeholder_relation' category.")}
            )

    @property
    def stakeholder_kind(self) -> str | None:
        if not self.content_type_id:
            return None
        return next(
            (kind for kind, model in STAKEHOLDER_KINDS.items() if model == self.content_type.model),
            None,
        )

    def __str__(self):
        relation_label = (
            self.relation_type.code if self.relation_type else self.other or "?"
        )
        return f"{self.stakeholder} → {relation_label} → {self.to_organization}"
