from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from statistics import median
from typing import Iterable

from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .ovum_mira_modbus import WpmStatus

_STORAGE_VERSION = 1
_MAX_START_EVENTS = 12
_SLOPE_LOOKBACK = timedelta(hours=4)
_MIN_SLOPE_SPAN = timedelta(minutes=45)
_MIN_SLOPE_SAMPLES = 6
_MIN_COOLING_SLOPE_C_PER_HOUR = -0.01
_MAX_FORECAST = timedelta(hours=72)


@dataclass(slots=True)
class DhwStartEvent:
    timestamp_utc: str
    temperature_c: float | None


def _parse_timestamp(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def linear_regression_slope_c_per_hour(points: Iterable[tuple[datetime, float]]) -> float | None:
    """Return linear temperature slope in °C/hour for timestamped samples."""
    rows = list(points)
    if len(rows) < 2:
        return None
    origin = rows[0][0]
    xs = [(timestamp - origin).total_seconds() / 3600.0 for timestamp, _ in rows]
    ys = [float(value) for _, value in rows]
    x_mean = sum(xs) / len(xs)
    y_mean = sum(ys) / len(ys)
    denominator = sum((x - x_mean) ** 2 for x in xs)
    if denominator <= 0:
        return None
    return sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys, strict=True)) / denominator


def predict_crossing_time(
    *,
    now: datetime,
    current_temperature_c: float,
    trigger_temperature_c: float,
    slope_c_per_hour: float,
) -> datetime | None:
    """Linearly extrapolate when cooling reaches the learned DHW start temperature."""
    if slope_c_per_hour >= _MIN_COOLING_SLOPE_C_PER_HOUR:
        return None
    if current_temperature_c <= trigger_temperature_c:
        return now
    hours = (trigger_temperature_c - current_temperature_c) / slope_c_per_hour
    if hours < 0:
        return None
    delta = timedelta(hours=hours)
    if delta > _MAX_FORECAST:
        return None
    return now + delta


class DhwAnalytics:
    """Track DHW starts and derive a simple cooling-curve forecast."""

    def __init__(self, hass, entry_id: str) -> None:
        self._store: Store[dict] = Store(hass, _STORAGE_VERSION, f"{DOMAIN}.{entry_id}.dhw_analytics")
        self.start_events: list[DhwStartEvent] = []
        self._previous_hot_water_active: bool | None = None
        self.current_slope_c_per_hour: float | None = None
        self.predicted_next_start: datetime | None = None
        self.slope_samples_used: int = 0

    @property
    def last_start(self) -> datetime | None:
        if not self.start_events:
            return None
        return _parse_timestamp(self.start_events[-1].timestamp_utc)

    @property
    def estimated_trigger_temperature_c(self) -> float | None:
        temperatures = [event.temperature_c for event in self.start_events if event.temperature_c is not None]
        if not temperatures:
            return None
        return float(median(temperatures[-5:]))

    async def async_load(self) -> None:
        data = await self._store.async_load()
        if not isinstance(data, dict):
            return
        rows = data.get("start_events", [])
        if not isinstance(rows, list):
            return
        loaded: list[DhwStartEvent] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            timestamp = row.get("timestamp_utc")
            if _parse_timestamp(timestamp) is None:
                continue
            temperature = row.get("temperature_c")
            loaded.append(
                DhwStartEvent(
                    timestamp_utc=timestamp,
                    temperature_c=float(temperature) if isinstance(temperature, (int, float)) else None,
                )
            )
        self.start_events = loaded[-_MAX_START_EVENTS:]

    def initialize_live_state(self, system) -> None:
        """Set the current status baseline without creating a false start on HA startup."""
        self._previous_hot_water_active = self._is_hot_water_active(system)

    def update(self, system, history) -> None:
        now = dt_util.utcnow()
        active = self._is_hot_water_active(system)
        hot_water = system.hsm.hot_water
        temperature = hot_water.readings.primary_temperature if hot_water is not None else None

        if self._previous_hot_water_active is None:
            self._previous_hot_water_active = active
        elif active and not self._previous_hot_water_active:
            self.start_events.append(
                DhwStartEvent(
                    timestamp_utc=now.isoformat(),
                    temperature_c=float(temperature) if temperature is not None else None,
                )
            )
            self.start_events = self.start_events[-_MAX_START_EVENTS:]
            self._store.async_delay_save(self.as_storage_dict, 5)

        self._previous_hot_water_active = active
        self._update_forecast(now, temperature, active, history)

    def _update_forecast(self, now: datetime, current_temperature, active: bool, history) -> None:
        self.current_slope_c_per_hour = None
        self.predicted_next_start = None
        self.slope_samples_used = 0
        trigger = self.estimated_trigger_temperature_c
        if active or current_temperature is None or trigger is None:
            return

        cutoff = now - _SLOPE_LOOKBACK
        points: list[tuple[datetime, float]] = []
        for sample in history.samples:
            timestamp = _parse_timestamp(sample.timestamp_utc)
            if timestamp is None or timestamp < cutoff:
                continue
            if sample.dhw_temperature_c is None:
                continue
            # Exclude samples while any WPM explicitly reports DHW preparation.
            if any(row.get("status") == "hot_water" for row in sample.wpm):
                continue
            points.append((timestamp, float(sample.dhw_temperature_c)))

        if len(points) < _MIN_SLOPE_SAMPLES:
            return
        if points[-1][0] - points[0][0] < _MIN_SLOPE_SPAN:
            return

        slope = linear_regression_slope_c_per_hour(points)
        if slope is None:
            return
        self.current_slope_c_per_hour = slope
        self.slope_samples_used = len(points)
        self.predicted_next_start = predict_crossing_time(
            now=now,
            current_temperature_c=float(current_temperature),
            trigger_temperature_c=trigger,
            slope_c_per_hour=slope,
        )

    @staticmethod
    def _is_hot_water_active(system) -> bool:
        return any(wpm.readings.status == WpmStatus.HOT_WATER for wpm in system.wpms)

    def as_storage_dict(self) -> dict:
        return {
            "start_events": [
                {"timestamp_utc": event.timestamp_utc, "temperature_c": event.temperature_c}
                for event in self.start_events
            ]
        }

    async def async_save(self) -> None:
        await self._store.async_save(self.as_storage_dict())

    def diagnostics(self) -> dict:
        return {
            "last_start_utc": self.last_start.isoformat() if self.last_start else None,
            "estimated_trigger_temperature_c": self.estimated_trigger_temperature_c,
            "current_slope_c_per_hour": self.current_slope_c_per_hour,
            "predicted_next_start_utc": self.predicted_next_start.isoformat() if self.predicted_next_start else None,
            "slope_samples_used": self.slope_samples_used,
            "start_events": self.as_storage_dict()["start_events"],
        }
