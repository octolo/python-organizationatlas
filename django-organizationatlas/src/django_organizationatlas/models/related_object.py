"""Link an organization to any other Django model."""

from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils.translation import gettext_lazy as _
from django_boosted import AuditMixin


class OrganizationAtlasRelatedObject(AuditMixin):
    """Link an organization to any other Django model."""

    organization = models.ForeignKey(
        "django_organizationatlas.OrganizationAtlasOrganization",
        on_delete=models.CASCADE,
        related_name="to_organizationatlasrelatedobject",
        verbose_name=_("Organization"),
        help_text=_("Organization to which this object is related"),
    )
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        verbose_name=_("Content Type"),
        help_text=_("Type of the related object"),
    )
    object_id = models.CharField(
        max_length=255,
        verbose_name=_("Object ID"),
        help_text=_("ID of the related object (integer pk as well as UUID)"),
    )
    content_object = GenericForeignKey("content_type", "object_id")
    object_str = models.CharField(
        editable=False,
        max_length=500,
        verbose_name=_("Object String Representation"),
        help_text=_(
            "String representation of the related object (saved for reference if object is deleted)"
        ),
    )
    comment = models.TextField(
        blank=True,
        default="",
        verbose_name=_("Comment"),
        help_text=_("Internal comment or note"),
    )

    class Meta:
        verbose_name = _("Related Object")
        verbose_name_plural = _("Related Objects")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["content_type", "object_id"]),
        ]

    def save(self, *args, **kwargs):
        if self.object_id is not None:
            self.object_id = str(self.object_id).replace("-", "")
        if self.content_object:
            self.object_str = str(self.content_object)[:500]
        super().save(*args, **kwargs)

    def __str__(self):
        target = self.object_str or f"{self.content_type} #{self.object_id}"
        return f"{self.organization} -> {target}"
