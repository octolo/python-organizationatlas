from django.db import models
from django.utils.translation import gettext_lazy as _

from ...managers.virtuals.document import OrganizationAtlasVirtualDocumentManager


class OrganizationAtlasVirtualDocument(models.Model):
    """Virtual document model for organizationatlas."""

    objects = OrganizationAtlasVirtualDocumentManager()

    class Meta:
        managed = False
        verbose_name = _("Virtual Document")
        verbose_name_plural = _("Virtual Documents")

    def __str__(self):
        return str(self.pk) if self.pk is not None else str(self._meta.verbose_name)

