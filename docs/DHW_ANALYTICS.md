# DHW analytics

The OVUM WPM status code `HOT_WATER` is used as the authoritative signal for domestic-hot-water preparation.

## Last start

A start event is created on a transition from any non-`HOT_WATER` state to `HOT_WATER`. The event timestamp and the primary DHW temperature at the start are stored persistently. A Home Assistant restart while DHW is already active does not create a false start event.

## Heating-interval statistics

The integration derives the interval between consecutive observed DHW heating starts. An interval is considered valid only when:

- it is at least 2 hours and at most 72 hours long;
- synchronized analysis history covers the full interval;
- no history gap inside the interval exceeds 2 minutes.

This intentionally rejects intervals where Home Assistant may have been offline long enough to miss an intermediate DHW start. Manual or unusual short recharges below 2 hours and very long exceptional gaps above 72 hours are also excluded.

The latest 10 valid intervals are considered. Once at least 2 valid intervals are available, the arithmetic mean is exposed as the normal average-heating-interval sensor. The median is available as a diagnostic sensor and is disabled by default.

These interval statistics are observational only; they do not change MIRA settings or trigger DHW preparation.

## Forecast

The forecast deliberately uses a simple explainable model:

1. Learn the switch-on temperature as the median of the latest five observed start temperatures.
2. Take synchronized DHW temperature samples from the last four hours.
3. Exclude samples recorded while any WPM is in `HOT_WATER`.
4. Fit a straight line by least-squares regression.
5. If the line is cooling, extrapolate to the learned switch-on temperature.

The result is unavailable until at least one real start event exists and enough cooling samples have accumulated. Forecasts beyond 72 hours are hidden.

The prediction is expected to react to circulation-pump activity: increased circulation causes a steeper negative temperature slope and therefore an earlier predicted next DHW start. That makes the derived sensors useful for tuning circulation schedules, but the prediction is not intended for safety or control of the heat pump itself.

### Optional holiday-mode heuristic

OVUM does not expose a holiday-mode status or its end time through the Modbus interface supported by this integration. A low effective DHW target can be used as a **heuristic for an assumed holiday mode**, not as an authoritative controller-reported status.

Open **Settings → Devices & services → OVUM MIRA → Configure** to set:

- **Infer holiday mode from the DHW target**: disabled by default; enable it only if low effective DHW targets indicate a period when the normal next-start forecast should be paused.
- **Holiday-mode target threshold (°C)**: configurable from 0 to 60 °C, with 15 °C suggested initially. It has no effect while detection is disabled. Choose a value at or above your holiday target and below your normal operating targets.

The comparison uses the **effective target temperature**, never the measured tank temperature or only the user-configured normal target. With detection enabled:

| Effective DHW target | Inference | Next-start forecast |
| --- | --- | --- |
| At or below the threshold | Assumed holiday mode | Paused; no predicted timestamp |
| Above the threshold | Holiday mode not inferred | Allowed, subject to the usual data requirements |
| Missing or non-finite | Unknown | Paused until a valid target is available |

For example, a 15 °C threshold pauses the prediction when the effective target is reduced from 50 °C to 10 °C. The prediction is recalculated once the target rises above 15 °C; it is not a prediction of when holiday mode will end. Previously learned start temperatures are retained. The inference is recomputed from live data after a Home Assistant restart.

Only the predicted next-start timestamp is suppressed. Temperature history, cooling-slope calculation, actual DHW start events, interval statistics and energy accounting continue normally. No controller settings are changed, no additional registers are read or written, and no holiday schedule is programmed. In particular, observed long intervals during a holiday can still contribute to the existing interval statistics if they meet the normal validity criteria.

**Limitations:** a time program, manual setback or other low-target setting can trigger the same heuristic. A holiday setting above the threshold will not be detected. The integration cannot distinguish these causes or know when the normal target will return. This inferred state must not be treated as a safety signal or reliable proof that a home is unoccupied.

The predicted-next-start sensor exposes these attributes, also included in the `dhw_analytics` diagnostics section:

- `holiday_target_threshold_c`: the configured threshold, or `null` when detection is disabled.
- `holiday_mode_inferred`: `true` or `false` for a valid comparison; `null` when detection is disabled or the target is unknown.
- `forecast_suppression_reason`: `holiday_mode_inferred` or `effective_target_missing`; otherwise `null`. A `null` reason does not guarantee a forecast: normal requirements such as sufficient cooling samples still apply.

While paused, the forecast entity has no timestamp (Home Assistant displays `unknown`), rather than a misleading prediction of "now". Automations consuming the forecast should handle this missing-value state.
