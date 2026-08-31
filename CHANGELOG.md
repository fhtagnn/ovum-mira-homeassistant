# Changelog

## Unreleased

### Added
- Opt-in two-restart migration for 14 legacy OVUM Modbus entities and two Powercalc energy entities.
- Persistent migration diagnostics, including active legacy sources, energy-total imports, per-entity Recorder actions, and archived duplicate statistic IDs.

### Changed
- Recorder state-history migration now runs atomically in the Recorder queue. Existing target state rows are merged, while continuous legacy statistics keep their metadata and overlapping target statistics are retained under unique archive IDs.
- Legacy `migrate_legacy` config-entry data is preserved as an option during schema migration instead of being discarded.

## 0.1.0-beta.2 - 2026-08-31

### Added
- Operating-mode energy accounting for domestic hot water, heating, cooling, and an unclassified/other bucket.
- Installation-wide domestic-hot-water and heating electrical energy, thermal energy, and work-factor sensors.
- Cooling energy/work-factor sensors, disabled by default until more real installations have been validated.
- Compressor cycling metrics: starts today, starts this week, rolling starts-per-day statistic, and average completed-cycle runtime.
- Domestic-hot-water average heating interval plus a diagnostic median interval sensor.

### Changed
- Energy storage schema moves from version 1 to version 2 with an explicit migration path.
- Version-1 authoritative total, daily, and weekly energy counters remain unchanged during migration. Available analysis history is replayed to reconstruct operating-mode energy; any unreconstructable residual is assigned to the unclassified/other bucket.
- Temporarily unconfigured WPM records continue to be retained in storage and are excluded from live aggregates until re-enabled.
- Diagnostics now report the integration version consistently with the beta.2 code version.
- Added and expanded upgrade/data-compatibility tests for storage migration, entity identity, and energy-statistics metadata.

### Compatibility
- Existing total energy entity unique IDs and long-term-statistics semantics are unchanged.
- The config-entry schema remains version 5; this release changes only the integration-managed energy store schema.
- No legacy Recorder or Powercalc statistics migration is performed.

## 0.1.0-beta.1

Initial public beta.

### Added
- Local Modbus TCP communication with OVUM MIRA.
- Config flow and configurable installation topology.
- Heating circuit and domestic hot water control.
- Buffer, temperature, and WPM monitoring.
- Electrical and thermal energy statistics.
- COP and performance statistics.
- Domestic hot water cycle analytics and linear next-start prediction.
- Diagnostics and synchronized analysis history.
- English and German translations.
- HACS metadata and HACS/Hassfest GitHub Actions.
- Apache-2.0 licensing, contribution and security documentation, and AI-assisted development disclosure.

The earlier development builds were internal prototypes and are not part of the public release history.
