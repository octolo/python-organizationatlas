# django-organizationatlas

Django integration for organizationatlas: models, admin and the search-then-create flow.

## Installation

```bash
pip install django-organizationatlas
```

## Requirements

Python 3.11+ and Django 5.0+ (CI covers Django 5.0, 5.1 and 5.2).

## Organization data files

`ORGANIZATIONATLAS_DATA_FILE_STORAGE` selects an alias from Django's
`STORAGES` setting. It defaults to `default` and is resolved when models load.
`ORGANIZATIONATLAS_DATA_FILE_UPLOAD_TO` accepts a relative path with Django's
usual date formatting, or a callable taking `(instance, filename)`. It defaults
to `organizationatlas/data/%Y/%m/`.

```python
ORGANIZATIONATLAS_DATA_FILE_STORAGE = 'organization_data'
ORGANIZATIONATLAS_DATA_FILE_UPLOAD_TO = 'organizations/%Y/%m/'
```

Configure the `organization_data` alias in `STORAGES` before starting Django.
Changing either setting does not move existing files; changing the storage
also requires making existing files available in the new storage.

Reference categories have a `unique` flag, enabled by default. The built-in
visual identity category is created with it disabled through `for_name`.
Data types may optionally belong to a reference category. For a unique
category, saving an active data row closes other active rows for the same
organization and data type. For other categories, saving an active row with
`main=True` clears `main` on the other active rows of that type. A row is
active when its end date is empty or later than today. Data types without a
category retain the existing per-source open-row behavior.
When a matching category is added after uncategorized provider data already
exists for that country, the existing type remains uncategorized until it is
explicitly associated or migrated.

The transition is rejected if it would close a future period before it
starts. Changing a category or making it unique is rejected when existing
active rows conflict. Create and update data through model `save()`; bulk
creation and bulk updates of validity, identity or `main` are not supported.

## Duplicating an organization

An existing provider result offers **Duplicate Organization** to users with
organization add permission. It creates a separate organization from the
provider result, not a copy of local changes, relationships or documents.
The duplicate retains the official code and country, receives a distinct
named ID and is marked as a duplicate. The original remains unique per
country and code. Duplicates are independent organizations, not isolated
test environments.

The `refresh` and `load_history` commands accept `--organization-id` to select
one organization when several share a code. Selecting by `--code` reports an
ambiguity instead of choosing one. Bulk operations include duplicates.

The organization admin shows the count beside the duplicate indicator. It
counts all organizations with the same exact code, including the current row
and organizations in other countries. Click the count to see those
organizations, or use the shared-code filter to list all shared or unique
codes. The count remains global when the list is searched or filtered.

## Multi-provider refresh and tasks

The organization admin refresh form accepts multiple providers. Leave the
selection empty to use all providers supporting reference lookup in the
organization's country. The same operation can be called from Python:

```python
from django_organizationatlas.services.refresh import (
    preferred_data,
    refresh_from_providers,
)

result = refresh_from_providers(organization, ['insee', 'inpi'])
values = preferred_data(organization)
french_activity = values.get(('FR', 'ape'))
```

The result contains `refreshed` provider names and `errors`. Refresh merges
provider observations into one current data row per type and country. The
row's `source` is the winning provider; `metadata["provider_observations"]`
retains each provider's value and known validity date. The winner is selected
by the most recent known provider validity date, then provider priority.
Missing dates remain unknown; missing fields and failed providers do not
delete previous observations. Changes on the same day replace that day's
value. Existing duplicate rows are not deleted or closed automatically; if
they prevent a merge, an error is reported. `preferred_data` selects the best
current row for each `(country_code, data_type)` pair, using the data row's
country code, including `XX` for manual entries. Search results are checked
against the organization's identifiers; its code and source are not replaced.
The organization admin displays these preferred rows read-only in its main
section for users permitted to view data. File-backed rows show the file name.

For display and database ordering, annotate data with
`OrganizationAtlasData.objects.with_start_at().order_by('start_at')`.
`start_at` is `valid_from` when known, otherwise the local date of
`created_at`. The admin and timeline mark the latter as recorded, not as a
confirmed validity date. Supplying `valid_from` later automatically updates
the displayed date and its position. This fallback does not affect provider
ranking or change stored validity dates.

Providers offering history are queried for dates; their response is retained
in the history trace. This does not import historical periods: use the
separate Load history action for that. When both task actions are selected,
refresh runs before history import. Headquarters candidates are tracked by
source and selected with the same date and priority rule. Provider failures
are logged and reported without stopping the other providers.
Existing provider source names are reused. If both the provider's name and
display name already exist as source labels, resolve the ambiguity before
refreshing that provider.

To enqueue a refresh of every organization:

```python
from django_organizationatlas.task.refresh import (
    enqueue_refresh_all_organizations,
)

enqueue_refresh_all_organizations()  # All applicable providers.
enqueue_refresh_all_organizations(['insee', 'inpi'])
enqueue_refresh_all_organizations(actions=['history'])
enqueue_refresh_all_organizations(actions=['refresh', 'history'])
```

The default action is `refresh`. `history` imports available historical
periods; when both are selected, the history response is reused for refresh.
An ambiguous conflict with existing current data is reported rather than
overwriting that data. Person, document and event tasks are not yet supported.

`ORGANIZATIONATLAS_TASK_BACKEND` selects `sync` (default), `thread`, `celery`,
or `rq`. Install the matching optional Celery or RQ dependency when needed.
Celery workers must import `django_organizationatlas.task.celery`; RQ uses its
default queue. No periodic schedule is created automatically. The all-
organizations task attempts every organization and fails after completion if
any provider or organization failed. Generic work can also be submitted with
`get_task_backend().enqueue(callable, *args, **kwargs)`; asynchronous callables
must be importable by workers.

## Reference codes and data values

### Reference library

Library files ending in `_ref.csv` contain references; files ending in
`_cat.csv` contain categories. The reference and category admin pages each
offer **Import from library**, limited to their respective files.
The category lists include every category used in the corresponding folder.
Blank category descriptions do not overwrite existing descriptions.
Category CSVs accept `unique` values `true` and `false`. A missing or blank
value preserves an existing setting, or uses the category default on creation.

Built-in category names are human-readable. Provider data keys such as `ape`
remain unchanged and are matched to their built-in category names, such as
`APE code`. Imports also recognize the former built-in category names.
Databases that already applied the previous initial migration must be
recreated or manually adapted, including their existing category names and
the new fields and global country code `XG`; changing the initial migration
does not update those databases.

External CSV imports keep their existing behavior: the management command
identifies categories by their columns, and the reference admin upload imports
references regardless of filename.

### Visual identity and files

The built-in `Visual identity` references include `logo`, `favicon`, `font`,
`primary_color` and `secondary_color`. Use the organization's **Add data**
action to enter them. Logos and favicons use the `image` value type, fonts use
`file`, and colors remain text values. Each reference has a separate data type,
so multiple identity elements can coexist.

For `image` and `file` data, store the upload in `file` and leave `value` empty;
other data types use `value` and must not include a file. `typed_value` returns
the Django `FieldFile` for file-backed data. Images are validated by Pillow;
SVG is not supported. Other file types are not content-validated. Files use
Django's configured default storage and are not deleted automatically when a
record is replaced or deleted, because historical records may refer to them.
Configure media storage and URLs appropriately and serve untrusted uploads from
a separate domain; uploaded files must not be trusted as executable content.
Other references can use file uploads by first creating a corresponding data
type with value type `file` or `image`.

Reference codes are compared after trimming, removing periods and converting
to uppercase. This applies to every reference category; underscores and other
characters are preserved. For example, `62.01Z` and `6201z` both become
`6201Z`. `display_code` retains the form used for display.

Known string-coded data values are stored using the reference's `display_code`.
Values with a non-string data type are not converted.
Reference lookup uses the data type, country and display value. If there is no
country-specific category, the global `XG` category is used.
For manually entered data, the organization's country is used instead of the
`XX` source marker. Provider data is linked to a matching value reference when
created or refreshed; unknown values remain unchanged without a link.
Importing references later reconciles existing matching display values but does
not automatically link existing data. Refreshing provider data can add the link.

`default_value` remains separate from the display code. Rules such as
`ORDINARY_MAJORITY` can have a default of `50%` and an explicitly linked data
value of `66%`. Reference category, code and display code cannot be changed
while the reference is used by data.
Some built-in French company rules use `to complete` as a placeholder, not a
verified legal value.

The current initial migration defines the schema but does not normalize data
in existing databases. Existing deployments need an explicit data conversion
and collision resolution before using normalized codes. Existing direct
queries on `Reference.code` must use the normalized uppercase form. Reference
CSV imports accept an optional `display_code`, and exports include
`display_code` and `default_value`.
