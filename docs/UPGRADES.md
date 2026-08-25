# Upgrade and data compatibility

This document defines the compatibility contract for updates of the OVUM MIRA integration from the public beta onward.

The goal is that an in-place integration update does not create new entities unnecessarily and does not discard data already collected by this integration.

## What is preserved during a normal update

When the existing OVUM MIRA config entry is kept, updates are expected to preserve:

- connection and installation configuration stored in the Home Assistant config entry;
- stable entity `unique_id` values;
- Home Assistant entity-registry associations and existing entity IDs;
- long-term statistics for the persistent energy sensors;
- accumulated electrical and thermal energy stored by the integration;
- the compact 14-day analysis history;
- persisted DHW start events used by the DHW analytics.

Reconfiguration of host, port, login code, or WPM count keeps the same Home Assistant config-entry ID. The integration's internal storage keys and entity unique IDs are based on that config-entry ID, so a normal reconfigure does not intentionally start a new data set.

## Internal storage compatibility contract

The public beta uses these Home Assistant storage keys:

```text
ovum_mira.<entry_id>.energy
ovum_mira.<entry_id>.analysis_history
ovum_mira.<entry_id>.dhw_analytics
```

All three currently use storage major version `1`.

These keys and versions are treated as persistent API. A future change to a storage schema must add an explicit migration before the version is changed. It must not silently fall back to an empty store when valid older data exists.

The test suite contains upgrade-compatibility fixtures that load data using the public-beta storage keys and verify that the current code still reads the accumulated energy, analysis history, and DHW events.

### WPM-count changes

Energy belonging to a temporarily unconfigured WPM is retained in storage. For example, changing an installation from two configured WPMs to one and later back to two must not erase the second WPM's accumulated integration energy merely because it was temporarily absent from the active configuration.

Inactive WPM data is retained but is not included in the live aggregate sensors while that WPM is not configured.

## Entity and Recorder compatibility

Entity `unique_id` values are also treated as persistent API. Changing an entity key can make Home Assistant treat it as a different entity, which can split Recorder history or long-term statistics.

For the energy totals, the following semantics are additionally part of the compatibility contract:

- device class: `energy`;
- unit: `kWh`;
- state class: `total_increasing`.

Changes to these values require explicit review because they can affect Home Assistant statistics and the Energy dashboard.

The test suite locks representative public-beta entity IDs and the energy-statistics metadata so accidental changes fail CI.

## Config-entry migrations

The Home Assistant config entry currently uses schema version `5`.

Schema version 5 separates connection data from physical installation settings in the Home Assistant-native way: host, port, WPM count, and login code remain in `ConfigEntry.data`, while sensor counts and optional installed components live in `ConfigEntry.options`.

`async_migrate_entry` updates older config-entry schemas in place. A version-4 entry is converted without changing its config-entry ID or unique ID, so the existing internal stores and entity registry associations remain attached. Existing option values take precedence over legacy copies in `data`, and unrelated future fields are preserved.

Config-entry schema migrations are separate from Recorder/history migration. The integration does not import old Powercalc/helper statistics from earlier prototype setups.

## Safe update procedure

For a normal HACS or manual update:

1. Keep the existing OVUM MIRA integration entry in **Settings → Devices & services**.
2. Update the integration files through HACS, or replace the custom-component files in place.
3. Restart Home Assistant when required by the update method.
4. Do not delete and recreate the OVUM MIRA config entry solely to apply an update.
5. After the update, verify that the existing energy entities and their long-term statistics continue rather than appearing as new entities.

Using the integration's **Reconfigure** or **Reauthenticate** flow is preferred over deleting and recreating the config entry when connection details or credentials change.

## Important limitation: deleting and recreating the config entry

The integration's internal stores are keyed by Home Assistant's config-entry ID. Deleting the OVUM MIRA config entry and adding it again creates a new entry ID, so the new entry will not automatically attach itself to the old internal stores.

Therefore, if preserving integration-managed energy and analysis data matters, do not delete the config entry as part of a routine upgrade.

A Home Assistant backup remains the recommended recovery path before major changes or manual storage edits.

## Release rule for future schema changes

Before a release may change any persistent storage schema, entity identity, or energy-statistics semantics, it should include:

- a fixture representing the previous released format;
- a migration or compatibility path in code;
- a test proving the previous data survives the upgrade;
- release notes calling out any unavoidable user-visible change.

If an old format cannot be migrated safely, the integration should fail clearly rather than silently overwrite valid stored data.
