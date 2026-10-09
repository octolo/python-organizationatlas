from django import forms
from django.utils.translation import gettext_lazy as _


class ReferenceImportForm(forms.Form):
    csv_file = forms.FileField(
        label=_("CSV file"),
        help_text=_("Expected columns: category;code;description;country_code;source"),
    )
