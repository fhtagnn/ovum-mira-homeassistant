from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import math
from typing import Any

# Do not integrate a long communication gap or Home Assistant downtime into energy.
MAX_INTEGRATION_GAP_SECONDS = 120.0
MIN_POWER_FOR_COP_KW = 0.05
MIN_ENERGY_FOR_RATIO_KWH = 0.01


def _clean_power(value: float | int | None) -> float:
    """Return a finite, non-negative power value in kW."""
    if value is None:
        return 0.0
    try:
        result = float(value)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(result) or result < 0:
        return 0.0
    return result


def _day_key(local_now: datetime) -> str:
    return local_now.date().isoformat()


def _week_key(local_now: datetime) -> str:
    iso = local_now.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


@dataclass(slots=True)
class EnergyAccumulator:
    """Integrate one WPM's power readings into persistent energy statistics.

    All energy values are kWh. Last sample data is deliberately not persisted so
    that Home Assistant downtime is never integrated as if the last known power
    had continued unchanged.
    """

    total_electrical_kwh: float = 0.0
    total_thermal_kwh: float = 0.0
    daily_electrical_kwh: float = 0.0
    daily_thermal_kwh: float = 0.0
    weekly_electrical_kwh: float = 0.0
    weekly_thermal_kwh: float = 0.0
    day_key: str = ""
    week_key: str = ""

    _last_utc: datetime | None = None
    _last_electrical_kw: float = 0.0
    _last_thermal_kw: float = 0.0

    def ensure_period(self, local_now: datetime) -> None:
        """Reset calendar-period counters when the local day/week changes."""
        day = _day_key(local_now)
        week = _week_key(local_now)
        if self.day_key != day:
            self.day_key = day
            self.daily_electrical_kwh = 0.0
            self.daily_thermal_kwh = 0.0
        if self.week_key != week:
            self.week_key = week
            self.weekly_electrical_kwh = 0.0
            self.weekly_thermal_kwh = 0.0

    def update(
        self,
        *,
        now_utc: datetime,
        local_now: datetime,
        electrical_kw: float | int | None,
        thermal_kw: float | int | None,
    ) -> None:
        """Integrate one sample using the trapezoidal rule.

        Samples further apart than MAX_INTEGRATION_GAP_SECONDS form a new
        baseline instead of filling an unknown gap.
        """
        electrical = _clean_power(electrical_kw)
        thermal = _clean_power(thermal_kw)
        self.ensure_period(local_now)

        if self._last_utc is not None:
            seconds = (now_utc - self._last_utc).total_seconds()
            if 0 < seconds <= MAX_INTEGRATION_GAP_SECONDS:
                hours = seconds / 3600.0
                electrical_delta = (self._last_electrical_kw + electrical) * 0.5 * hours
                thermal_delta = (self._last_thermal_kw + thermal) * 0.5 * hours
                self.total_electrical_kwh += electrical_delta
                self.total_thermal_kwh += thermal_delta
                self.daily_electrical_kwh += electrical_delta
                self.daily_thermal_kwh += thermal_delta
                self.weekly_electrical_kwh += electrical_delta
                self.weekly_thermal_kwh += thermal_delta

        self._last_utc = now_utc
        self._last_electrical_kw = electrical
        self._last_thermal_kw = thermal

    def set_baseline(
        self,
        *,
        now_utc: datetime,
        local_now: datetime,
        electrical_kw: float | int | None,
        thermal_kw: float | int | None,
    ) -> None:
        """Set a first sample without integrating any previous time gap."""
        self.ensure_period(local_now)
        self._last_utc = now_utc
        self._last_electrical_kw = _clean_power(electrical_kw)
        self._last_thermal_kw = _clean_power(thermal_kw)

    @property
    def instantaneous_cop(self) -> float | None:
        """Current thermal/electrical power ratio while meaningfully running."""
        if self._last_electrical_kw < MIN_POWER_FOR_COP_KW or self._last_thermal_kw <= 0:
            return None
        ratio = self._last_thermal_kw / self._last_electrical_kw
        return ratio if 0 <= ratio <= 20 else None

    @staticmethod
    def _ratio(thermal_kwh: float, electrical_kwh: float) -> float | None:
        if electrical_kwh < MIN_ENERGY_FOR_RATIO_KWH or thermal_kwh < 0:
            return None
        ratio = thermal_kwh / electrical_kwh
        return ratio if 0 <= ratio <= 20 else None

    @property
    def daily_work_factor(self) -> float | None:
        return self._ratio(self.daily_thermal_kwh, self.daily_electrical_kwh)

    @property
    def weekly_work_factor(self) -> float | None:
        return self._ratio(self.weekly_thermal_kwh, self.weekly_electrical_kwh)

    @property
    def total_work_factor(self) -> float | None:
        return self._ratio(self.total_thermal_kwh, self.total_electrical_kwh)

    def as_storage_dict(self) -> dict[str, Any]:
        """Serialize only persistent counters; transient samples are excluded."""
        data = asdict(self)
        data.pop("_last_utc", None)
        data.pop("_last_electrical_kw", None)
        data.pop("_last_thermal_kw", None)
        return data

    @classmethod
    def from_storage_dict(cls, data: dict[str, Any] | None) -> "EnergyAccumulator":
        if not isinstance(data, dict):
            return cls()
        allowed = {
            "total_electrical_kwh",
            "total_thermal_kwh",
            "daily_electrical_kwh",
            "daily_thermal_kwh",
            "weekly_electrical_kwh",
            "weekly_thermal_kwh",
            "day_key",
            "week_key",
        }
        clean = {key: value for key, value in data.items() if key in allowed}
        try:
            return cls(**clean)
        except (TypeError, ValueError):
            return cls()


class EnergyBook:
    """Energy accumulators for all configured WPM units."""

    def __init__(self, unit_ids: list[int]) -> None:
        self.by_unit: dict[int, EnergyAccumulator] = {
            unit_id: EnergyAccumulator() for unit_id in unit_ids
        }

    def load(self, data: dict[str, Any] | None) -> None:
        units = data.get("units", {}) if isinstance(data, dict) else {}
        for unit_id in list(self.by_unit):
            self.by_unit[unit_id] = EnergyAccumulator.from_storage_dict(
                units.get(str(unit_id)) if isinstance(units, dict) else None
            )

    def as_storage_dict(self) -> dict[str, Any]:
        return {
            "units": {
                str(unit_id): accumulator.as_storage_dict()
                for unit_id, accumulator in self.by_unit.items()
            }
        }

    def aggregate(self) -> EnergyAccumulator:
        """Return a read-only aggregate snapshot for multi-WPM installations."""
        result = EnergyAccumulator()
        if not self.by_unit:
            return result
        first = next(iter(self.by_unit.values()))
        result.day_key = first.day_key
        result.week_key = first.week_key
        for accumulator in self.by_unit.values():
            result.total_electrical_kwh += accumulator.total_electrical_kwh
            result.total_thermal_kwh += accumulator.total_thermal_kwh
            result.daily_electrical_kwh += accumulator.daily_electrical_kwh
            result.daily_thermal_kwh += accumulator.daily_thermal_kwh
            result.weekly_electrical_kwh += accumulator.weekly_electrical_kwh
            result.weekly_thermal_kwh += accumulator.weekly_thermal_kwh
            result._last_electrical_kw += accumulator._last_electrical_kw
            result._last_thermal_kw += accumulator._last_thermal_kw
        return result
