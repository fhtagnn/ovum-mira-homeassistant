from homeassistant.components.number import NumberEntity
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import OvumConfigEntry
from .entity import OvumMiraEntity

PARALLEL_UPDATES = 1


class OvumTemperatureNumber(OvumMiraEntity, NumberEntity):
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

    def __init__(
        self,
        coordinator,
        entry_id,
        key,
        translation_key,
        getter,
        setter,
        low,
        high,
        step=1,
        *,
        enabled=True,
        entity_category=None,
        translation_placeholders=None,
    ):
        super().__init__(coordinator, entry_id, key)
        self._attr_translation_key = translation_key
        self._attr_translation_placeholders = translation_placeholders
        self._getter = getter
        self._setter = setter
        self._attr_native_min_value = low
        self._attr_native_max_value = high
        self._attr_native_step = step
        self._attr_entity_registry_enabled_default = enabled
        self._attr_entity_category = entity_category

    @property
    def native_value(self):
        return self._getter(self.coordinator.system)

    async def async_set_native_value(self, value: float) -> None:
        await self._async_write_action(self._setter(self.coordinator.system, value))


async def async_setup_entry(hass: HomeAssistant, entry: OvumConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    c = entry.runtime_data.coordinator
    s = c.system
    entities = []

    if s.hsm.hot_water is not None:
        entities.append(OvumTemperatureNumber(
            c, entry.entry_id, "dhw_pv_target", "pv_hot_water_target_temperature",
            lambda x: x.hsm.hot_water.settings.pv_target_temperature,
            lambda x, v: x.hsm.hot_water.settings.async_set_pv_target_temperature(int(v)),
            0, 67, enabled=False, entity_category=EntityCategory.CONFIG,
        ))
    if s.hsm.heating_buffer is not None:
        entities.append(OvumTemperatureNumber(
            c, entry.entry_id, "buffer_pv_target", "pv_heating_buffer_target_temperature",
            lambda x: x.hsm.heating_buffer.settings.pv_target_temperature,
            lambda x, v: x.hsm.heating_buffer.settings.async_set_pv_target_temperature(int(v)),
            0, 70, enabled=False, entity_category=EntityCategory.CONFIG,
        ))

    for n in (1, 2):
        circuit = getattr(s.hsm, f"heating_circuit_{n}")
        if circuit is None:
            continue
        # When a real room probe exists, climate is the primary UI for the same target.
        room_target_enabled = circuit.room_readings is None
        entities.append(OvumTemperatureNumber(
            c, entry.entry_id, f"hk{n}_room_target_heating", "heating_circuit_room_target_heating",
            lambda x, num=n: getattr(x.hsm, f"heating_circuit_{num}").settings.room_target_heating,
            lambda x, v, num=n: getattr(x.hsm, f"heating_circuit_{num}").settings.async_set_room_target_heating(v),
            0, 50, 0.5, enabled=room_target_enabled, entity_category=None, translation_placeholders={"circuit": str(n)},
        ))
        entities.append(OvumTemperatureNumber(
            c, entry.entry_id, f"hk{n}_pv_raise", "pv_heating_circuit_target_raise",
            lambda x, num=n: getattr(x.hsm, f"heating_circuit_{num}").settings.pv_raise,
            lambda x, v, num=n: getattr(x.hsm, f"heating_circuit_{num}").settings.async_set_pv_raise(int(v)),
            0, 25, enabled=False, entity_category=EntityCategory.CONFIG, translation_placeholders={"circuit": str(n)},
        ))
        entities.append(OvumTemperatureNumber(
            c, entry.entry_id, f"hk{n}_pv_reduce", "pv_heating_circuit_target_reduce",
            lambda x, num=n: getattr(x.hsm, f"heating_circuit_{num}").settings.pv_reduce,
            lambda x, v, num=n: getattr(x.hsm, f"heating_circuit_{num}").settings.async_set_pv_reduce(int(v)),
            -25, 0, enabled=False, entity_category=EntityCategory.CONFIG, translation_placeholders={"circuit": str(n)},
        ))

    async_add_entities(entities)
