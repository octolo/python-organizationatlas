from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

from ..managers.reference import FEATURE_CATEGORY


class OrganizationAtlasFeatureManager(models.Model):
    """Permission level of one feature for one role on one organization.

    A higher level includes the lower ones.
    """

    class Role(models.TextChoices):
        ADMIN = "ADMIN", _("Administrator")
        MANAGER = "MANAGER", _("Manager")
        USER = "USER", _("User")

    class Level(models.IntegerChoices):
        NONE = 0, _("No access")
        INVOLVED = 10, _("Only the data concerning me")
        VIEWER = 20, _("Read all data")
        CONTRIBUTOR = 30, _("Create and edit")
        EXPORTER = 40, _("Export data")
        MANAGER = 50, _("Full management")

    organization = models.ForeignKey(
        "django_organizationatlas.OrganizationAtlasOrganization",
        on_delete=models.CASCADE,
        related_name="feature_managers",
        verbose_name=_("Organization"),
        help_text=_("Organization this feature belongs to"),
    )
    feature = models.ForeignKey(
        "django_organizationatlas.OrganizationAtlasReference",
        on_delete=models.CASCADE,
        related_name="feature_managers",
        limit_choices_to={"category__name": FEATURE_CATEGORY},
        verbose_name=_("Feature"),
        help_text=_("Reference tagged as a feature"),
    )
    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        verbose_name=_("Role"),
        help_text=_("Role this configuration applies to"),
    )
    enabled = models.BooleanField(
        default=True,
        verbose_name=_("Enabled"),
        help_text=_("Whether this feature is enabled for the role"),
    )
    level = models.PositiveSmallIntegerField(
        choices=Level.choices,
        default=Level.VIEWER,
        verbose_name=_("Level"),
        help_text=_(
            "10 involved, 20 viewer, 30 contributor, 40 exporter, 50 manager. "
            "A higher level includes the lower ones."
        ),
    )

    class Meta:
        verbose_name = _("Feature manager")
        verbose_name_plural = _("Feature managers")
        ordering = ["organization", "feature", "role"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "feature", "role"],
                name="unique_organization_feature_role",
            ),
        ]

    def has_level(self, level: int) -> bool:
        return bool(self.enabled) and self.level >= level

    @property
    def can_read(self) -> bool:
        return self.has_level(self.Level.INVOLVED)

    @property
    def involved_only(self) -> bool:
        return bool(self.enabled) and self.level == self.Level.INVOLVED

    @property
    def can_view(self) -> bool:
        return self.has_level(self.Level.VIEWER)

    @property
    def can_contribute(self) -> bool:
        return self.has_level(self.Level.CONTRIBUTOR)

    @property
    def can_export(self) -> bool:
        return self.has_level(self.Level.EXPORTER)

    @property
    def can_manage(self) -> bool:
        return self.has_level(self.Level.MANAGER)

    def clean(self):
        super().clean()
        if self.feature_id and self.feature.category.name != FEATURE_CATEGORY:
            raise ValidationError(
                {"feature": _("Reference must belong to the 'feature' category.")}
            )

    def __str__(self):
        return f"{self.organization} - {self.feature} - {self.role}"
