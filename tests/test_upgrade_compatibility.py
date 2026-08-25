from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import patch

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import UnitOfEnergy
from homeassistant.helpers.storage import Store

from custom_components.ovum_mira.coordinator import OvumMiraCoordinator
from custom_components.ovum_mira.dhw_analytics import DhwAnalytics
from custom_components.ovum_mira.energy import EnergyBook
from custom_components.ovum_mira.entity import OvumMiraEntity
from custom_components.ovum_mira.history import HistoryBook
from custom_components.ovum_mira.sensor import (
    OvumSystemEnergySensor,
    OvumWpmEnergySensor,
    SensorDef,
)

ENTRY_ID = "01JUPGRADECOMPATIBILITY"
NOW = datetime(2026, 8, 25, 12, 0, tzinfo=UTC)


def _wpm_system():
    return SimpleNamespace(
        wpms=[
            SimpleNamespace(
                readings=SimpleNamespace(
                    electrical_power=0.0,
                    thermal_power=0.0,
                )
            )
        ]
    )


def test_public_beta_storage_keys_and_versions_are_stable(hass):
    coordinator = OvumMiraCoordinator(hass, _wpm_system(), ENTRY_ID)

    assert coordinator._store.key == f"ovum_mira.{ENTRY_ID}.energy"
    assert coordinator._store.version == 1
    assert coordinator.history._store.key == f"ovum_mira.{ENTRY_ID}.analysis_history"
    assert coordinator.history._store.version == 1
    assert coordinator.dhw_analytics._store.key == f"ovum_mira.{ENTRY_ID}.dhw_analytics"
    assert coordinator.dhw_analytics._store.version == 1


async def test_public_beta_energy_store_loads_without_reset(hass):
    stored = {
        "units": {
            "111": {
                "total_electrical_kwh": 123.4,
                "total_thermal_kwh": 456.7,
                "daily_electrical_kwh": 4.5,
                "daily_thermal_kwh": 16.2,
                "weekly_electrical_kwh": 27.3,
                "weekly_thermal_kwh": 98.1,
                "day_key": "2026-08-25",
                "week_key": "2026-W35",
            }
        }
    }
    await Store(hass, 1, f"ovum_mira.{ENTRY_ID}.energy").async_save(stored)
    coordinator = OvumMiraCoordinator(hass, _wpm_system(), ENTRY_ID)

    with (
        patch(
            "custom_components.ovum_mira.coordinator.dt_util.utcnow",
            return_value=NOW,
        ),
        patch(
            "custom_components.ovum_mira.coordinator.dt_util.now",
            return_value=NOW,
        ),
    ):
        await coordinator.async_initialize_energy()

    energy = coordinator.energy.by_unit[111]
    assert energy.total_electrical_kwh == 123.4
    assert energy.total_thermal_kwh == 456.7
    assert energy.daily_electrical_kwh == 4.5
    assert energy.weekly_thermal_kwh == 98.1


async def test_public_beta_history_store_loads_existing_samples(hass):
    stored = {
        "samples": [
            {
                "timestamp_utc": "2026-08-25T10:00:00+00:00",
                "outside_temperature_c": 21.0,
                "dhw_temperature_c": 47.2,
                "dhw_effective_target_c": 50.0,
                "dhw_enabled": "on",
                "buffer_temperature_c": 32.5,
                "wpm": [
                    {
                        "unit_id": 111,
                        "status": "ready",
                        "electrical_power_kw": 0.0,
                        "thermal_power_kw": 0.0,
                    }
                ],
            }
        ]
    }
    await Store(
        hass,
        1,
        f"ovum_mira.{ENTRY_ID}.analysis_history",
    ).async_save(stored)
    history = HistoryBook(hass, ENTRY_ID)

    with patch(
        "custom_components.ovum_mira.history.dt_util.utcnow",
        return_value=NOW,
    ):
        await history.async_load()

    assert len(history.samples) == 1
    assert history.samples[0].dhw_temperature_c == 47.2
    assert history.samples[0].wpm[0]["unit_id"] == 111


async def test_public_beta_dhw_analytics_store_loads_existing_events(hass):
    stored = {
        "start_events": [
            {
                "timestamp_utc": "2026-08-25T08:30:00+00:00",
                "temperature_c": 44.8,
            }
        ]
    }
    await Store(
        hass,
        1,
        f"ovum_mira.{ENTRY_ID}.dhw_analytics",
    ).async_save(stored)
    analytics = DhwAnalytics(hass, ENTRY_ID)

    await analytics.async_load()

    assert analytics.last_start == datetime(2026, 8, 25, 8, 30, tzinfo=UTC)
    assert analytics.estimated_trigger_temperature_c == 44.8


def test_energy_book_retains_temporarily_unconfigured_wpm_data():
    stored = {
        "units": {
            "111": {
                "total_electrical_kwh": 10.0,
                "total_thermal_kwh": 40.0,
            },
            "112": {
                "total_electrical_kwh": 20.0,
                "total_thermal_kwh": 80.0,
            },
        }
    }

    one_wpm = EnergyBook([111])
    one_wpm.load(stored)
    saved_with_one_wpm = one_wpm.as_storage_dict()

    assert saved_with_one_wpm["units"]["112"]["total_electrical_kwh"] == 20.0

    restored_two_wpm = EnergyBook([111, 112])
    restored_two_wpm.load(saved_with_one_wpm)

    assert restored_two_wpm.by_unit[112].total_electrical_kwh == 20.0
    assert restored_two_wpm.by_unit[112].total_thermal_kwh == 80.0


def test_public_beta_entity_and_statistics_identity_is_stable():
    coordinator = SimpleNamespace(
        system=SimpleNamespace(wpms=[]),
        last_update_success=True,
        energy=EnergyBook([111]),
    )

    stable_entities = {
        "outside_temperature": "ovum_outdoor_temperature",
        "dhw_temperature": "ovum_hot_water_temperature",
        "buffer_temperature": "ovum_heating_buffer_temperature",
        "hk1_mode": "ovum_heating_circuit_1_mode",
        "hot_water_main_switch": "ovum_hot_water_main_switch",
    }
    for key, object_id in stable_entities.items():
        entity = OvumMiraEntity(coordinator, ENTRY_ID, key)
        assert entity.unique_id == f"{ENTRY_ID}_{key}"
        assert entity.suggested_object_id == object_id

    energy_desc = SensorDef(
        key="electrical_energy_total",
        value=lambda energy: energy.total_electrical_kwh,
        device_class=SensorDeviceClass.ENERGY,
        unit=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
    )
    wpm_energy = OvumWpmEnergySensor(coordinator, ENTRY_ID, 111, energy_desc)
    total_energy = OvumSystemEnergySensor(coordinator, ENTRY_ID, energy_desc)

    assert wpm_energy.unique_id == f"{ENTRY_ID}_wpm_111_electrical_energy_total"
    assert wpm_energy.suggested_object_id == "ovum_wpm_1_electrical_energy_total"
    assert wpm_energy.device_class is SensorDeviceClass.ENERGY
    assert wpm_energy.native_unit_of_measurement == UnitOfEnergy.KILO_WATT_HOUR
    assert wpm_energy.state_class is SensorStateClass.TOTAL_INCREASING

    assert total_energy.unique_id == f"{ENTRY_ID}_system_electrical_energy_total"
    assert total_energy.suggested_object_id == "ovum_total_electrical_energy_total"
    assert total_energy.device_class is SensorDeviceClass.ENERGY
    assert total_energy.native_unit_of_measurement == UnitOfEnergy.KILO_WATT_HOUR
    assert total_energy.state_class is SensorStateClass.TOTAL_INCREASING
