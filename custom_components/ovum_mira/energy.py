from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
import math
from typing import Any, Callable, Iterable

from .ovum_mira_modbus import WpmStatus

# Do not integrate a long communication gap or Home Assistant downtime into energy.
MAX_INTEGRATION_GAP_SECONDS = 120.0
MIN_POWER_FOR_COP_KW = 0.05
MIN_ENERGY_FOR_RATIO_KWH = 0.01
START_HISTORY_DAYS = 14

MODE_HOT_WATER = "hot_water"
MODE_HEATING = "heating"
MODE_COOLING = "cooling"
MODE_OTHER = "other"
ENERGY_MODES = (MODE_HOT_WATER, MODE_HEATING, MODE_COOLING, MODE_OTHER)

_USEFUL_MODE_BY_STATUS = {
    WpmStatus.HOT_WATER: MODE_HOT_WATER,
    WpmStatus.HEATING: MODE_HEATING,
    WpmStatus.COOLING: MODE_COOLING,
}
_ACTIVE_STATUSES = {
    WpmStatus.START,
    WpmStatus.HOT_WATER,
    WpmStatus.HEATING,
    WpmStatus.COOLING,
    WpmStatus.DEFROST,
    WpmStatus.MANUAL_DEFROST,
    WpmStatus.STOPPING,
}


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


def _clean_runtime(value: float | int | None) -> float | None:
    """Return a finite, non-negative cumulative compressor runtime in minutes."""
    if value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(result) or result < 0:
        return None
    return result


def _day_key(local_now: datetime) -> str:
    return local_now.date().isoformat()


def _week_key(local_now: datetime) -> str:
    iso = local_now.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def _status_from_history(value: Any) -> WpmStatus | None:
    """Convert the compact history status representation back to WpmStatus."""
    if isinstance(value, WpmStatus):
        return value
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    for status in WpmStatus:
        if status.name.lower() == normalized:
            return status
    return None


def is_compressor_active(status: WpmStatus | None) -> bool:
    """Return whether a WPM status belongs to one observed compressor cycle."""
    return status in _ACTIVE_STATUSES if status is not None else False


def classify_interval_mode(
    previous_status: WpmStatus | None,
    current_status: WpmStatus | None,
    last_useful_mode: str | None,
) -> tuple[str, str | None]:
    """Classify an interval and return the updated remembered useful mode.

    The interval is represented by its two endpoint statuses. Explicit useful
    modes take precedence. START and STOPPING inherit the useful mode from the
    opposite endpoint or the immediately preceding useful mode. Automatic
    defrost inherits the most recent useful mode; manual defrost stays in the
    conservative ``other`` bucket.
    """
    previous_mode = _USEFUL_MODE_BY_STATUS.get(previous_status)
    current_mode = _USEFUL_MODE_BY_STATUS.get(current_status)

    remembered = last_useful_mode
    if previous_mode is not None:
        remembered = previous_mode

    if previous_status == WpmStatus.MANUAL_DEFROST or current_status == WpmStatus.MANUAL_DEFROST:
        mode = MODE_OTHER
    elif current_mode is not None:
        mode = current_mode
    elif previous_mode is not None:
        mode = previous_mode
    elif previous_status == WpmStatus.START and current_status in _USEFUL_MODE_BY_STATUS:
        mode = _USEFUL_MODE_BY_STATUS[current_status]
    elif current_status == WpmStatus.START and previous_status in _USEFUL_MODE_BY_STATUS:
        mode = _USEFUL_MODE_BY_STATUS[previous_status]
    elif previous_status == WpmStatus.DEFROST or current_status == WpmStatus.DEFROST:
        mode = remembered if remembered in {MODE_HOT_WATER, MODE_HEATING, MODE_COOLING} else MODE_OTHER
    elif previous_status == WpmStatus.STOPPING or current_status == WpmStatus.STOPPING:
        mode = remembered if remembered in {MODE_HOT_WATER, MODE_HEATING, MODE_COOLING} else MODE_OTHER
    elif previous_status == WpmStatus.START or current_status == WpmStatus.START:
        mode = remembered if remembered in {MODE_HOT_WATER, MODE_HEATING, MODE_COOLING} else MODE_OTHER
    else:
        mode = MODE_OTHER

    if current_mode is not None:
        remembered = current_mode
    elif current_status not in {WpmStatus.START, WpmStatus.DEFROST, WpmStatus.STOPPING}:
        # A clearly non-useful state ends the inheritance chain. Unknown status is
        # handled by callers conservatively and is not passed here for live data.
        remembered = None

    return mode, remembered


@dataclass(slots=True)
class ModeEnergyAccumulator:
    """Persistent energy counters for one operating-mode bucket."""

    total_electrical_kwh: float = 0.0
    total_thermal_kwh: float = 0.0
    daily_electrical_kwh: float = 0.0
    daily_thermal_kwh: float = 0.0
    weekly_electrical_kwh: float = 0.0
    weekly_thermal_kwh: float = 0.0

    def reset_daily(self) -> None:
        self.daily_electrical_kwh = 0.0
        self.daily_thermal_kwh = 0.0

    def reset_weekly(self) -> None:
        self.weekly_electrical_kwh = 0.0
        self.weekly_thermal_kwh = 0.0

    def add(self, electrical_kwh: float, thermal_kwh: float) -> None:
        self.total_electrical_kwh += electrical_kwh
        self.total_thermal_kwh += thermal_kwh
        self.daily_electrical_kwh += electrical_kwh
        self.daily_thermal_kwh += thermal_kwh
        self.weekly_electrical_kwh += electrical_kwh
        self.weekly_thermal_kwh += thermal_kwh

    @property
    def total_work_factor(self) -> float | None:
        return EnergyAccumulator._ratio(self.total_thermal_kwh, self.total_electrical_kwh)

    def as_storage_dict(self) -> dict[str, float]:
        return asdict(self)

    @classmethod
    def from_storage_dict(cls, data: Any) -> "ModeEnergyAccumulator":
        if not isinstance(data, dict):
            return cls()
        clean: dict[str, float] = {}
        for key in (
            "total_electrical_kwh",
            "total_thermal_kwh",
            "daily_electrical_kwh",
            "daily_thermal_kwh",
            "weekly_electrical_kwh",
            "weekly_thermal_kwh",
        ):
            value = data.get(key)
            if isinstance(value, (int, float)) and math.isfinite(float(value)) and float(value) >= 0:
                clean[key] = float(value)
        return cls(**clean)


def _mode_accumulators() -> dict[str, ModeEnergyAccumulator]:
    return {mode: ModeEnergyAccumulator() for mode in ENERGY_MODES}


@dataclass(slots=True)
class EnergyAccumulator:
    """Integrate one WPM's power readings into persistent energy statistics."""

    total_electrical_kwh: float = 0.0
    total_thermal_kwh: float = 0.0
    daily_electrical_kwh: float = 0.0
    daily_thermal_kwh: float = 0.0
    weekly_electrical_kwh: float = 0.0
    weekly_thermal_kwh: float = 0.0
    day_key: str = ""
    week_key: str = ""
    modes: dict[str, ModeEnergyAccumulator] = field(default_factory=_mode_accumulators)

    compressor_starts_total: int = 0
    compressor_starts_today: int = 0
    compressor_starts_week: int = 0
    start_counts_by_day: dict[str, int] = field(default_factory=dict)
    completed_cycle_runtime_minutes_total: float = 0.0
    completed_cycles: int = 0

    _last_utc: datetime | None = None
    _last_electrical_kw: float = 0.0
    _last_thermal_kw: float = 0.0
    _last_status: WpmStatus | None = None
    _last_useful_mode: str | None = None
    _compressor_active: bool | None = None
    _cycle_start_utc: datetime | None = None
    _cycle_start_runtime_minutes: float | None = None

    def ensure_period(self, local_now: datetime) -> None:
        """Reset calendar-period counters when the local day/week changes."""
        day = _day_key(local_now)
        week = _week_key(local_now)
        if self.day_key != day:
            self.day_key = day
            self.daily_electrical_kwh = 0.0
            self.daily_thermal_kwh = 0.0
            self.compressor_starts_today = 0
            for bucket in self.modes.values():
                bucket.reset_daily()
        if self.week_key != week:
            self.week_key = week
            self.weekly_electrical_kwh = 0.0
            self.weekly_thermal_kwh = 0.0
            self.compressor_starts_week = 0
            for bucket in self.modes.values():
                bucket.reset_weekly()
        # Record zero-start days as observed days so the rolling average does not
        # silently ignore days on which the compressor never started.
        self.start_counts_by_day.setdefault(day, 0)
        self._prune_start_history(local_now.date())

    def update(
        self,
        *,
        now_utc: datetime,
        local_now: datetime,
        electrical_kw: float | int | None,
        thermal_kw: float | int | None,
        status: WpmStatus | None = None,
        compressor_runtime_minutes: float | int | None = None,
    ) -> None:
        """Integrate one sample using the trapezoidal rule."""
        electrical = _clean_power(electrical_kw)
        thermal = _clean_power(thermal_kw)
        runtime = _clean_runtime(compressor_runtime_minutes)
        self.ensure_period(local_now)

        seconds: float | None = None
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
                mode, remembered = classify_interval_mode(
                    self._last_status,
                    status,
                    self._last_useful_mode,
                )
                self.modes[mode].add(electrical_delta, thermal_delta)
                self._last_useful_mode = remembered
            elif seconds > MAX_INTEGRATION_GAP_SECONDS:
                # A long gap invalidates transition-based cycle inference and mode
                # inheritance. Establish a new live baseline without fabricating a
                # start or cycle duration.
                self._compressor_active = is_compressor_active(status) if status is not None else None
                self._cycle_start_utc = None
                self._cycle_start_runtime_minutes = None
                self._last_useful_mode = _USEFUL_MODE_BY_STATUS.get(status)

        if status is not None and seconds is not None and 0 < seconds <= MAX_INTEGRATION_GAP_SECONDS:
            self._update_cycle_state(
                now_utc=now_utc,
                local_now=local_now,
                status=status,
                runtime_minutes=runtime,
            )
        elif self._compressor_active is None and status is not None:
            self._compressor_active = is_compressor_active(status)

        self._last_utc = now_utc
        self._last_electrical_kw = electrical
        self._last_thermal_kw = thermal
        if status is not None:
            self._last_status = status
            useful = _USEFUL_MODE_BY_STATUS.get(status)
            if useful is not None:
                self._last_useful_mode = useful

    def set_baseline(
        self,
        *,
        now_utc: datetime,
        local_now: datetime,
        electrical_kw: float | int | None,
        thermal_kw: float | int | None,
        status: WpmStatus | None = None,
        compressor_runtime_minutes: float | int | None = None,
    ) -> None:
        """Set a first sample without integrating or counting a phantom start."""
        self.ensure_period(local_now)
        self._last_utc = now_utc
        self._last_electrical_kw = _clean_power(electrical_kw)
        self._last_thermal_kw = _clean_power(thermal_kw)
        self._last_status = status
        self._last_useful_mode = _USEFUL_MODE_BY_STATUS.get(status)
        self._compressor_active = is_compressor_active(status) if status is not None else None
        self._cycle_start_utc = None
        self._cycle_start_runtime_minutes = _clean_runtime(compressor_runtime_minutes) if self._compressor_active else None

    def _update_cycle_state(
        self,
        *,
        now_utc: datetime,
        local_now: datetime,
        status: WpmStatus,
        runtime_minutes: float | None,
    ) -> None:
        active = is_compressor_active(status)
        if self._compressor_active is None:
            self._compressor_active = active
            return
        if active and not self._compressor_active:
            self._record_start(local_now)
            self._cycle_start_utc = now_utc
            self._cycle_start_runtime_minutes = runtime_minutes
        elif not active and self._compressor_active:
            if self._cycle_start_utc is not None:
                duration_minutes: float | None = None
                if (
                    runtime_minutes is not None
                    and self._cycle_start_runtime_minutes is not None
                    and runtime_minutes >= self._cycle_start_runtime_minutes
                ):
                    runtime_delta = runtime_minutes - self._cycle_start_runtime_minutes
                    if runtime_delta > 0:
                        duration_minutes = runtime_delta
                if duration_minutes is None:
                    wall_minutes = (now_utc - self._cycle_start_utc).total_seconds() / 60.0
                    if wall_minutes > 0:
                        duration_minutes = wall_minutes
                if duration_minutes is not None:
                    self.completed_cycle_runtime_minutes_total += duration_minutes
                    self.completed_cycles += 1
            self._cycle_start_utc = None
            self._cycle_start_runtime_minutes = None
        self._compressor_active = active

    def _record_start(self, local_now: datetime) -> None:
        day = _day_key(local_now)
        self.compressor_starts_total += 1
        self.compressor_starts_today += 1
        self.compressor_starts_week += 1
        self.start_counts_by_day[day] = self.start_counts_by_day.get(day, 0) + 1
        self._prune_start_history(local_now.date())

    def _prune_start_history(self, today: date) -> None:
        cutoff = today - timedelta(days=START_HISTORY_DAYS)
        kept: dict[str, int] = {}
        for key, count in self.start_counts_by_day.items():
            try:
                parsed = date.fromisoformat(key)
            except ValueError:
                continue
            if parsed >= cutoff and isinstance(count, int) and count >= 0:
                kept[key] = count
        self.start_counts_by_day = kept

    @property
    def average_starts_per_day_7d(self) -> float | None:
        if not self.day_key:
            return None
        try:
            today = date.fromisoformat(self.day_key)
        except ValueError:
            return None
        # Rolling seven calendar days including today. Only days actually observed
        # by this integration are used, so a fresh installation is not diluted by
        # invented pre-installation zeroes.
        days = [today - timedelta(days=offset) for offset in range(7)]
        tracked = [
            self.start_counts_by_day[day.isoformat()]
            for day in days
            if day.isoformat() in self.start_counts_by_day
        ]
        if not tracked:
            return None
        return sum(tracked) / len(tracked)

    @property
    def average_cycle_runtime_minutes(self) -> float | None:
        if self.completed_cycles <= 0:
            return None
        return self.completed_cycle_runtime_minutes_total / self.completed_cycles

    @property
    def instantaneous_cop(self) -> float | None:
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
        """Serialize persistent counters only; live samples remain transient."""
        return {
            "total_electrical_kwh": self.total_electrical_kwh,
            "total_thermal_kwh": self.total_thermal_kwh,
            "daily_electrical_kwh": self.daily_electrical_kwh,
            "daily_thermal_kwh": self.daily_thermal_kwh,
            "weekly_electrical_kwh": self.weekly_electrical_kwh,
            "weekly_thermal_kwh": self.weekly_thermal_kwh,
            "day_key": self.day_key,
            "week_key": self.week_key,
            "modes": {mode: bucket.as_storage_dict() for mode, bucket in self.modes.items()},
            "cycles": {
                "compressor_starts_total": self.compressor_starts_total,
                "compressor_starts_today": self.compressor_starts_today,
                "compressor_starts_week": self.compressor_starts_week,
                "start_counts_by_day": dict(self.start_counts_by_day),
                "completed_cycle_runtime_minutes_total": self.completed_cycle_runtime_minutes_total,
                "completed_cycles": self.completed_cycles,
            },
        }

    @classmethod
    def from_storage_dict(cls, data: dict[str, Any] | None) -> "EnergyAccumulator":
        if not isinstance(data, dict):
            return cls()
        scalar_keys = {
            "total_electrical_kwh",
            "total_thermal_kwh",
            "daily_electrical_kwh",
            "daily_thermal_kwh",
            "weekly_electrical_kwh",
            "weekly_thermal_kwh",
            "day_key",
            "week_key",
        }
        clean = {key: value for key, value in data.items() if key in scalar_keys}
        try:
            result = cls(**clean)
        except (TypeError, ValueError):
            result = cls()

        mode_data = data.get("modes", {})
        if isinstance(mode_data, dict):
            result.modes = {
                mode: ModeEnergyAccumulator.from_storage_dict(mode_data.get(mode))
                for mode in ENERGY_MODES
            }

        cycles = data.get("cycles", {})
        if isinstance(cycles, dict):
            for key in (
                "compressor_starts_total",
                "compressor_starts_today",
                "compressor_starts_week",
                "completed_cycles",
            ):
                value = cycles.get(key)
                if isinstance(value, int) and value >= 0:
                    setattr(result, key, value)
            runtime = cycles.get("completed_cycle_runtime_minutes_total")
            if isinstance(runtime, (int, float)) and math.isfinite(float(runtime)) and float(runtime) >= 0:
                result.completed_cycle_runtime_minutes_total = float(runtime)
            starts = cycles.get("start_counts_by_day")
            if isinstance(starts, dict):
                result.start_counts_by_day = {
                    str(key): int(value)
                    for key, value in starts.items()
                    if isinstance(key, str) and isinstance(value, int) and value >= 0
                }
        return result


class EnergyBook:
    """Energy accumulators for all configured WPM units."""

    def __init__(self, unit_ids: list[int]) -> None:
        self.by_unit: dict[int, EnergyAccumulator] = {
            unit_id: EnergyAccumulator() for unit_id in unit_ids
        }
        self._retained_units: dict[str, Any] = {}

    def load(self, data: dict[str, Any] | None) -> None:
        units = data.get("units", {}) if isinstance(data, dict) else {}
        if not isinstance(units, dict):
            units = {}

        configured_unit_keys = {str(unit_id) for unit_id in self.by_unit}
        self._retained_units = {
            str(unit_id): deepcopy(value)
            for unit_id, value in units.items()
            if str(unit_id) not in configured_unit_keys
        }
        for unit_id in list(self.by_unit):
            self.by_unit[unit_id] = EnergyAccumulator.from_storage_dict(units.get(str(unit_id)))

    def as_storage_dict(self) -> dict[str, Any]:
        units = deepcopy(self._retained_units)
        units.update(
            {
                str(unit_id): accumulator.as_storage_dict()
                for unit_id, accumulator in self.by_unit.items()
            }
        )
        return {"units": units}

    def aggregate(self) -> EnergyAccumulator:
        """Return a read-only aggregate snapshot for active WPM units."""
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
            result.compressor_starts_total += accumulator.compressor_starts_total
            result.compressor_starts_today += accumulator.compressor_starts_today
            result.compressor_starts_week += accumulator.compressor_starts_week
            result.completed_cycle_runtime_minutes_total += accumulator.completed_cycle_runtime_minutes_total
            result.completed_cycles += accumulator.completed_cycles
            for day, count in accumulator.start_counts_by_day.items():
                result.start_counts_by_day[day] = result.start_counts_by_day.get(day, 0) + count
            for mode in ENERGY_MODES:
                source = accumulator.modes[mode]
                target = result.modes[mode]
                target.total_electrical_kwh += source.total_electrical_kwh
                target.total_thermal_kwh += source.total_thermal_kwh
                target.daily_electrical_kwh += source.daily_electrical_kwh
                target.daily_thermal_kwh += source.daily_thermal_kwh
                target.weekly_electrical_kwh += source.weekly_electrical_kwh
                target.weekly_thermal_kwh += source.weekly_thermal_kwh
        return result

    def aggregate_mode(self, mode: str) -> ModeEnergyAccumulator:
        result = ModeEnergyAccumulator()
        if mode not in ENERGY_MODES:
            return result
        for accumulator in self.by_unit.values():
            source = accumulator.modes[mode]
            result.total_electrical_kwh += source.total_electrical_kwh
            result.total_thermal_kwh += source.total_thermal_kwh
            result.daily_electrical_kwh += source.daily_electrical_kwh
            result.daily_thermal_kwh += source.daily_thermal_kwh
            result.weekly_electrical_kwh += source.weekly_electrical_kwh
            result.weekly_thermal_kwh += source.weekly_thermal_kwh
        return result

    @classmethod
    def migrate_v1_storage(
        cls,
        data: dict[str, Any] | None,
        history_samples: Iterable[Any],
        *,
        localize: Callable[[datetime], datetime],
    ) -> dict[str, Any]:
        """Migrate v1 totals to v2 mode/cycle data without changing totals."""
        units = data.get("units", {}) if isinstance(data, dict) else {}
        if not isinstance(units, dict):
            return {"units": {}}
        migrated: dict[str, Any] = {}
        for raw_unit_id, raw in units.items():
            unit_key = str(raw_unit_id)
            existing = EnergyAccumulator.from_storage_dict(raw if isinstance(raw, dict) else None)
            try:
                unit_id = int(unit_key)
            except ValueError:
                migrated[unit_key] = existing.as_storage_dict()
                continue
            replay = _replay_history_for_unit(unit_id, history_samples, localize=localize)
            _reconcile_modes(existing, replay)
            existing.compressor_starts_total = replay.compressor_starts_total
            existing.compressor_starts_today = replay.compressor_starts_today if replay.day_key == existing.day_key else 0
            existing.compressor_starts_week = replay.compressor_starts_week if replay.week_key == existing.week_key else 0
            existing.start_counts_by_day = dict(replay.start_counts_by_day)
            existing.completed_cycle_runtime_minutes_total = replay.completed_cycle_runtime_minutes_total
            existing.completed_cycles = replay.completed_cycles
            migrated[unit_key] = existing.as_storage_dict()
        return {"units": migrated}


def _replay_history_for_unit(
    unit_id: int,
    history_samples: Iterable[Any],
    *,
    localize: Callable[[datetime], datetime],
) -> EnergyAccumulator:
    replay = EnergyAccumulator()
    first = True
    for sample in history_samples:
        timestamp_raw = getattr(sample, "timestamp_utc", None)
        try:
            timestamp = datetime.fromisoformat(timestamp_raw)
        except (TypeError, ValueError):
            continue
        row = next(
            (
                item
                for item in getattr(sample, "wpm", [])
                if isinstance(item, dict) and item.get("unit_id") == unit_id
            ),
            None,
        )
        if row is None:
            continue
        status = _status_from_history(row.get("status"))
        electrical = row.get("electrical_power_kw")
        thermal = row.get("thermal_power_kw")
        local_now = localize(timestamp)
        if first:
            replay.set_baseline(
                now_utc=timestamp,
                local_now=local_now,
                electrical_kw=electrical,
                thermal_kw=thermal,
                status=status,
            )
            first = False
        else:
            replay.update(
                now_utc=timestamp,
                local_now=local_now,
                electrical_kw=electrical,
                thermal_kw=thermal,
                status=status,
            )
    return replay


def _reconcile_modes(existing: EnergyAccumulator, replay: EnergyAccumulator) -> None:
    """Fit reconstructed mode buckets exactly under authoritative v1 totals."""
    for energy_kind in ("electrical", "thermal"):
        _reconcile_period(existing, replay, energy_kind, "total", period_matches=True)
        _reconcile_period(
            existing,
            replay,
            energy_kind,
            "daily",
            period_matches=bool(existing.day_key and replay.day_key == existing.day_key),
        )
        _reconcile_period(
            existing,
            replay,
            energy_kind,
            "weekly",
            period_matches=bool(existing.week_key and replay.week_key == existing.week_key),
        )


def _reconcile_period(
    existing: EnergyAccumulator,
    replay: EnergyAccumulator,
    energy_kind: str,
    period: str,
    *,
    period_matches: bool,
) -> None:
    total_attr = f"{period}_{energy_kind}_kwh"
    authoritative = max(float(getattr(existing, total_attr)), 0.0)
    values = {
        mode: max(float(getattr(replay.modes[mode], total_attr)), 0.0)
        if period_matches or period == "total"
        else 0.0
        for mode in ENERGY_MODES
    }
    reconstructed = sum(values.values())
    if reconstructed > authoritative and reconstructed > 0:
        scale = authoritative / reconstructed
        values = {mode: value * scale for mode, value in values.items()}
    residual = authoritative - sum(values.values())
    values[MODE_OTHER] += max(residual, 0.0)
    for mode, value in values.items():
        setattr(existing.modes[mode], total_attr, value)
