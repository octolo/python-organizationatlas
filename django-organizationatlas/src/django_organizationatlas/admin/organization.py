from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.html import escape, format_html, format_html_join
from django.utils.http import urlencode
from django.utils.translation import gettext_lazy as _
from django_boosted import AdminBoostModel, admin_boost_view, get_current_user
from virtualqueryset.queryset import VirtualQuerySet

from .history import with_history

from ..category_names import category_name
from ..fields import RichTextField
from ..forms.organization import (
    ADD_ORGANIZATION_DATA_READONLY,
    OrganizationHistoryForm,
    OrganizationRefreshForm,
    add_organization_data_form,
    reference_data_type,
)
from ..reference_codes import normalize_reference_code
from ..services.history import load_history_from_providers
from ..services.refresh import preferred_data, refresh_from_providers
from ..task.history import enqueue_load_one_organization_history
from ..task.refresh import enqueue_refresh_one_organization
from ..models.data import OrganizationAtlasData, OrganizationAtlasDataType
from ..models.organization import ORGANIZATIONATLAS_FIELDS_COMPANY, OrganizationAtlasOrganization
from ..models.reference import OrganizationAtlasReference
from ..models.source import (
    ORGANIZATIONATLAS_FIELDS_AUDIT,
    ORGANIZATIONATLAS_FIELDS_SOURCE,
    USER_COUNTRY_CODE,
)
from ..models.virtuals.organization import OrganizationAtlasVirtualOrganization
from .address import OrganizationAtlasAddressInline
from .timeline import timeline_entries, timeline_groups
from .data import OrganizationAtlasDataInline
from .feature import OrganizationAtlasFeatureManagerInline
from .person import OrganizationAtlasPersonInline
from .related_object import OrganizationAtlasRelatedObjectInline
from .relation import OrganizationAtlasOrganizationRelationInline

class _AddDataReferenceListAdmin:
    """Serve the add-data reference list through the reference admin filters."""

    def __init__(self, model_admin, queryset):
        self._model_admin = model_admin
        self._queryset = queryset

    def get_queryset(self, request):
        return self._queryset.all()

    def __getattr__(self, name):
        return getattr(self._model_admin, name)


def _add_data_reference_changelist(request, model_admin, queryset, list_display):
    list_admin = _AddDataReferenceListAdmin(model_admin, queryset)
    change_list_class = model_admin.get_changelist(request)
    arguments = [
        request,
        OrganizationAtlasReference,
        list_display,
        None,
        model_admin.get_list_filter(request),
        None,
        model_admin.get_search_fields(request),
        False,
        model_admin.list_per_page,
        model_admin.list_max_show_all,
        (),
        list_admin,
        model_admin.get_sortable_by(request),
        model_admin.search_help_text,
    ]
    changelist = change_list_class(*arguments)
    changelist.formset = None
    return changelist


class SameCodeFilter(admin.SimpleListFilter):
    title = _('Shared code')
    parameter_name = 'shared_code'

    def lookups(self, request, model_admin):
        return (
            ('yes', _('Shared by multiple organizations')),
            ('no', _('Used by one organization')),
        )

    def queryset(self, request, queryset):
        if self.value() == 'yes':
            return queryset.filter(sql_same_code_count__gt=1)
        if self.value() == 'no':
            return queryset.filter(sql_same_code_count=1)
        return queryset


@admin.register(OrganizationAtlasOrganization)
class OrganizationAtlasOrganizationAdmin(with_history(AdminBoostModel)):
    list_display = [
        'denomination_display',
        'duplicate_display',
        "headquarters_address_display",
        "created_at",
    ]
    list_display_links = ['denomination_display']
    list_filter = [SameCodeFilter, "created_at"]
    search_fields = ["denomination", "abbreviation", "code", "to_organizationatlasdata__value"]
    readonly_fields = [
        "named_id",
        'is_duplicate',
        'preferred_data_display',
        *ORGANIZATIONATLAS_FIELDS_AUDIT,
        "source_label",
    ]
    inlines = [
        OrganizationAtlasDataInline,
        OrganizationAtlasAddressInline,
        OrganizationAtlasPersonInline,
        OrganizationAtlasFeatureManagerInline,
        OrganizationAtlasOrganizationRelationInline,
        OrganizationAtlasRelatedObjectInline,
    ]

    def has_change_permission(self, request, obj=None):
        return admin.ModelAdmin.has_change_permission(self, request, obj)

    def get_queryset(self, request):
        return (
            super().get_queryset(request)
            .with_headquarters()
            .with_same_code_count()
        )

    @admin.display(description=_('Denomination'), ordering='denomination')
    def denomination_display(self, obj):
        return self.format_with_help_text(
            escape(obj.denomination),
            obj.code,
        )

    @admin.display(description=_('Duplicate'), ordering='is_duplicate')
    def duplicate_display(self, obj):
        url = reverse(
            'admin:django_organizationatlas_organizationatlasorganization_changelist',
            current_app=self.admin_site.name,
        )
        return format_html(
            '{} <a href="{}?{}">{}</a>',
            self.boolean_icon_html(obj.is_duplicate),
            url,
            urlencode({'code__exact': obj.code}),
            obj.sql_same_code_count,
        )

    def get_search_results(self, request, queryset, search_term):
        queryset, use_distinct = super().get_search_results(request, queryset, search_term)
        return queryset.distinct(), use_distinct

    def changelist_view(self, request, extra_context=None):
        response = super().changelist_view(request, extra_context)
        context = getattr(response, 'context_data', None)
        if not context or 'cl' not in context:
            return response
        changelist = context['cl']
        virtual_admin = self.admin_site._registry[OrganizationAtlasVirtualOrganization]
        if (
            changelist.query.strip()
            and not changelist.result_count
            and not changelist.is_popup
            and virtual_admin.has_view_permission(request)
        ):
            url = reverse(
                'admin:django_organizationatlas_'
                'organizationatlasvirtualorganization_changelist',
                current_app=self.admin_site.name,
            )
            search_url = f'{url}?{urlencode({"q": changelist.query})}'
            messages.info(
                request,
                format_html(
                    '{} <a href="{}">{}</a>',
                    _('No organization found.'),
                    search_url,
                    _('Search external organizations to create one.'),
                ),
            )
        return response

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        if isinstance(db_field, RichTextField):
            kwargs.setdefault("required", False)
        return super().formfield_for_dbfield(db_field, request, **kwargs)

    def get_fieldsets(self, request, obj=None):
        fieldsets = super().get_fieldsets(request, obj)
        inline = OrganizationAtlasDataInline(self.model, self.admin_site)
        if obj is not None and inline.has_view_or_change_permission(
            request, obj,
        ):
            return fieldsets
        return [
            (
                name,
                {
                    **options,
                    'fields': [
                        field
                        for field in options['fields']
                        if field != 'preferred_data_display'
                    ],
                },
            )
            for name, options in fieldsets
        ]

    def change_fieldsets(self):
        self.add_to_fieldset(
            None,
            [
                *ORGANIZATIONATLAS_FIELDS_COMPANY,
                'is_duplicate',
                'preferred_data_display',
            ],
        )
        self.add_to_fieldset(_("Source"), ORGANIZATIONATLAS_FIELDS_SOURCE)

    @admin.display(description=_('Preferred data'))
    def preferred_data_display(self, obj):
        if not obj or not obj.pk:
            return '-'
        rows = preferred_data(obj)
        if not rows:
            return '-'
        items = format_html_join(
            '',
            '<li><strong>{} / {}</strong>: {} ({})</li>',
            (
                (
                    country or '-',
                    name,
                    row.file.name if row.file else row.value,
                    row.source_label(),
                )
                for (country, name), row in sorted(rows.items())
            ),
        )
        return format_html('<ul>{}</ul>', items)

    def headquarters_address_display(self, obj: OrganizationAtlasOrganization) -> str:
        prefetched = getattr(obj, "prefetched_headquarters", None)
        if prefetched:
            return str(prefetched[0].address)
        return "-"
    headquarters_address_display.short_description = _("Headquarters Address")

    @admin_boost_view("list", _("Actions"), requires_object=True, permission="change")
    def organization_actions(self, request, obj):
        rows = []
        for name, label in (
            ("refresh", _("Refresh")),
            ("add_data_references", _("Add data")),
            ("load_history", _("Load history")),
        ):
            row = OrganizationAtlasOrganization(denomination=str(label))
            row.action_url = self._organization_admin_url(name, obj.pk)
            rows.append(row)

        def action_link(item):
            return format_html('<a href="{}">{}</a>', item.action_url, item.denomination)
        action_link.short_description = _("Action")

        return {
            "queryset": VirtualQuerySet(model=OrganizationAtlasOrganization, data=rows),
            "list_display": [action_link],
            "actions_on_top": False,
            "actions_on_bottom": False,
        }

    @admin_boost_view("adminform", _("Refresh"), hidden=True)
    def refresh(self, request, obj, form=None):
        if not self.has_change_permission(request, obj):
            raise PermissionDenied
        if request.method == "POST" and form is not None and form.is_valid():
            providers = form.cleaned_data["providers"]
            if form.cleaned_data["enqueue"]:
                try:
                    enqueue_refresh_one_organization(obj.pk, providers)
                except RuntimeError as exc:
                    messages.error(request, str(exc))
                    return {"form": form}
                messages.success(request, _("Organization refresh queued."))
            else:
                result = refresh_from_providers(obj, providers)
                for error in result["errors"]:
                    messages.warning(request, error)
                if not result["refreshed"]:
                    messages.error(request, _("Organization refresh failed."))
                    return {"form": form}
                messages.success(request, _("Organization refreshed."))
            url = reverse(
                "admin:django_organizationatlas_organizationatlasorganization_change",
                args=[obj.pk],
            )
            return {"redirect_url": url}
        return {"form": OrganizationRefreshForm()}

    @admin_boost_view("adminform", _("Load history"), permission="change", hidden=True)
    def load_history(self, request, obj, form=None):
        if not self.has_change_permission(request, obj):
            raise PermissionDenied
        if request.method == "POST" and form is not None and form.is_valid():
            providers = form.cleaned_data["providers"]
            if form.cleaned_data["enqueue"]:
                try:
                    enqueue_load_one_organization_history(obj.pk, providers)
                except RuntimeError as exc:
                    messages.error(request, str(exc))
                    return {"form": form}
                messages.success(request, _("Organization history load queued."))
            else:
                result = load_history_from_providers(obj, providers)
                for error in result["errors"]:
                    messages.warning(request, error)
                if not result["processed"]:
                    messages.error(request, _("Organization history load failed."))
                    return {"form": form}
                messages.success(request, _("Organization history loaded."))
            url = reverse(
                "admin:django_organizationatlas_organizationatlasorganization_change",
                args=[obj.pk],
            )
            return {"redirect_url": url}
        return {"form": OrganizationHistoryForm()}

    @admin_boost_view(
        "message",
        _("Timeline"),
        template_name="django_organizationatlas/timeline.html",
    )
    def timeline(self, request, obj):
        return {"groups": timeline_groups(timeline_entries(obj))}

    @admin_boost_view("redirect", _("Data"))
    def list_data(self, request, obj):
        url = reverse("admin:django_organizationatlas_organizationatlasdata_changelist")
        return f"{url}?organization_id={obj.pk}"

    @admin_boost_view("redirect", _("Address"))
    def list_address(self, request, obj):
        url = reverse("admin:django_organizationatlas_organizationatlasaddress_changelist")
        return f"{url}?organization_id={obj.pk}"

    @admin_boost_view("redirect", _("Relations"))
    def list_relations(self, request, obj):
        url = reverse("admin:django_organizationatlas_organizationatlasorganizationrelation_changelist")
        return f"{url}?from_organization_id={obj.pk}"

    @admin_boost_view("message", _("Search Organization"))
    def search_organization(self, request):
        return redirect("admin:django_organizationatlas_organizationatlasvirtualorganization_changelist")

    def _organization_admin_url(self, name, *args, query=None):
        opts = self.model._meta
        url = reverse(
            f"admin:{opts.app_label}_{opts.model_name}_{name}",
            args=args,
            current_app=self.admin_site.name,
        )
        if query:
            return f"{url}?{query}"
        return url

    def _deny_data_change(self, request, obj):
        if self.has_change_permission(request, obj):
            return None
        messages.error(request, _("You do not have permission to add data."))
        return redirect(self._organization_admin_url("change", obj.pk))

    def _save_added_data(
        self,
        request,
        obj,
        *,
        data_type_name,
        value,
        file=None,
        value_type='str',
        main=False,
        valid_from=None,
        valid_to=None,
        reference=None,
    ):
        max_length = OrganizationAtlasDataType._meta.get_field("data_type").max_length
        if len(data_type_name) > max_length:
            messages.error(request, _("Data type name is too long."))
            return None
        try:
            data_type = (
                OrganizationAtlasDataType.objects.for_reference(reference)
                if reference
                else OrganizationAtlasDataType.for_key(
                    data_type_name, value_type,
                )
            )
        except (ValueError, ValidationError) as exc:
            messages.error(request, str(exc))
            return None
        row = OrganizationAtlasData(
            organization=obj,
            data_type=data_type,
            value=value,
            file=file,
            main=main,
            valid_from=valid_from,
            valid_to=valid_to,
        )
        user = get_current_user()
        if user is not None and user.is_authenticated and user.pk:
            row.source = row._manual_source(user)
            row.country_code = USER_COUNTRY_CODE
        try:
            row.clean()
            normalize = reference is None or (
                reference.category.name == category_name(data_type_name)
                and not reference.default_value
                and normalize_reference_code(value) == reference.code
            )
            row.save(normalize_reference=normalize)
        except ValidationError as exc:
            for message in exc.messages:
                messages.error(request, message)
            return None
        except IntegrityError:
            messages.error(
                request,
                _("An open data of this type already exists for this organization."),
            )
            return None
        if reference is not None:
            row.reference.add(reference)
        messages.success(request, _("Data added."))
        return self._organization_admin_url("change", obj.pk)

    @admin_boost_view(
        "list",
        _("Add data"),
        requires_object=True,
        permission="change",
        hidden=True,
    )
    def add_data_references(self, request, obj):
        denied = self._deny_data_change(request, obj)
        if denied is not None:
            return denied
        queryset = OrganizationAtlasReference.objects.select_related("category")
        reference_admin = self.admin_site._registry[OrganizationAtlasReference]

        def reference_code(reference):
            return reference.display_code
        reference_code.short_description = _("Code")

        def reference_description(reference):
            return reference.description
        reference_description.short_description = _("Description")

        def reference_category(reference):
            return str(reference.category) if reference.category_id else ""
        reference_category.short_description = _("Category")

        def add_reference_button(reference):
            url = self._organization_admin_url(
                "add_reference_data",
                obj.pk,
                query=f"reference={reference.pk}",
            )
            return format_html('<a class="button" href="{}">{}</a>', url, _("Add"))
        add_reference_button.short_description = _("Add")

        list_display = [
            reference_code,
            reference_description,
            reference_category,
            add_reference_button,
        ]
        return {
            "queryset": queryset,
            "list_display": list_display,
            "cl": _add_data_reference_changelist(
                request,
                reference_admin,
                queryset,
                list_display,
            ),
            "actions_on_top": False,
            "actions_on_bottom": False,
        }

    @admin_boost_view(
        "adminform",
        _("Add"),
        requires_object=True,
        permission="change",
        hidden=True,
    )
    def add_reference_data(self, request, obj, form=None):
        denied = self._deny_data_change(request, obj)
        if denied is not None:
            return denied
        try:
            reference_id = int(request.GET.get("reference") or "")
        except (TypeError, ValueError):
            reference_id = None
        reference = None
        if reference_id is not None:
            reference = (
                OrganizationAtlasReference.objects.select_related(
                    "category",
                    "source_category",
                )
                .with_usage_count()
                .filter(pk=reference_id)
                .first()
            )
        list_url = self._organization_admin_url("add_data_references", obj.pk)
        if reference is None:
            messages.error(request, _("Unknown reference."))
            return redirect(list_url)
        if request.method == "POST" and form is not None and form.is_valid():
            data_type_name, value_type = reference_data_type(reference)
            saved_url = self._save_added_data(
                request,
                obj,
                data_type_name=data_type_name,
                value=form.cleaned_data.get('value', ''),
                file=form.cleaned_data.get('file'),
                value_type=value_type,
                main=form.cleaned_data.get('main', False),
                valid_from=form.cleaned_data["valid_from"],
                valid_to=form.cleaned_data["valid_to"],
                reference=reference,
            )
            return {"redirect_url": saved_url or list_url}
        add_form = add_organization_data_form(reference)
        return {
            "form": add_form,
            "readonly_fields": ADD_ORGANIZATION_DATA_READONLY,
            'has_file_field': add_form.is_multipart(),
        }
