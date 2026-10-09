"""Rich text widget is chosen from settings."""

from django.forms import Textarea, TextInput

from django_organizationatlas.fields import RichTextField
from django_organizationatlas.models import OrganizationAtlasOrganization


def test_richtext_widget_defaults_to_textarea():
    form_field = RichTextField().formfield()
    assert isinstance(form_field.widget, Textarea)


def test_richtext_widget_from_settings(settings):
    settings.ORGANIZATIONATLAS_RICHTEXT_WIDGET = "django.forms.TextInput"
    form_field = RichTextField().formfield()
    assert isinstance(form_field.widget, TextInput)


def test_organization_resume_uses_richtext_field():
    field = OrganizationAtlasOrganization._meta.get_field("resume")
    assert isinstance(field, RichTextField)
    assert field.blank is True
    assert field.null is True
