from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import UnitOfEnergy, UnitOfPower, UnitOfTemperature, UnitOfTime, PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import OvumConfigEntry
from .const import FIRST_WPM_UNIT
from .energy import MODE_COOLING, MODE_HEATING, MODE_HOT_WATER, MODE_OTHER
from .entity import OvumMiraEntity, OvumWpmEntity
from .ovum_mira_modbus import WpmStatus

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class SensorDef:
    key: str
    translation_key: str | None = None
    value: Callable[[Any], Any]
    device_class: SensorDeviceClass | None = None
    unit: str | None = None
    state_class: SensorStateClass | None = None
    entity_registry_enabled_default: bool = True
    entity_category: EntityCategory | None = None
    extra_attributes: Callable[[Any], dict[str, Any]] | None = None


class OvumSensor(OvumMiraEntity, SensorEntity):
    def __init__(self, coordinator, entry_id: str, desc: SensorDef) -> None:
        super().__init__(coordinator, entry_id, desc.key)
        self.desc = desc
        self._attr_translation_key = desc.translation_key or desc.key
        self._attr_device_class = desc.device_class
        self._attr_native_unit_of_measurement = desc.unit
        self._attr_state_class = desc.state_class
        self._attr_entity_registry_enabled_default = desc.entity_registry_enabled_default
        self._attr_entity_category = desc.entity_category

    @property
    def native_value(self):
        return self.desc.value(self.coordinator.system)

    @property
    def extra_state_attributes(self):
        if self.desc.extra_attributes is None:
            return None
        return self.desc.extra_attributes(self.coordinator)


class OvumWpmSensor(OvumWpmEntity, SensorEntity):
    def __init__(self, coordinator, entry_id: str, unit_id: int, index: int, desc: SensorDef) -> None:
        super().__init__(coordinator, entry_id, unit_id, desc.key)
        self.index = index
        self.desc = desc
        self._attr_translation_key = desc.translation_key or desc.key
        self._attr_device_class = desc.device_class
        self._attr_native_unit_of_measurement = desc.unit
        self._attr_state_class = desc.state_class
        self._attr_entity_registry_enabled_default = desc.entity_registry_enabled_default
        self._attr_entity_category = desc.entity_category

    @property
    def native_value(self):
        return self.desc.value(self.coordinator.system.wpms[self.index])


class OvumWpmEnergySensor(OvumWpmEntity, SensorEntity):
    """Derived persistent energy/statistics sensor for one WPM."""

    def __init__(self, coordinator, entry_id: str, unit_id: int, desc: SensorDef) -> None:
        super().__init__(coordinator, entry_id, unit_id, desc.key)
        self.desc = desc
        self._attr_translation_key = desc.translation_key or desc.key
        self._attr_device_class = desc.device_class
        self._attr_native_unit_of_measurement = desc.unit
        self._attr_state_class = desc.state_class
        self._attr_entity_registry_enabled_default = desc.entity_registry_enabled_default
        self._attr_entity_category = desc.entity_category
        self._attr_suggested_display_precision = 2

    @property
    def native_value(self):
        stats = self.coordinator.energy.by_unit[self._unit_id]
        value = self.desc.value(stats)
        return round(value, 4) if isinstance(value, float) else value


class OvumSystemEnergySensor(OvumMiraEntity, SensorEntity):
    """Aggregate derived statistics for installations with multiple WPMs."""

    def __init__(self, coordinator, entry_id: str, desc: SensorDef) -> None:
        super().__init__(coordinator, entry_id, f"system_{desc.key}")
        self.desc = desc
        self._attr_translation_key = f"system_{desc.translation_key or desc.key}"
        self._attr_suggested_object_id = f"ovum_total_{desc.key}"
        self._attr_device_class = desc.device_class
        self._attr_native_unit_of_measurement = desc.unit
        self._attr_state_class = desc.state_class
        self._attr_suggested_display_precision = 2

    @property
    def native_value(self):
        value = self.desc.value(self.coordinator.energy.aggregate())
        return round(value, 4) if isinstance(value, float) else value


class OvumModeEnergySensor(OvumMiraEntity, SensorEntity):
    """Installation-wide energy statistics for one operating mode."""

    def __init__(self, coordinator, entry_id: str, mode: str, desc: SensorDef) -> None:
        super().__init__(coordinator, entry_id, desc.key)
        self.mode = mode
        self.desc = desc
        self._attr_translation_key = desc.translation_key or desc.key
        self._attr_device_class = desc.device_class
        self._attr_native_unit_of_measurement = desc.unit
        self._attr_state_class = desc.state_class
        self._attr_entity_registry_enabled_default = desc.entity_registry_enabled_default
        self._attr_entity_category = desc.entity_category
        self._attr_suggested_display_precision = 2

    @property
    def native_value(self):
        value = self.desc.value(self.coordinator.energy.aggregate_mode(self.mode))
        return round(value, 4) if isinstance(value, float) else value


class OvumDhwAnalyticsSensor(OvumMiraEntity, SensorEntity):
    """Derived DHW analysis sensor backed by coordinator analytics."""

    def __init__(self, coordinator, entry_id: str, desc: SensorDef) -> None:
        super().__init__(coordinator, entry_id, desc.key)
        self.desc = desc
        self._attr_translation_key = desc.translation_key or desc.key
        self._attr_device_class = desc.device_class
        self._attr_native_unit_of_measurement = desc.unit
        self._attr_state_class = desc.state_class
        self._attr_entity_registry_enabled_default = desc.entity_registry_enabled_default
        self._attr_entity_category = desc.entity_category
        if desc.key == "dhw_temperature_slope":
            self._attr_suggested_display_precision = 3
        elif desc.key in {"dhw_average_heating_interval", "dhw_median_heating_interval"}:
            self._attr_suggested_display_precision = 2

    @property
    def native_value(self):
        value = self.desc.value(self.coordinator.dhw_analytics)
        return value

    @property
    def extra_state_attributes(self):
        if self.desc.extra_attributes is None:
            return None
        return self.desc.extra_attributes(self.coordinator)


async def async_setup_entry(hass: HomeAssistant, entry: OvumConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    coordinator = entry.runtime_data.coordinator
    system = coordinator.system
    entities: list[SensorEntity] = []

    defs = [
        SensorDef(key="outside_temperature", value=lambda s: s.hsm.common.outside_temperature, device_class=SensorDeviceClass.TEMPERATURE, unit=UnitOfTemperature.CELSIUS, state_class=SensorStateClass.MEASUREMENT),
    ]
    if system.hsm.heating_buffer is not None:
        defs += [
            SensorDef(key="buffer_temperature", value=lambda s: s.hsm.heating_buffer.readings.primary_temperature, device_class=SensorDeviceClass.TEMPERATURE, unit=UnitOfTemperature.CELSIUS, state_class=SensorStateClass.MEASUREMENT),
            SensorDef(key="buffer_effective_target", value=lambda s: s.hsm.heating_buffer.readings.effective_target_temperature, device_class=SensorDeviceClass.TEMPERATURE, unit=UnitOfTemperature.CELSIUS, state_class=SensorStateClass.MEASUREMENT),
        ]
        if system.hsm.options.heating_buffer_sensor_count == 2:
            defs.append(SensorDef(key="buffer_upper_temperature", value=lambda s: s.hsm.heating_buffer.readings.upper_temperature, device_class=SensorDeviceClass.TEMPERATURE, unit=UnitOfTemperature.CELSIUS, state_class=SensorStateClass.MEASUREMENT))
    if system.hsm.hot_water is not None:
        dhw_primary_translation = "dhw_upper_temperature" if system.hsm.options.hot_water_sensor_count == 2 else "dhw_temperature"
        defs += [
            SensorDef(key="dhw_temperature", translation_key=dhw_primary_translation, value=lambda s: s.hsm.hot_water.readings.primary_temperature, device_class=SensorDeviceClass.TEMPERATURE, unit=UnitOfTemperature.CELSIUS, state_class=SensorStateClass.MEASUREMENT),
            SensorDef(key="dhw_effective_target", value=lambda s: s.hsm.hot_water.readings.effective_target_temperature, device_class=SensorDeviceClass.TEMPERATURE, unit=UnitOfTemperature.CELSIUS, state_class=SensorStateClass.MEASUREMENT),
        ]
        if system.hsm.options.hot_water_sensor_count == 2:
            defs.append(SensorDef(key="dhw_lower_temperature", value=lambda s: s.hsm.hot_water.readings.lower_temperature, device_class=SensorDeviceClass.TEMPERATURE, unit=UnitOfTemperature.CELSIUS, state_class=SensorStateClass.MEASUREMENT))
        analytics_defs = [
            SensorDef(
                key="dhw_last_heating_start",
                value=lambda a: a.last_start,
                device_class=SensorDeviceClass.TIMESTAMP,
            ),
            SensorDef(
                key="dhw_predicted_next_heating_start",
                value=lambda a: a.predicted_next_start,
                device_class=SensorDeviceClass.TIMESTAMP,
                extra_attributes=lambda c: {
                    "temperature_slope_c_per_hour": c.dhw_analytics.current_slope_c_per_hour,
                    "estimated_start_temperature_c": c.dhw_analytics.estimated_trigger_temperature_c,
                    "samples_used": c.dhw_analytics.slope_samples_used,
                    "method": "linear_temperature_extrapolation",
                    "holiday_target_threshold_c": c.dhw_analytics.holiday_target_threshold_c,
                    "holiday_mode_inferred": c.dhw_analytics.holiday_mode_inferred,
                    "forecast_suppression_reason": c.dhw_analytics.forecast_suppression_reason,
                },
            ),
            SensorDef(
                key="dhw_temperature_slope",
                value=lambda a: a.current_slope_c_per_hour,
                unit="°C/h",
                state_class=SensorStateClass.MEASUREMENT,
            ),
            SensorDef(
                key="dhw_estimated_start_temperature",
                value=lambda a: a.estimated_trigger_temperature_c,
                device_class=SensorDeviceClass.TEMPERATURE,
                unit=UnitOfTemperature.CELSIUS,
                state_class=SensorStateClass.MEASUREMENT,
                entity_registry_enabled_default=False,
                entity_category=EntityCategory.DIAGNOSTIC,
            ),
            SensorDef(
                key="dhw_average_heating_interval",
                value=lambda a: a.average_heating_interval_hours,
                device_class=SensorDeviceClass.DURATION,
                unit=UnitOfTime.HOURS,
                state_class=SensorStateClass.MEASUREMENT,
            ),
            SensorDef(
                key="dhw_median_heating_interval",
                value=lambda a: a.median_heating_interval_hours,
                device_class=SensorDeviceClass.DURATION,
                unit=UnitOfTime.HOURS,
                state_class=SensorStateClass.MEASUREMENT,
                entity_registry_enabled_default=False,
                entity_category=EntityCategory.DIAGNOSTIC,
            ),
        ]
        entities.extend(OvumDhwAnalyticsSensor(coordinator, entry.entry_id, d) for d in analytics_defs)
    for number, circuit in ((1, system.hsm.heating_circuit_1), (2, system.hsm.heating_circuit_2)):
        if circuit is not None:
            defs += [
                SensorDef(key=f"hk{number}_actual", translation_key="heating_circuit_actual", value=lambda s, n=number: getattr(s.hsm, f"heating_circuit_{n}").readings.actual_value, device_class=SensorDeviceClass.TEMPERATURE, unit=UnitOfTemperature.CELSIUS, state_class=SensorStateClass.MEASUREMENT),
                SensorDef(key=f"hk{number}_effective_target", translation_key="heating_circuit_effective_target", value=lambda s, n=number: getattr(s.hsm, f"heating_circuit_{n}").readings.effective_target_temperature, device_class=SensorDeviceClass.TEMPERATURE, unit=UnitOfTemperature.CELSIUS, state_class=SensorStateClass.MEASUREMENT),
                SensorDef(key=f"hk{number}_type", translation_key="heating_circuit_type", value=lambda s, n=number: getattr(s.hsm, f"heating_circuit_{n}").circuit_type.name.lower(), entity_registry_enabled_default=False, entity_category=EntityCategory.DIAGNOSTIC),
            ]
    entities.extend(OvumSensor(coordinator, entry.entry_id, d) for d in defs)

    energy_defs = [
        SensorDef(key="electrical_energy_total", value=lambda e: e.total_electrical_kwh, device_class=SensorDeviceClass.ENERGY, unit=UnitOfEnergy.KILO_WATT_HOUR, state_class=SensorStateClass.TOTAL_INCREASING),
        SensorDef(key="thermal_energy_total", value=lambda e: e.total_thermal_kwh, device_class=SensorDeviceClass.ENERGY, unit=UnitOfEnergy.KILO_WATT_HOUR, state_class=SensorStateClass.TOTAL_INCREASING),
        SensorDef(key="electrical_energy_today", value=lambda e: e.daily_electrical_kwh, device_class=SensorDeviceClass.ENERGY, unit=UnitOfEnergy.KILO_WATT_HOUR, state_class=SensorStateClass.TOTAL_INCREASING),
        SensorDef(key="thermal_energy_today", value=lambda e: e.daily_thermal_kwh, device_class=SensorDeviceClass.ENERGY, unit=UnitOfEnergy.KILO_WATT_HOUR, state_class=SensorStateClass.TOTAL_INCREASING),
        SensorDef(key="electrical_energy_week", value=lambda e: e.weekly_electrical_kwh, device_class=SensorDeviceClass.ENERGY, unit=UnitOfEnergy.KILO_WATT_HOUR, state_class=SensorStateClass.TOTAL_INCREASING),
        SensorDef(key="thermal_energy_week", value=lambda e: e.weekly_thermal_kwh, device_class=SensorDeviceClass.ENERGY, unit=UnitOfEnergy.KILO_WATT_HOUR, state_class=SensorStateClass.TOTAL_INCREASING),
        SensorDef(key="cop_current", value=lambda e: e.instantaneous_cop, state_class=SensorStateClass.MEASUREMENT),
        SensorDef(key="work_factor_today", value=lambda e: e.daily_work_factor, state_class=SensorStateClass.MEASUREMENT),
        SensorDef(key="work_factor_week", value=lambda e: e.weekly_work_factor, state_class=SensorStateClass.MEASUREMENT),
        SensorDef(key="work_factor_total", value=lambda e: e.total_work_factor, state_class=SensorStateClass.MEASUREMENT),
        SensorDef(key="compressor_starts_today", value=lambda e: e.compressor_starts_today),
        SensorDef(key="compressor_starts_week", value=lambda e: e.compressor_starts_week),
        SensorDef(key="compressor_starts_average_7d", value=lambda e: e.average_starts_per_day_7d, state_class=SensorStateClass.MEASUREMENT),
        SensorDef(key="compressor_average_cycle_runtime", value=lambda e: e.average_cycle_runtime_minutes, device_class=SensorDeviceClass.DURATION, unit=UnitOfTime.MINUTES, state_class=SensorStateClass.MEASUREMENT),
    ]

    mode_defs = {
        MODE_HOT_WATER: [
            SensorDef(key="hot_water_electrical_energy", value=lambda e: e.total_electrical_kwh, device_class=SensorDeviceClass.ENERGY, unit=UnitOfEnergy.KILO_WATT_HOUR, state_class=SensorStateClass.TOTAL_INCREASING),
            SensorDef(key="hot_water_thermal_energy", value=lambda e: e.total_thermal_kwh, device_class=SensorDeviceClass.ENERGY, unit=UnitOfEnergy.KILO_WATT_HOUR, state_class=SensorStateClass.TOTAL_INCREASING),
            SensorDef(key="hot_water_work_factor", value=lambda e: e.total_work_factor, state_class=SensorStateClass.MEASUREMENT),
        ],
        MODE_HEATING: [
            SensorDef(key="heating_electrical_energy", value=lambda e: e.total_electrical_kwh, device_class=SensorDeviceClass.ENERGY, unit=UnitOfEnergy.KILO_WATT_HOUR, state_class=SensorStateClass.TOTAL_INCREASING),
            SensorDef(key="heating_thermal_energy", value=lambda e: e.total_thermal_kwh, device_class=SensorDeviceClass.ENERGY, unit=UnitOfEnergy.KILO_WATT_HOUR, state_class=SensorStateClass.TOTAL_INCREASING),
            SensorDef(key="heating_work_factor", value=lambda e: e.total_work_factor, state_class=SensorStateClass.MEASUREMENT),
        ],
        MODE_COOLING: [
            SensorDef(key="cooling_electrical_energy", value=lambda e: e.total_electrical_kwh, device_class=SensorDeviceClass.ENERGY, unit=UnitOfEnergy.KILO_WATT_HOUR, state_class=SensorStateClass.TOTAL_INCREASING, entity_registry_enabled_default=False),
            SensorDef(key="cooling_thermal_energy", value=lambda e: e.total_thermal_kwh, device_class=SensorDeviceClass.ENERGY, unit=UnitOfEnergy.KILO_WATT_HOUR, state_class=SensorStateClass.TOTAL_INCREASING, entity_registry_enabled_default=False),
            SensorDef(key="cooling_work_factor", value=lambda e: e.total_work_factor, state_class=SensorStateClass.MEASUREMENT, entity_registry_enabled_default=False),
        ],
        MODE_OTHER: [
            SensorDef(key="other_electrical_energy", value=lambda e: e.total_electrical_kwh, device_class=SensorDeviceClass.ENERGY, unit=UnitOfEnergy.KILO_WATT_HOUR, state_class=SensorStateClass.TOTAL_INCREASING),
            SensorDef(key="other_thermal_energy", value=lambda e: e.total_thermal_kwh, device_class=SensorDeviceClass.ENERGY, unit=UnitOfEnergy.KILO_WATT_HOUR, state_class=SensorStateClass.TOTAL_INCREASING),
        ],
    }
    for mode, definitions in mode_defs.items():
        entities.extend(
            OvumModeEnergySensor(coordinator, entry.entry_id, mode, definition)
            for definition in definitions
        )

    wpm_defs = [
        SensorDef(key="demand", value=lambda w: w.readings.demand_percent, unit=PERCENTAGE, state_class=SensorStateClass.MEASUREMENT),
        SensorDef(key="electrical_power", value=lambda w: (w.readings.electrical_power * 1000.0) if w.readings.electrical_power is not None else None, device_class=SensorDeviceClass.POWER, unit=UnitOfPower.WATT, state_class=SensorStateClass.MEASUREMENT),
        SensorDef(key="thermal_power", value=lambda w: w.readings.thermal_power, device_class=SensorDeviceClass.POWER, unit=UnitOfPower.KILO_WATT, state_class=SensorStateClass.MEASUREMENT),
        SensorDef(key="condenser_inlet", value=lambda w: w.readings.condenser_inlet_temperature, device_class=SensorDeviceClass.TEMPERATURE, unit=UnitOfTemperature.CELSIUS, state_class=SensorStateClass.MEASUREMENT),
        SensorDef(key="condenser_outlet", value=lambda w: w.readings.condenser_outlet_temperature, device_class=SensorDeviceClass.TEMPERATURE, unit=UnitOfTemperature.CELSIUS, state_class=SensorStateClass.MEASUREMENT),
        SensorDef(key="compressor_runtime", value=lambda w: w.readings.compressor_runtime_minutes, device_class=SensorDeviceClass.DURATION, unit=UnitOfTime.MINUTES),
    ]
    for idx, wpm in enumerate(system.wpms):
        unit_id = FIRST_WPM_UNIT + idx
        entities.extend(OvumWpmSensor(coordinator, entry.entry_id, unit_id, idx, d) for d in wpm_defs)
        entities.extend(OvumWpmEnergySensor(coordinator, entry.entry_id, unit_id, d) for d in energy_defs)
        status = OvumWpmSensor(coordinator, entry.entry_id, unit_id, idx, SensorDef(key="status", value=lambda w: w.readings.status.name.lower() if isinstance(w.readings.status, WpmStatus) else None, device_class=SensorDeviceClass.ENUM))
        status._attr_options = [s.name.lower() for s in WpmStatus]
        entities.append(status)

    if len(system.wpms) > 1:
        entities.extend(OvumSystemEnergySensor(coordinator, entry.entry_id, d) for d in energy_defs)

    async_add_entities(entities)
