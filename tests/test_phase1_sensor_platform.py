from types import SimpleNamespace

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import UnitOfEnergy, UnitOfTime
from homeassistant.helpers.entity import EntityCategory

from custom_components.ovum_mira.energy import MODE_COOLING, MODE_HOT_WATER, EnergyBook
from custom_components.ovum_mira.ovum_mira_modbus import InstallationOptions, SwitchState, WpmStatus
from custom_components.ovum_mira.sensor import async_setup_entry


def _system():
    options = InstallationOptions(
        heating_buffer_sensor_count=1,
        hot_water_sensor_count=1,
    )
    return SimpleNamespace(
        hsm=SimpleNamespace(
            options=options,
            common=SimpleNamespace(outside_temperature=12.0),
            hot_water=SimpleNamespace(
                readings=SimpleNamespace(
                    primary_temperature=48.0,
                    effective_target_temperature=50.0,
                    lower_temperature=None,
                ),
                settings=SimpleNamespace(enabled=SwitchState.ON),
            ),
            heating_buffer=None,
            heating_circuit_1=None,
            heating_circuit_2=None,
        ),
        wpms=[
            SimpleNamespace(
                readings=SimpleNamespace(
                    demand_percent=25,
                    electrical_power=1.0,
                    thermal_power=4.0,
                    condenser_inlet_temperature=30.0,
                    condenser_outlet_temperature=35.0,
                    compressor_runtime_minutes=100,
                    status=WpmStatus.READY,
                )
            )
        ],
    )


async def test_phase1_sensors_have_expected_identity_and_defaults():
    system = _system()
    energy = EnergyBook([111])
    energy.by_unit[111].modes[MODE_HOT_WATER].total_electrical_kwh = 2.5
    energy.by_unit[111].modes[MODE_HOT_WATER].total_thermal_kwh = 10.0
    energy.by_unit[111].modes[MODE_COOLING].total_electrical_kwh = 1.0
    coordinator = SimpleNamespace(
        system=system,
        last_update_success=True,
        energy=energy,
        dhw_analytics=SimpleNamespace(
            last_start=None,
            predicted_next_start=None,
            current_slope_c_per_hour=None,
            estimated_trigger_temperature_c=None,
            slope_samples_used=0,
            average_heating_interval_hours=24.0,
            median_heating_interval_hours=23.5,
        ),
    )
    entry = SimpleNamespace(
        entry_id="entry-id",
        runtime_data=SimpleNamespace(coordinator=coordinator),
    )
    entities = []

    await async_setup_entry(None, entry, entities.extend)
    by_unique_id = {entity.unique_id: entity for entity in entities}

    hot_water_energy = by_unique_id["entry-id_hot_water_electrical_energy"]
    assert hot_water_energy.suggested_object_id == "ovum_hot_water_electrical_energy"
    assert hot_water_energy.native_value == 2.5
    assert hot_water_energy.device_class is SensorDeviceClass.ENERGY
    assert hot_water_energy.native_unit_of_measurement == UnitOfEnergy.KILO_WATT_HOUR
    assert hot_water_energy.state_class is SensorStateClass.TOTAL_INCREASING

    work_factor = by_unique_id["entry-id_hot_water_work_factor"]
    assert work_factor.native_value == 4.0
    assert work_factor.state_class is SensorStateClass.MEASUREMENT

    cooling = by_unique_id["entry-id_cooling_electrical_energy"]
    assert cooling.entity_registry_enabled_default is False

    interval = by_unique_id["entry-id_dhw_average_heating_interval"]
    assert interval.native_value == 24.0
    assert interval.device_class is SensorDeviceClass.DURATION
    assert interval.native_unit_of_measurement == UnitOfTime.HOURS

    median_interval = by_unique_id["entry-id_dhw_median_heating_interval"]
    assert median_interval.native_value == 23.5
    assert median_interval.entity_category is EntityCategory.DIAGNOSTIC
    assert median_interval.entity_registry_enabled_default is False

    assert "entry-id_wpm_111_compressor_starts_today" in by_unique_id
