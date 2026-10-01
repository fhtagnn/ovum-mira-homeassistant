from typing import override

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import OvumConfigEntry
from .const import FIRST_WPM_UNIT
from .energy import is_compressor_active
from .entity import OvumMiraEntity, OvumWpmEntity
from .ovum_mira_modbus import WpmStatus

PARALLEL_UPDATES = 0

_PROBLEM_STATUSES = {
    WpmStatus.FAULT,
    WpmStatus.INVERTER_OFFLINE,
}


class OvumModbusCommunicationBinarySensor(OvumMiraEntity, BinarySensorEntity):
    """Report whether the last complete Modbus device refresh succeeded."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "modbus_communication"

    def __init__(self, coordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id, "modbus_communication")

    @property
    @override
    def available(self) -> bool:
        """Remain available so a failed refresh is represented as disconnected."""
        return True

    @property
    def is_on(self) -> bool:
        return self.coordinator.modbus_available

    @property
    def extra_state_attributes(self) -> dict[str, str]:
        return {
            "last_successful_update": self.coordinator.last_successful_modbus_update.isoformat()
        }


class OvumWpmProblemBinarySensor(OvumWpmEntity, BinarySensorEntity):
    """Summarize explicit WPM fault states for automations."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "wpm_problem"

    def __init__(self, coordinator, entry_id: str, unit_id: int, index: int) -> None:
        super().__init__(coordinator, entry_id, unit_id, "problem")
        self._index = index

    @property
    def _status(self) -> WpmStatus | None:
        status = self.coordinator.system.wpms[self._index].readings.status
        return status if isinstance(status, WpmStatus) else None

    @property
    def is_on(self) -> bool | None:
        status = self._status
        return None if status is None else status in _PROBLEM_STATUSES

    @property
    def extra_state_attributes(self) -> dict[str, int | str | None]:
        status = self._status
        return {
            "unit_id": self._unit_id,
            "wpm_status": status.name.lower() if status is not None else None,
            "wpm_status_code": int(status) if status is not None else None,
        }


class OvumWpmRunningBinarySensor(OvumWpmEntity, BinarySensorEntity):
    """Report one continuous observed compressor cycle."""

    _attr_device_class = BinarySensorDeviceClass.RUNNING
    _attr_translation_key = "wpm_running"

    def __init__(self, coordinator, entry_id: str, unit_id: int, index: int) -> None:
        super().__init__(coordinator, entry_id, unit_id, "running")
        self._index = index

    @property
    def _status(self) -> WpmStatus | None:
        status = self.coordinator.system.wpms[self._index].readings.status
        return status if isinstance(status, WpmStatus) else None

    @property
    def is_on(self) -> bool | None:
        status = self._status
        return None if status is None else is_compressor_active(status)

    @property
    def extra_state_attributes(self) -> dict[str, int | str | None]:
        status = self._status
        return {
            "unit_id": self._unit_id,
            "wpm_status": status.name.lower() if status is not None else None,
        }


async def async_setup_entry(
    hass: HomeAssistant,
    entry: OvumConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data.coordinator
    entities: list[BinarySensorEntity] = [
        OvumModbusCommunicationBinarySensor(coordinator, entry.entry_id)
    ]
    for index, _wpm in enumerate(coordinator.system.wpms):
        unit_id = FIRST_WPM_UNIT + index
        entities.extend(
            (
                OvumWpmProblemBinarySensor(
                    coordinator, entry.entry_id, unit_id, index
                ),
                OvumWpmRunningBinarySensor(
                    coordinator, entry.entry_id, unit_id, index
                ),
            )
        )
    async_add_entities(entities)
