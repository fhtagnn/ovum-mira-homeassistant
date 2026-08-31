import logging
from typing import Any, override

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import DEFAULT_SCAN_INTERVAL, DOMAIN, FIRST_WPM_UNIT
from .dhw_analytics import DhwAnalytics
from .energy import EnergyBook
from .history import HistoryBook
from .ovum_mira_modbus import OvumMiraSystem

_LOGGER = logging.getLogger(__name__)
_STORAGE_VERSION = 2
_SAVE_DELAY_SECONDS = 60


class EnergyStore(Store[dict[str, Any]]):
    """Persistent energy store with explicit public-beta migrations."""

    def __init__(self, hass: HomeAssistant, key: str, history: HistoryBook) -> None:
        super().__init__(hass, _STORAGE_VERSION, key)
        self._history = history

    @override
    async def _async_migrate_func(
        self,
        old_major_version: int,
        old_minor_version: int,
        old_data: dict[str, Any],
    ) -> dict[str, Any]:
        if old_major_version == 1:
            return EnergyBook.migrate_v1_storage(
                old_data,
                self._history.samples,
                localize=dt_util.as_local,
            )
        raise NotImplementedError


class OvumMiraCoordinator(DataUpdateCoordinator[None]):
    """Coordinate one pooled refresh for the whole MIRA installation."""

    def __init__(self, hass: HomeAssistant, system: OvumMiraSystem, entry_id: str) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name="OVUM MIRA",
            update_interval=DEFAULT_SCAN_INTERVAL,
            always_update=True,
        )
        self.system = system
        unit_ids = [FIRST_WPM_UNIT + index for index in range(len(system.wpms))]
        self.energy = EnergyBook(unit_ids)
        self.history = HistoryBook(hass, entry_id)
        self.dhw_analytics = DhwAnalytics(hass, entry_id)
        self._store: Store[dict[str, Any]] = EnergyStore(
            hass,
            f"{DOMAIN}.{entry_id}.energy",
            self.history,
        )

    async def async_initialize(self) -> None:
        """Restore persistent derived state and establish baselines."""
        await self.history.async_load()
        await self.dhw_analytics.async_load()
        await self.async_initialize_energy()
        self.history.maybe_sample(self.system)
        self.dhw_analytics.initialize_live_state(self.system)
        self.dhw_analytics.update(self.system, self.history)

    async def async_initialize_energy(self) -> None:
        """Restore accumulated energy and establish a no-gap first sample."""
        stored = await self._store.async_load()
        self.energy.load(stored)
        now_utc = dt_util.utcnow()
        local_now = dt_util.now()
        for index, wpm in enumerate(self.system.wpms):
            unit_id = FIRST_WPM_UNIT + index
            self.energy.by_unit[unit_id].set_baseline(
                now_utc=now_utc,
                local_now=local_now,
                electrical_kw=wpm.readings.electrical_power,
                thermal_kw=wpm.readings.thermal_power,
                status=wpm.readings.status,
                compressor_runtime_minutes=wpm.readings.compressor_runtime_minutes,
            )

    def _update_derived_data(self) -> None:
        now_utc = dt_util.utcnow()
        local_now = dt_util.now()
        for index, wpm in enumerate(self.system.wpms):
            unit_id = FIRST_WPM_UNIT + index
            self.energy.by_unit[unit_id].update(
                now_utc=now_utc,
                local_now=local_now,
                electrical_kw=wpm.readings.electrical_power,
                thermal_kw=wpm.readings.thermal_power,
                status=wpm.readings.status,
                compressor_runtime_minutes=wpm.readings.compressor_runtime_minutes,
            )
        self._store.async_delay_save(self.energy.as_storage_dict, _SAVE_DELAY_SECONDS)
        self.history.maybe_sample(self.system)
        self.dhw_analytics.update(self.system, self.history)

    async def async_save_persistent_state(self) -> None:
        """Persist counters and analysis data immediately."""
        await self._store.async_save(self.energy.as_storage_dict())
        await self.history.async_save()
        await self.dhw_analytics.async_save()

    async def _async_update_data(self) -> None:
        try:
            await self.system.async_update()
            self._update_derived_data()
        except Exception as err:
            raise UpdateFailed(f"Error communicating with OVUM MIRA: {err}") from err
        return None
