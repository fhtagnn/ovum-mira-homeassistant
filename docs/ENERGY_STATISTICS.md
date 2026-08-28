# Energy and efficiency statistics

The integration derives energy from the MIRA WPM power registers already polled every 15 seconds.

For each configured WPM the integration exposes:

- electrical energy since tracking started
- thermal energy since tracking started
- electrical/thermal energy today
- electrical/thermal energy in the current ISO week (Monday-Sunday)
- instantaneous COP while the unit is meaningfully producing heat
- work factor for today, current week, and since tracking started
- compressor starts today and this week
- average compressor starts per day over the recent tracked seven-day window
- average runtime of completed compressor cycles

For multi-WPM installations, the existing aggregate total-energy and aggregate cycling sensors sum the currently configured WPM units.

## Operating-mode energy

Energy is additionally classified into four internal operating-mode buckets:

- `hot_water`
- `heating`
- `cooling`
- `other`

The public mode-energy sensors are installation-wide aggregates. Domestic-hot-water and heating electrical energy, thermal energy, and work factor are enabled by default. Cooling sensors are created disabled by default while real-world behavior is validated further. The `other` bucket remains visible so energy is never silently forced into a guessed useful mode.

Classification uses WPM status transitions. `START` and `STOPPING` inherit a clearly adjacent useful mode, and automatic `DEFROST` is attributed to the last clearly active useful mode when that context is available. `MANUAL_DEFROST`, ambiguous intervals, and energy that cannot be reconstructed during migration remain in `other`.

Mode work factors are accumulated energy ratios (`thermal kWh / electrical kWh`) and are therefore work factors, not instantaneous COP values.

## Calculation

Power in kW is integrated using a trapezoidal Riemann sum between successful Modbus polls. Gaps longer than 120 seconds are not filled, preventing Home Assistant downtime or communication outages from creating artificial energy.

Daily counters reset at local midnight. Weekly counters reset when the local ISO week changes. Persistent counters are saved in Home Assistant storage; the last live power/status sample is intentionally not persisted, so restart downtime is not integrated and a compressor already running at restart does not create a false new start.

A compressor start is counted only when an observed inactive state transitions into the compressor-active lifecycle. Transitions inside the active lifecycle, such as `HEATING -> DEFROST -> HEATING`, do not create additional starts. A cycle completes when the status returns to an explicitly inactive state. When the cumulative compressor-runtime register is usable across the observed cycle, its delta is preferred for cycle duration; otherwise the observed wall-clock interval is used.

## Storage schema and beta.2 migration

`0.1.0-beta.2` changes only the integration-managed energy store from schema version 1 to version 2. Existing authoritative total, daily, and weekly electrical/thermal counters are not replaced by reconstructed values.

When a version-1 store is loaded, the retained 14-day synchronized analysis history is replayed where possible to reconstruct mode allocation and recent compressor cycles. Because that history is sampled more coarsely than live energy integration, any difference between reconstructed mode energy and the existing authoritative counter is assigned to `other`. The migration maintains the invariant that the mode buckets sum to the pre-existing authoritative energy counter for each migrated period.

Temporarily unconfigured WPM records remain retained in storage and are restored if that WPM is configured again later.

## Accuracy caveat

OVUM describes the reported thermal power as not being a calibrated/verified heat-meter measurement. Therefore thermal energy and all COP/work-factor values calculated from it are monitoring/optimization estimates, not billing-grade measurements.

## Domestic-hot-water analytics

The synchronized history and status foundation is also used by the DHW analytics. See `DHW_ANALYTICS.md` for start detection, interval statistics, and prediction of the next DHW heating start.
