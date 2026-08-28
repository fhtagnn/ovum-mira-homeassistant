from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.ovum_mira.coordinator import OvumMiraCoordinator
from custom_components.ovum_mira.ovum_mira_modbus import WpmStatus


def _wpm(electrical: float, thermal: float):
    return SimpleNamespace(
        readings=SimpleNamespace(
            electrical_power=electrical,
            thermal_power=thermal,
            status=WpmStatus.READY,
            compressor_runtime_minutes=0,
        )
    )


async def test_initialize_energy_restores_counters_and_sets_live_baselines(hass):
    system = SimpleNamespace(wpms=[_wpm(1.0, 3.0), _wpm(2.0, 7.0)])
    coordinator = OvumMiraCoordinator(hass, system, "entry-id")
    stored = {
        "units": {
            "111": {
                "total_electrical_kwh": 10.0,
                "total_thermal_kwh": 30.0,
            },
            "112": {
                "total_electrical_kwh": 20.0,
                "total_thermal_kwh": 70.0,
            },
        }
    }
    now_utc = datetime(2026, 8, 25, 8, 0, tzinfo=UTC)
    local_now = datetime(2026, 8, 25, 10, 0, tzinfo=UTC)

    with (
        patch.object(coordinator._store, "async_load", new=AsyncMock(return_value=stored)),
        patch(
            "custom_components.ovum_mira.coordinator.dt_util.utcnow",
            return_value=now_utc,
        ),
        patch(
            "custom_components.ovum_mira.coordinator.dt_util.now",
            return_value=local_now,
        ),
    ):
        await coordinator.async_initialize_energy()

    assert coordinator.energy.by_unit[111].total_electrical_kwh == 10.0
    assert coordinator.energy.by_unit[112].total_thermal_kwh == 70.0
    assert coordinator.energy.by_unit[111]._last_utc == now_utc
    assert coordinator.energy.by_unit[111]._last_electrical_kw == 1.0
    assert coordinator.energy.by_unit[112]._last_thermal_kw == 7.0


def test_update_derived_data_integrates_and_schedules_all_derived_state(hass):
    system = SimpleNamespace(wpms=[_wpm(1.0, 4.0)])
    coordinator = OvumMiraCoordinator(hass, system, "entry-id")
    start = datetime(2026, 8, 25, 8, 0, tzinfo=UTC)
    coordinator.energy.by_unit[111].set_baseline(
        now_utc=start,
        local_now=start,
        electrical_kw=1.0,
        thermal_kw=4.0,
        status=WpmStatus.READY,
        compressor_runtime_minutes=0,
    )
    system.wpms[0].readings.electrical_power = 2.0
    system.wpms[0].readings.thermal_power = 6.0
    delay_save = MagicMock()
    maybe_sample = MagicMock()
    analytics_update = MagicMock()

    with (
        patch(
            "custom_components.ovum_mira.coordinator.dt_util.utcnow",
            return_value=start + timedelta(seconds=60),
        ),
        patch(
            "custom_components.ovum_mira.coordinator.dt_util.now",
            return_value=start + timedelta(seconds=60),
        ),
        patch.object(coordinator._store, "async_delay_save", new=delay_save),
        patch.object(coordinator.history, "maybe_sample", new=maybe_sample),
        patch.object(coordinator.dhw_analytics, "update", new=analytics_update),
    ):
        coordinator._update_derived_data()

    acc = coordinator.energy.by_unit[111]
    assert acc.total_electrical_kwh > 0
    assert acc.total_thermal_kwh > 0
    delay_save.assert_called_once_with(coordinator.energy.as_storage_dict, 60)
    maybe_sample.assert_called_once_with(system)
    analytics_update.assert_called_once_with(system, coordinator.history)
