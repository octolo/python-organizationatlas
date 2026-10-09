from django import forms
from django.utils.translation import gettext_lazy as _

from ..models.person import GENDER_CATEGORIES, OrganizationAtlasPerson
from ..models.reference import OrganizationAtlasReference


class OrganizationAtlasPersonForm(forms.ModelForm):
    """Form with radio buttons for choice fields."""

    officer_or_owner = forms.ChoiceField(
        choices=OrganizationAtlasPerson._meta.get_field('officer_or_owner').choices,
        widget=forms.RadioSelect,
        label=_("Person Type"),
    )
    gender = forms.ModelChoiceField(
        queryset=OrganizationAtlasReference.objects.filter(
            category__name__in=GENDER_CATEGORIES,
        ).order_by("category__name", "-priority"),
        widget=forms.RadioSelect,
        label=_("Gender"),
        required=False,
        empty_label=_("Not specified"),
    )

    class Meta:
        model = OrganizationAtlasPerson
        fields = '__all__'
