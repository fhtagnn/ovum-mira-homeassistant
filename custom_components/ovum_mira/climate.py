from homeassistant.components.climate import ClimateEntity, ClimateEntityFeature, HVACMode
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import OvumConfigEntry
from .entity import OvumMiraEntity

PARALLEL_UPDATES = 1


class HeatingCircuitClimate(OvumMiraEntity, ClimateEntity):
    """Room climate entity only when a real room probe is configured.

    Without a room probe, the MIRA HK actual value is a water-circuit temperature
    and must not be presented as current room temperature. In that case the room
    target remains available as a Number entity instead.
    """

    _attr_hvac_modes = [HVACMode.HEAT]
    _attr_hvac_mode = HVACMode.HEAT
    _attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_min_temp = 0
    _attr_max_temp = 50
    _attr_target_temperature_step = 0.5

    def __init__(self, coordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id, "hk1_climate")
        self._attr_translation_key = "heating_circuit_room"
        self._attr_translation_placeholders = {"circuit": "1"}

    @property
    def _circuit(self):
        return self.coordinator.system.hsm.heating_circuit_1

    @property
    def current_temperature(self) -> float | None:
        room = self._circuit.room_readings
        return room.actual_room_temperature if room is not None else None

    @property
    def target_temperature(self) -> float | None:
        return self._circuit.settings.room_target_heating

    async def async_set_temperature(self, **kwargs) -> None:
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is not None:
            await self._async_write_action(
                self._circuit.settings.async_set_room_target_heating(float(temperature))
            )


async def async_setup_entry(hass: HomeAssistant, entry: OvumConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    coordinator = entry.runtime_data.coordinator
    circuit = coordinator.system.hsm.heating_circuit_1
    if circuit is not None and circuit.room_readings is not None:
        async_add_entities([HeatingCircuitClimate(coordinator, entry.entry_id)])
