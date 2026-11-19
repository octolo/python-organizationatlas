# Audit statique — reste

Date : 2026-11-19

Les écarts qui ne passaient pas (code mort, complexité ≥ 11, maintenabilité < 20, redondance des lecteurs CSV, ruff BLE001 / B904 / DJ001 / DJ007 / DJ008 / UP035) sont corrigés. Ce fichier ne garde que ce qui est encore ouvert.

Les champs texte `source`, `country_code`, `short_denomination` et `website` n'acceptent plus `NULL`. La migration correspondante n'a pas été générée.

---

## Complexité sous le seuil (rang B, CC 8 à 10)

| CC | Symbole |
|---|---|
| 10 | `OrganizationAtlasOrganizationAdmin.load_history`, `person_name_from_description` |
| 9 | `refresh`, `_history_rows_from_result`, `_iter_data_fields`, `_upsert_data`, `typed_value`, `import_reference_from_path`, `_build_address_str`, `_current_headquarters_siret` |
| 8 | `add_reference_data`, `_refresh_address`, `_save_history_row`, `apply_organization_history`, `Command.handle`, `OrganizationAtlasSourceBase.save`, `get_csv_paths`, `import_reference_rows`, `_build_address_json`, `address_payload`, `principal_from_establishments`, `street_line`, `_history_from_periods` |

D'autres blocs sont en rang B entre 6 et 7.

---

## Ruff, non retenu comme défaut métier

| Nombre | Règle | Lecture |
|---|---|---|
| 132 | RUF012 | Listes mutables des classes admin et modèles. Idiome Django |
| 21 | I001 | Imports non triés |
| 6 | RUF022 | `__all__` non trié |
| 35 | ARG002 | Arguments de signature imposés (`request` admin, `raw` / `kwargs` des providers) |
| 1 | B018 | `self.typed_value` dans `models/data.py` : l'accès sert à valider |
| 1 | DJ012 | `models/feature.py` : `__str__` est déclaré après `clean` |
| 1 | PLR0911 | `typed_value` |
| 1 | PLR0913 | `_build_address_str` |
