from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from .organization import OrganizationAtlasOrganization
from .source import OrganizationAtlasSourceBase

GENDER_CATEGORIES = ("gender", "gender_response", "gender_structure")


class OrganizationAtlasPerson(OrganizationAtlasSourceBase):
    """Physical persons attached to a organization (officers and beneficial owners)."""

    organization = models.ForeignKey(
        OrganizationAtlasOrganization,
        on_delete=models.CASCADE,
        related_name="to_organizationatlasperson",
        verbose_name=_("Organization"),
        help_text=_("Organization this person belongs to"),
    )
    officer_or_owner = models.CharField(
        max_length=100,
        verbose_name=_("Person Type"),
        help_text=_("Type of person (officer, owner)"),
        choices=[
            ("officer", _("Officer")),
            ("owner", _("Ultimate Beneficial Owner")),
        ],
    )

    # Identity
    first_name = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name=_("First Name"),
        help_text=_("First name of the person"),
    )
    last_name = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name=_("Last Name"),
        help_text=_("Last name of the person"),
    )
    birth_date = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("Birth Date"),
        help_text=_("Birth date of the person"),
    )
    gender = models.ForeignKey(
        "django_organizationatlas.OrganizationAtlasReferentiel",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="persons",
        limit_choices_to=Q(category__in=GENDER_CATEGORIES),
        verbose_name=_("Gender"),
        help_text=_("Gender or holding status of the person"),
    )

    class Meta:
        verbose_name = _("Person")
        verbose_name_plural = _("Persons")
        indexes = [
            models.Index(fields=["organization", "officer_or_owner"]),
        ]
        ordering = ["officer_or_owner", "-created_at"]

    def clean(self):
        if self.gender_id and self.gender.category not in GENDER_CATEGORIES:
            raise ValidationError(
                {"gender": _("Referentiel must belong to a gender category.")}
            )

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip() or "—"

    def __str__(self):
        return f"{self.organization.denomination} — {self.officer_or_owner} — {self.full_name}"
