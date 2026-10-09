from django import forms
from django.utils.translation import gettext_lazy as _

from ..models.virtuals.provider import OrganizationAtlasProviderModel


def organization_provider_choices():
    choices = []
    for provider in OrganizationAtlasProviderModel.objects.all():
        if getattr(provider, "abstract", False):
            continue
        label = getattr(provider, "display_name", None) or provider.name
        choices.append((provider.name, label))
    return choices


def organization_provider_initial(source, choices):
    if not source:
        return ""
    for value, label in choices:
        if source in (value, label):
            return value
    return ""


class OrganizationRefreshForm(forms.Form):
    provider = forms.ChoiceField(label=_("Provider"))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["provider"].choices = organization_provider_choices()
