from __future__ import annotations

from homeassistant.components.water_heater import STATE_HEAT_PUMP, WaterHeaterEntity, WaterHeaterEntityFeature
from homeassistant.const import ATTR_TEMPERATURE, STATE_OFF, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import OvumConfigEntry
from .entity import OvumMiraEntity
from .ovum_mira_modbus import SwitchState

PARALLEL_UPDATES = 1


class OvumHotWater(OvumMiraEntity, WaterHeaterEntity):
    _attr_translation_key = "hot_water"
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_min_temp = 0
    _attr_max_temp = 62
    _attr_target_temperature_step = 1
    _attr_supported_features = WaterHeaterEntityFeature.TARGET_TEMPERATURE | WaterHeaterEntityFeature.ON_OFF

    def __init__(self, coordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id, "hot_water")

    @property
    def _hot_water(self):
        return self.coordinator.system.hsm.hot_water

    @property
    def current_temperature(self) -> float | None:
        return self._hot_water.readings.primary_temperature

    @property
    def target_temperature(self) -> float | None:
        return self._hot_water.settings.target_temperature

    @property
    def current_operation(self) -> str | None:
        state = self._hot_water.settings.enabled
        if state is None:
            return None
        return STATE_HEAT_PUMP if state == SwitchState.ON else STATE_OFF

    async def async_set_temperature(self, **kwargs) -> None:
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is not None:
            await self._async_write_action(
                self._hot_water.settings.async_set_target_temperature(round(float(temperature)))
            )

    async def async_turn_on(self) -> None:
        await self._async_write_action(self._hot_water.settings.async_set_enabled(True))

    async def async_turn_off(self) -> None:
        await self._async_write_action(self._hot_water.settings.async_set_enabled(False))


async def async_setup_entry(hass: HomeAssistant, entry: OvumConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    coordinator = entry.runtime_data.coordinator
    if coordinator.system.hsm.hot_water is not None:
        async_add_entities([OvumHotWater(coordinator, entry.entry_id)])
