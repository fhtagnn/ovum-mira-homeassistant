# Changelog

## Unreleased

### Changed
- Added explicit upgrade/data-compatibility tests for config-entry data, internal storage, entity identity, and energy-statistics metadata.
- Preserve accumulated energy data for temporarily unconfigured WPM units so reducing and later restoring the configured WPM count does not erase their stored totals.
- Documented the supported in-place upgrade path and compatibility guarantees.

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
