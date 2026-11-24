from django import forms
from django.contrib.admin.widgets import AdminDateWidget, FilteredSelectMultiple
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from ..models.data import OrganizationAtlasDataType
from ..models.virtuals.provider import OrganizationAtlasProviderModel
from ..visual_identity import visual_identity_data_type


def reference_data_type(reference):
    """Resolve the data key and value type used by a reference."""
    return OrganizationAtlasDataType.objects.reference_data_type(reference)


def organization_provider_choices():
    choices = []
    for provider in OrganizationAtlasProviderModel.objects.all():
        if getattr(provider, "abstract", False):
            continue
        if not getattr(provider, "has_search_organization_by_reference", False):
            continue
        label = getattr(provider, "display_name", None) or provider.name
        choices.append((provider.name, label))
    return choices


class OrganizationRefreshForm(forms.Form):
    providers = forms.MultipleChoiceField(
        label=_("Providers"),
        required=False,
        help_text=_("Leave empty to use all available providers."),
        widget=FilteredSelectMultiple(_('Providers'), is_stacked=False),
    )
    enqueue = forms.BooleanField(
        label=_("Run as a task"),
        required=False,
        help_text=_("Queue the operation instead of running it now."),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["providers"].choices = organization_provider_choices()


def history_provider_choices():
    choices = []
    for provider in OrganizationAtlasProviderModel.objects.all():
        if getattr(provider, "abstract", False):
            continue
        if not getattr(provider, "has_get_organization_history", False):
            continue
        label = getattr(provider, "display_name", None) or provider.name
        choices.append((provider.name, label))
    return choices


ADD_ORGANIZATION_DATA_READONLY = (
    "category",
    "source_category",
    "code",
    "description",
    "default_value",
    "characteristics",
    "priority",
    "country_code",
    "source",
    "used_count",
)


class AddOrganizationDataForm(forms.Form):
    category = forms.CharField(required=False, label=_("Category"))
    source_category = forms.CharField(required=False, label=_("Source category"))
    code = forms.CharField(required=False, label=_("Code"))
    description = forms.CharField(required=False, label=_("Description"))
    default_value = forms.CharField(required=False, label=_("Default value"))
    characteristics = forms.CharField(required=False, label=_("Characteristics"))
    priority = forms.CharField(required=False, label=_("Priority"))
    country_code = forms.CharField(required=False, label=_("Country Code"))
    source = forms.CharField(required=False, label=_("Source"))
    used_count = forms.CharField(required=False, label=_("Used count"))
    value = forms.CharField(label=_("Value"))
    file = forms.FileField(label=_('File'), required=False)
    main = forms.BooleanField(label=_('Main'), required=False)
    valid_from = forms.DateField(
        required=False,
        label=_("Valid from"),
        help_text=_("Date from which the information is valid (depuis)"),
        widget=AdminDateWidget,
    )
    valid_to = forms.DateField(
        required=False,
        label=_("Valid to"),
        help_text=_(
            "Date until which the information was valid (jusqu'au, empty = still current)"
        ),
        widget=AdminDateWidget,
    )

    def __init__(self, *args, reference=None, **kwargs):
        if reference is not None:
            default = (reference.default_value or "").strip()
            source_category = (
                reference.source_category if reference.source_category_id else ""
            )
            kwargs["initial"] = {
                "category": reference.category if reference.category_id else "",
                "source_category": source_category,
                "code": reference.code,
                "description": reference.description,
                "default_value": reference.default_value,
                "characteristics": reference.characteristics,
                "priority": str(reference.priority),
                "country_code": reference.country_code,
                "source": reference.source,
                "used_count": str(getattr(reference, "sql_used_count", 0)),
                "value": default or reference.display_code,
                "valid_from": timezone.localdate(),
            }
        super().__init__(*args, **kwargs)
        identity = visual_identity_data_type(reference) if reference else None
        value_type = reference_data_type(reference)[1] if reference else 'str'
        if reference and reference.category.unique:
            self.fields.pop('main')
        if value_type in {'image', 'file'}:
            self.fields.pop('value')
            field_class = forms.ImageField if value_type == 'image' else forms.FileField
            self.fields['file'] = field_class(label=_('File'))
        else:
            self.fields.pop('file')
            if identity:
                self.initial['value'] = ''
        for name in ADD_ORGANIZATION_DATA_READONLY:
            self.fields[name].disabled = True

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get("valid_from")
        end = cleaned.get("valid_to")
        if start and end and end < start:
            self.add_error(
                "valid_to",
                _("'Valid to' cannot be earlier than 'Valid from'."),
            )
        return cleaned


def add_organization_data_form(reference):
    """Form class closed over the reference so a POST rebind keeps the details."""

    class ReferenceDataForm(AddOrganizationDataForm):
        def __init__(self, *args, **kwargs):
            kwargs["reference"] = reference
            super().__init__(*args, **kwargs)

    return ReferenceDataForm()


class OrganizationHistoryForm(forms.Form):
    providers = forms.MultipleChoiceField(
        label=_("Providers"),
        required=False,
        help_text=_("Leave empty to use all available providers."),
        widget=FilteredSelectMultiple(_("Providers"), is_stacked=False),
    )
    enqueue = forms.BooleanField(
        label=_("Run as a task"),
        required=False,
        help_text=_("Queue the operation instead of running it now."),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["providers"].choices = history_provider_choices()
