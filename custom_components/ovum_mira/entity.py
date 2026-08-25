from __future__ import annotations

from typing import override

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import OvumMiraCoordinator

_OBJECT_IDS = {
    "outside_temperature": "outdoor_temperature",
    "buffer_temperature": "heating_buffer_temperature",
    "buffer_effective_target": "heating_buffer_effective_target_temperature",
    "buffer_upper_temperature": "heating_buffer_upper_temperature",
    "dhw_temperature": "hot_water_temperature",
    "dhw_effective_target": "hot_water_effective_target_temperature",
    "dhw_lower_temperature": "hot_water_lower_temperature",
    "dhw_last_heating_start": "hot_water_last_heating_start",
    "dhw_predicted_next_heating_start": "hot_water_predicted_next_heating_start",
    "dhw_temperature_slope": "hot_water_temperature_slope",
    "dhw_estimated_start_temperature": "hot_water_estimated_start_temperature",
    "dhw_pv_target": "pv_hot_water_target_temperature",
    "buffer_pv_target": "pv_heating_buffer_target_temperature",
    "hot_water_main_switch": "hot_water_main_switch",
    "hot_water": "hot_water",
    "hk1_actual": "heating_circuit_1_temperature",
    "hk2_actual": "heating_circuit_2_temperature",
    "hk1_effective_target": "heating_circuit_1_effective_target_temperature",
    "hk2_effective_target": "heating_circuit_2_effective_target_temperature",
    "hk1_type": "heating_circuit_1_type",
    "hk2_type": "heating_circuit_2_type",
    "hk1_mode": "heating_circuit_1_mode",
    "hk2_mode": "heating_circuit_2_mode",
    "hk1_room_target_heating": "heating_circuit_1_room_target_heating",
    "hk2_room_target_heating": "heating_circuit_2_room_target_heating",
    "hk1_pv_raise": "pv_heating_circuit_1_target_raise",
    "hk2_pv_raise": "pv_heating_circuit_2_target_raise",
    "hk1_pv_reduce": "pv_heating_circuit_1_target_reduce",
    "hk2_pv_reduce": "pv_heating_circuit_2_target_reduce",
    "hk1_climate": "heating_circuit_1_room",
}


class OvumMiraEntity(CoordinatorEntity[OvumMiraCoordinator]):
    """Base OVUM MIRA entity."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: OvumMiraCoordinator, entry_id: str, key: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry_id}_{key}"
        self._entry_id = entry_id
        self._ovum_suggested_object_id = f"ovum_{_OBJECT_IDS.get(key, key)}"

    @property
    @override
    def suggested_object_id(self) -> str | None:
        """Return a stable English object ID independent of UI language."""
        return getattr(
            self,
            "_attr_suggested_object_id",
            self._ovum_suggested_object_id,
        )

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry_id)},
            name="OVUM MIRA",
            manufacturer="OVUM",
            model="MIRA",
        )


class OvumWpmEntity(OvumMiraEntity):
    def __init__(self, coordinator: OvumMiraCoordinator, entry_id: str, unit_id: int, key: str) -> None:
        super().__init__(coordinator, entry_id, f"wpm_{unit_id}_{key}")
        self._unit_id = unit_id
        self._ovum_suggested_object_id = f"ovum_wpm_{unit_id - 110}_{key}"

    @property
    def device_info(self) -> DeviceInfo:
        wpm = next((w for w in self.coordinator.system.wpms if getattr(w._unit, "unit_id", self._unit_id) == self._unit_id), None)
        name = getattr(getattr(wpm, "identity", None), "system_name", None) or f"Wärmepumpe {self._unit_id - 110}"
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self._entry_id}_wpm_{self._unit_id}")},
            via_device=(DOMAIN, self._entry_id),
            name=name,
            manufacturer="OVUM",
            model="MIRA WPM",
        )
