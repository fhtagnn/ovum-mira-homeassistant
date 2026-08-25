from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

from homeassistant.helpers.entity import EntityCategory

from custom_components.ovum_mira.number import async_setup_entry


def _settings(**values):
    data = dict(values)
    data.update(
        {
            "async_set_pv_target_temperature": AsyncMock(),
            "async_set_room_target_heating": AsyncMock(),
            "async_set_pv_raise": AsyncMock(),
            "async_set_pv_reduce": AsyncMock(),
        }
    )
    return SimpleNamespace(**data)


async def test_number_setup_exposes_detected_controls_and_executes_bindings():
    hot_water_settings = _settings(pv_target_temperature=55)
    buffer_settings = _settings(pv_target_temperature=42)
    circuit1_settings = _settings(
        room_target_heating=21.5,
        pv_raise=4,
        pv_reduce=-3,
    )
    circuit2_settings = _settings(
        room_target_heating=20.0,
        pv_raise=2,
        pv_reduce=-2,
    )
    system = SimpleNamespace(
        hsm=SimpleNamespace(
            hot_water=SimpleNamespace(settings=hot_water_settings),
            heating_buffer=SimpleNamespace(settings=buffer_settings),
            heating_circuit_1=SimpleNamespace(
                settings=circuit1_settings,
                room_readings=object(),
            ),
            heating_circuit_2=SimpleNamespace(
                settings=circuit2_settings,
                room_readings=None,
            ),
        )
    )
    coordinator = SimpleNamespace(
        system=system,
        last_update_success=True,
        async_request_refresh=AsyncMock(),
    )
    entry = SimpleNamespace(
        entry_id="entry-id",
        runtime_data=SimpleNamespace(coordinator=coordinator),
    )
    captured = []

    await async_setup_entry(None, entry, captured.extend)

    assert len(captured) == 8
    by_key = {entity.unique_id.removeprefix("entry-id_"): entity for entity in captured}

    assert by_key["dhw_pv_target"].native_value == 55
    assert by_key["dhw_pv_target"].entity_category is EntityCategory.CONFIG
    assert by_key["dhw_pv_target"].entity_registry_enabled_default is False

    assert by_key["buffer_pv_target"].native_value == 42
    assert by_key["hk1_room_target_heating"].native_value == 21.5
    assert by_key["hk1_room_target_heating"].native_step == 0.5
    assert by_key["hk1_room_target_heating"].entity_registry_enabled_default is False
    assert by_key["hk2_room_target_heating"].entity_registry_enabled_default is True
    assert by_key["hk1_pv_raise"].native_value == 4
    assert by_key["hk1_pv_reduce"].native_value == -3

    await by_key["dhw_pv_target"].async_set_native_value(56)
    hot_water_settings.async_set_pv_target_temperature.assert_awaited_once_with(56)

    await by_key["buffer_pv_target"].async_set_native_value(43)
    buffer_settings.async_set_pv_target_temperature.assert_awaited_once_with(43)

    await by_key["hk1_room_target_heating"].async_set_native_value(22.0)
    circuit1_settings.async_set_room_target_heating.assert_awaited_once_with(22.0)

    await by_key["hk1_pv_raise"].async_set_native_value(5)
    circuit1_settings.async_set_pv_raise.assert_awaited_once_with(5)

    await by_key["hk1_pv_reduce"].async_set_native_value(-4)
    circuit1_settings.async_set_pv_reduce.assert_awaited_once_with(-4)


async def test_number_setup_skips_absent_optional_systems():
    system = SimpleNamespace(
        hsm=SimpleNamespace(
            hot_water=None,
            heating_buffer=None,
            heating_circuit_1=None,
            heating_circuit_2=None,
        )
    )
    coordinator = SimpleNamespace(
        system=system,
        last_update_success=True,
        async_request_refresh=AsyncMock(),
    )
    entry = SimpleNamespace(
        entry_id="entry-id",
        runtime_data=SimpleNamespace(coordinator=coordinator),
    )
    captured = []

    await async_setup_entry(None, entry, captured.extend)

    assert captured == []
