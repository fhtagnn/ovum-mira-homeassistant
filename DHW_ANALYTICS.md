# DHW analytics

The OVUM WPM status code `HOT_WATER` is used as the authoritative signal for hot-water preparation.

## Last start

A start event is created on a transition from any non-`HOT_WATER` state to `HOT_WATER`. The event timestamp and the primary DHW temperature at the start are stored persistently. A Home Assistant restart while DHW is already active does not create a false start event.

## Forecast

The forecast deliberately uses a simple explainable model:

1. Learn the switch-on temperature as the median of the latest five observed start temperatures.
2. Take synchronized DHW temperature samples from the last four hours.
3. Exclude samples recorded while any WPM is in `HOT_WATER`.
4. Fit a straight line by least-squares regression.
5. If the line is cooling, extrapolate to the learned switch-on temperature.

The result is unavailable until at least one real start event exists and enough cooling samples have accumulated. Forecasts beyond 72 hours are hidden.

The prediction is expected to react to circulation-pump activity: increased circulation causes a steeper negative temperature slope and therefore an earlier predicted next DHW start. That makes the derived sensors useful for tuning circulation schedules, but the prediction is not intended for safety or control of the heat pump itself.
