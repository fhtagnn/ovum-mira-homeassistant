from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import OvumConfigEntry
from .entity import OvumMiraEntity
from .ovum_mira_modbus import SwitchState

PARALLEL_UPDATES = 1


class OvumHotWaterMainSwitch(OvumMiraEntity, SwitchEntity):
    """OVUM warm-water main switch (WW_SWITCH_ON / 55000)."""

    _attr_translation_key = "hot_water_main_switch"

    def __init__(self, coordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id, "hot_water_main_switch")

    @property
    def _hot_water(self):
        return self.coordinator.system.hsm.hot_water

    @property
    def is_on(self) -> bool | None:
        state = self._hot_water.settings.enabled
        if state is None:
            return None
        return state == SwitchState.ON

    async def async_turn_on(self, **kwargs) -> None:
        await self._async_write_action(self._hot_water.settings.async_set_enabled(True))

    async def async_turn_off(self, **kwargs) -> None:
        await self._async_write_action(self._hot_water.settings.async_set_enabled(False))


async def async_setup_entry(
    hass: HomeAssistant,
    entry: OvumConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data.coordinator
    if coordinator.system.hsm.hot_water is not None:
        async_add_entities([OvumHotWaterMainSwitch(coordinator, entry.entry_id)])
