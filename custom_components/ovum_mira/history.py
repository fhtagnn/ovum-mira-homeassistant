from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import Any

from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import DOMAIN, FIRST_WPM_UNIT

_HISTORY_STORAGE_VERSION = 1
_HISTORY_RETENTION = timedelta(days=14)
_HISTORY_SAMPLE_INTERVAL = timedelta(minutes=1)
_HISTORY_SAVE_DELAY_SECONDS = 600


def _enum_name(value: Any) -> str | None:
    if value is None:
        return None
    name = getattr(value, "name", None)
    return str(name).lower() if name is not None else str(value)


@dataclass(slots=True)
class HistorySample:
    """Compact synchronized sample used for DHW analysis and export."""

    timestamp_utc: str
    outside_temperature_c: float | None
    dhw_temperature_c: float | None
    dhw_effective_target_c: float | None
    dhw_enabled: str | None
    buffer_temperature_c: float | None
    wpm: list[dict[str, Any]]


class HistoryBook:
    """Persist a compact, synchronized time series independent of Recorder internals."""

    def __init__(self, hass, entry_id: str) -> None:
        self._store: Store[dict[str, Any]] = Store(
            hass,
            _HISTORY_STORAGE_VERSION,
            f"{DOMAIN}.{entry_id}.analysis_history",
        )
        self.samples: list[HistorySample] = []
        self._last_sample_utc: datetime | None = None

    async def async_load(self) -> None:
        data = await self._store.async_load()
        rows = data.get("samples", []) if isinstance(data, dict) else []
        loaded: list[HistorySample] = []
        if isinstance(rows, list):
            for row in rows:
                if not isinstance(row, dict):
                    continue
                try:
                    loaded.append(HistorySample(**row))
                except (TypeError, ValueError):
                    continue
        self.samples = loaded
        self._prune(dt_util.utcnow())
        if self.samples:
            try:
                self._last_sample_utc = datetime.fromisoformat(self.samples[-1].timestamp_utc)
            except ValueError:
                self._last_sample_utc = None

    def _prune(self, now_utc: datetime) -> None:
        cutoff = now_utc - _HISTORY_RETENTION
        kept: list[HistorySample] = []
        for sample in self.samples:
            try:
                timestamp = datetime.fromisoformat(sample.timestamp_utc)
            except ValueError:
                continue
            if timestamp >= cutoff:
                kept.append(sample)
        self.samples = kept

    def maybe_sample(self, system) -> None:
        now_utc = dt_util.utcnow()
        if self._last_sample_utc is not None and now_utc - self._last_sample_utc < _HISTORY_SAMPLE_INTERVAL:
            return

        hot_water = system.hsm.hot_water
        buffer = system.hsm.heating_buffer
        wpm_rows: list[dict[str, Any]] = []
        for index, wpm in enumerate(system.wpms):
            wpm_rows.append(
                {
                    "unit_id": FIRST_WPM_UNIT + index,
                    "status": _enum_name(wpm.readings.status),
                    "demand_percent": wpm.readings.demand_percent,
                    "electrical_power_kw": wpm.readings.electrical_power,
                    "thermal_power_kw": wpm.readings.thermal_power,
                    "condenser_inlet_c": wpm.readings.condenser_inlet_temperature,
                    "condenser_outlet_c": wpm.readings.condenser_outlet_temperature,
                }
            )

        sample = HistorySample(
            timestamp_utc=now_utc.isoformat(),
            outside_temperature_c=system.hsm.common.outside_temperature,
            dhw_temperature_c=(hot_water.readings.primary_temperature if hot_water is not None else None),
            dhw_effective_target_c=(hot_water.readings.effective_target_temperature if hot_water is not None else None),
            dhw_enabled=(_enum_name(hot_water.settings.enabled) if hot_water is not None else None),
            buffer_temperature_c=(buffer.readings.primary_temperature if buffer is not None else None),
            wpm=wpm_rows,
        )
        self.samples.append(sample)
        self._last_sample_utc = now_utc
        self._prune(now_utc)
        self._store.async_delay_save(self.as_storage_dict, _HISTORY_SAVE_DELAY_SECONDS)

    def as_storage_dict(self) -> dict[str, Any]:
        return {"samples": [asdict(sample) for sample in self.samples]}

    async def async_save(self) -> None:
        await self._store.async_save(self.as_storage_dict())

    def export_dict(self) -> dict[str, Any]:
        return {
            "format": "ovum_mira_analysis_history_v1",
            "sample_interval_seconds": int(_HISTORY_SAMPLE_INTERVAL.total_seconds()),
            "retention_days": int(_HISTORY_RETENTION.total_seconds() / 86400),
            "sample_count": len(self.samples),
            "samples": [asdict(sample) for sample in self.samples],
        }
