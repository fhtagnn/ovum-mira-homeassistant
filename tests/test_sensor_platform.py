from types import SimpleNamespace
from unittest.mock import MagicMock

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import UnitOfEnergy, UnitOfPower, UnitOfTime
from homeassistant.helpers.entity import EntityCategory

from custom_components.ovum_mira.ovum_mira_modbus import InstallationOptions, SwitchState, WpmStatus
from custom_components.ovum_mira.sensor import async_setup_entry


def _energy_stats():
    return SimpleNamespace(
        total_electrical_kwh=1.23456,
        total_thermal_kwh=4.56789,
        daily_electrical_kwh=0.5,
        daily_thermal_kwh=2.0,
        weekly_electrical_kwh=3.0,
        weekly_thermal_kwh=12.0,
        instantaneous_cop=4.0,
        daily_work_factor=4.1,
        weekly_work_factor=4.2,
        total_work_factor=4.3,
    )


def _system(*, buffer_sensors=1, dhw_sensors=1, wpm_count=1):
    options = InstallationOptions(
        heating_buffer_sensor_count=buffer_sensors,
        hot_water_sensor_count=dhw_sensors,
    )
    hot_water = SimpleNamespace(
        readings=SimpleNamespace(
            primary_temperature=48.0,
            effective_target_temperature=50.0,
            lower_temperature=47.0,
        ),
        settings=SimpleNamespace(enabled=SwitchState.ON),
    )
    heating_buffer = SimpleNamespace(
        readings=SimpleNamespace(
            primary_temperature=34.0,
            effective_target_temperature=35.0,
            upper_temperature=36.0,
        )
    )
    wpms = []
    for index in range(wpm_count):
        wpms.append(
            SimpleNamespace(
                _unit=SimpleNamespace(unit_id=111 + index),
                identity=SimpleNamespace(system_name=f"WPM-{index + 1}"),
                readings=SimpleNamespace(
                    demand_percent=42,
                    electrical_power=1.5,
                    thermal_power=6.0,
                    condenser_inlet_temperature=35.0,
                    condenser_outlet_temperature=41.0,
                    compressor_runtime_minutes=820,
                    status=WpmStatus.READY,
                ),
            )
        )
    return SimpleNamespace(
        hsm=SimpleNamespace(
            options=options,
            common=SimpleNamespace(outside_temperature=12.5),
            hot_water=hot_water,
            heating_buffer=heating_buffer,
            heating_circuit_1=None,
            heating_circuit_2=None,
        ),
        wpms=wpms,
    )


def _coordinator(system):
    stats = {111 + index: _energy_stats() for index in range(len(system.wpms))}
    aggregate = _energy_stats()
    return SimpleNamespace(
        system=system,
        last_update_success=True,
        energy=SimpleNamespace(by_unit=stats, aggregate=MagicMock(return_value=aggregate)),
        dhw_analytics=SimpleNamespace(
            last_start=None,
            predicted_next_start=None,
            current_slope_c_per_hour=-0.4,
            estimated_trigger_temperature_c=45.0,
            slope_samples_used=12,
        ),
    )


async def _entities(system):
    coordinator = _coordinator(system)
    entry = SimpleNamespace(
        entry_id="entry-id",
        runtime_data=SimpleNamespace(coordinator=coordinator),
    )
    entities = []
    await async_setup_entry(None, entry, entities.extend)
    return entities


def _by_unique_id(entities, unique_id):
    return next(entity for entity in entities if entity.unique_id == unique_id)


async def test_sensor_platform_exposes_expected_metadata_and_values():
    entities = await _entities(_system())

    outside = _by_unique_id(entities, "entry-id_outside_temperature")
    assert outside.native_value == 12.5
    assert outside.device_class is SensorDeviceClass.TEMPERATURE
    assert outside.state_class is SensorStateClass.MEASUREMENT

    power = _by_unique_id(entities, "entry-id_wpm_111_electrical_power")
    assert power.native_value == 1500.0
    assert power.device_class is SensorDeviceClass.POWER
    assert power.native_unit_of_measurement == UnitOfPower.WATT

    runtime = _by_unique_id(entities, "entry-id_wpm_111_compressor_runtime")
    assert runtime.native_value == 820
    assert runtime.device_class is SensorDeviceClass.DURATION
    assert runtime.native_unit_of_measurement == UnitOfTime.MINUTES

    energy = _by_unique_id(entities, "entry-id_wpm_111_electrical_energy_total")
    assert energy.native_value == 1.2346
    assert energy.device_class is SensorDeviceClass.ENERGY
    assert energy.native_unit_of_measurement == UnitOfEnergy.KILO_WATT_HOUR
    assert energy.state_class is SensorStateClass.TOTAL_INCREASING

    status = _by_unique_id(entities, "entry-id_wpm_111_status")
    assert status.native_value == "ready"
    assert status.device_class is SensorDeviceClass.ENUM
    assert "hot_water" in status.options


async def test_sensor_platform_respects_single_probe_configuration():
    entities = await _entities(_system(buffer_sensors=1, dhw_sensors=1))
    unique_ids = {entity.unique_id for entity in entities}

    assert "entry-id_buffer_upper_temperature" not in unique_ids
    assert "entry-id_dhw_lower_temperature" not in unique_ids
    assert "entry-id_buffer_temperature" in unique_ids
    assert "entry-id_dhw_temperature" in unique_ids


async def test_sensor_platform_adds_second_probe_sensors_when_configured():
    entities = await _entities(_system(buffer_sensors=2, dhw_sensors=2))

    assert _by_unique_id(entities, "entry-id_buffer_upper_temperature").native_value == 36.0
    assert _by_unique_id(entities, "entry-id_dhw_lower_temperature").native_value == 47.0


async def test_dhw_analytics_diagnostic_sensor_is_disabled_by_default():
    entities = await _entities(_system())

    estimated = _by_unique_id(entities, "entry-id_dhw_estimated_start_temperature")
    assert estimated.native_value == 45.0
    assert estimated.entity_category is EntityCategory.DIAGNOSTIC
    assert estimated.entity_registry_enabled_default is False

    predicted = _by_unique_id(entities, "entry-id_dhw_predicted_next_heating_start")
    assert predicted.extra_state_attributes == {
        "temperature_slope_c_per_hour": -0.4,
        "estimated_start_temperature_c": 45.0,
        "samples_used": 12,
        "method": "linear_temperature_extrapolation",
    }


async def test_multi_wpm_platform_adds_system_energy_totals():
    system = _system(wpm_count=2)
    entities = await _entities(system)

    total = _by_unique_id(entities, "entry-id_system_electrical_energy_total")
    assert total.native_value == 1.2346
    assert total.suggested_object_id == "ovum_total_electrical_energy_total"
    assert total.state_class is SensorStateClass.TOTAL_INCREASING
