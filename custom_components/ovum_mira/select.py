from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import OvumConfigEntry
from .entity import OvumMiraEntity
from .ovum_mira_modbus import HeatingCircuitMode

PARALLEL_UPDATES = 1

MODE_TO_OPTION = {
    HeatingCircuitMode.OFF_FROST_PROTECTION: "off_frost_protection",
    HeatingCircuitMode.AUTOMATIC: "automatic",
    HeatingCircuitMode.WINTER_HEATING_ONLY: "winter_heating_only",
    HeatingCircuitMode.SUMMER_COOLING_ONLY: "summer_cooling_only",
}
OPTION_TO_MODE = {v: k for k, v in MODE_TO_OPTION.items()}


class HeatingCircuitModeSelect(OvumMiraEntity, SelectEntity):
    def __init__(self, coordinator, entry_id: str, number: int) -> None:
        super().__init__(coordinator, entry_id, f"hk{number}_mode")
        self.number = number
        self._attr_translation_key = "heating_circuit_mode"
        self._attr_translation_placeholders = {"circuit": str(number)}
        self._attr_options = list(OPTION_TO_MODE)

    @property
    def _circuit(self):
        return getattr(self.coordinator.system.hsm, f"heating_circuit_{self.number}")

    @property
    def current_option(self) -> str | None:
        return MODE_TO_OPTION.get(self._circuit.settings.mode)

    async def async_select_option(self, option: str) -> None:
        await self._async_write_action(
            self._circuit.settings.async_set_mode(OPTION_TO_MODE[option])
        )


async def async_setup_entry(hass: HomeAssistant, entry: OvumConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    coordinator = entry.runtime_data.coordinator
    entities = []
    for number in (1, 2):
        if getattr(coordinator.system.hsm, f"heating_circuit_{number}") is not None:
            entities.append(HeatingCircuitModeSelect(coordinator, entry.entry_id, number))
    async_add_entities(entities)
