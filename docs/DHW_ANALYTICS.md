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
