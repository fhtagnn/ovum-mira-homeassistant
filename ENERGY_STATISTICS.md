# Energy and efficiency statistics (v0.5)

v0.5 derives energy from the MIRA WPM power registers already polled every 15 seconds.

For each WPM the integration exposes:

- electrical energy since the integration started tracking it
- thermal energy since tracking started
- electrical/thermal energy today
- electrical/thermal energy in the current ISO week (Monday-Sunday)
- instantaneous COP while the unit is meaningfully producing heat
- work factor for today, current week, and since tracking started

The energy sensors use `device_class: energy`, `kWh`, and `state_class: total_increasing`, making them suitable for Home Assistant long-term statistics. The electrical total can also be selected as an individual-device consumption source in the Energy dashboard.

## Calculation

Power in kW is integrated using a trapezoidal Riemann sum between successful Modbus polls. Gaps longer than 120 seconds are not filled, preventing Home Assistant downtime or communication outages from creating artificial energy.

Daily counters reset at local midnight. Weekly counters reset when the local ISO week changes (Monday start). Counters and accumulated totals are persisted in Home Assistant storage; the last power sample is intentionally not persisted, so restart downtime is not integrated.

## Accuracy caveat

OVUM describes the reported thermal power as not being a calibrated/verified heat-meter measurement. Therefore thermal energy and all COP/work-factor values calculated from it are monitoring/optimization estimates, not billing-grade measurements.

## Warm-water prediction

Prediction of the next domestic-hot-water charging cycle is intentionally not included yet. v0.5 establishes the persistent time-series and energy foundation first. A later version can derive DHW cycle events from WPM state plus DHW temperature dynamics and build a prediction from those events.
