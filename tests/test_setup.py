from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ovum_mira import async_setup_entry, async_unload_entry
from custom_components.ovum_mira.const import (
    CONF_BUFFER_SENSOR_COUNT,
    CONF_DHW_SENSOR_COUNT,
    CONF_HK1_ROOM_SENSOR,
    CONF_LOGIN_CODE,
    CONF_PV_SENSOR_MODULE,
    CONF_WPM_COUNT,
    DOMAIN,
    PLATFORMS,
)
from custom_components.ovum_mira.ovum_mira_modbus import InstallationOptions
from custom_components.ovum_mira.runtime import OvumRuntime

HOST = "192.0.2.10"
PORT = 502


def _entry(*, options: dict | None = None) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_HOST: HOST,
            CONF_PORT: PORT,
            CONF_WPM_COUNT: 2,
            CONF_LOGIN_CODE: "1234",
            CONF_BUFFER_SENSOR_COUNT: 1,
            CONF_DHW_SENSOR_COUNT: 1,
            CONF_HK1_ROOM_SENSOR: False,
            CONF_PV_SENSOR_MODULE: False,
        },
        options=options or {},
    )
    return entry


async def test_setup_entry_initializes_runtime_and_platforms(hass):
    """Set up runtime data with installation options and forward platforms."""
    entry = _entry(
        options={
            CONF_BUFFER_SENSOR_COUNT: 2,
            CONF_DHW_SENSOR_COUNT: 2,
            CONF_HK1_ROOM_SENSOR: True,
            CONF_PV_SENSOR_MODULE: True,
        }
    )
    entry.add_to_hass(hass)

    connection = SimpleNamespace(close=AsyncMock())
    system = object()
    coordinator = SimpleNamespace(
        async_initialize=AsyncMock(),
        async_save_persistent_state=AsyncMock(),
    )
    opener = AsyncMock(return_value=(connection, system))
    forward = AsyncMock()

    with (
        patch("custom_components.ovum_mira.async_open_system", new=opener),
        patch("custom_components.ovum_mira.OvumMiraCoordinator", return_value=coordinator) as coordinator_cls,
        patch.object(hass.config_entries, "async_forward_entry_setups", new=forward),
    ):
        assert await async_setup_entry(hass, entry) is True

    opener.assert_awaited_once_with(
        HOST,
        PORT,
        2,
        login_code=1234,
        options=InstallationOptions(
            heating_buffer_sensor_count=2,
            hot_water_sensor_count=2,
            heating_circuit_1_room_sensor=True,
            pv_sensor_module_installed=True,
            enable_ems_writes=False,
        ),
    )
    coordinator_cls.assert_called_once_with(hass, system, entry.entry_id)
    coordinator.async_initialize.assert_awaited_once_with()
    forward.assert_awaited_once_with(entry, PLATFORMS)
    assert entry.runtime_data.connection is connection
    assert entry.runtime_data.system is system
    assert entry.runtime_data.coordinator is coordinator


async def test_setup_entry_rejects_invalid_auth(hass):
    """Turn a rejected device login into Home Assistant auth failure."""
    entry = _entry()
    opener = AsyncMock(side_effect=PermissionError("denied"))

    with (
        patch("custom_components.ovum_mira.async_open_system", new=opener),
        pytest.raises(ConfigEntryAuthFailed, match="login was rejected"),
    ):
        await async_setup_entry(hass, entry)


async def test_setup_entry_retries_network_failure(hass):
    """Turn a temporary network error into ConfigEntryNotReady."""
    entry = _entry()
    opener = AsyncMock(side_effect=OSError("offline"))

    with (
        patch("custom_components.ovum_mira.async_open_system", new=opener),
        pytest.raises(ConfigEntryNotReady, match="offline"),
    ):
        await async_setup_entry(hass, entry)


async def test_setup_entry_closes_connection_if_coordinator_init_fails(hass):
    """Do not leak the Modbus connection when derived-state initialization fails."""
    entry = _entry()
    entry.add_to_hass(hass)

    connection = SimpleNamespace(close=AsyncMock())
    system = object()
    coordinator = SimpleNamespace(async_initialize=AsyncMock(side_effect=RuntimeError("store failed")))
    forward = AsyncMock()

    with (
        patch(
            "custom_components.ovum_mira.async_open_system",
            new=AsyncMock(return_value=(connection, system)),
        ),
        patch("custom_components.ovum_mira.OvumMiraCoordinator", return_value=coordinator),
        patch.object(hass.config_entries, "async_forward_entry_setups", new=forward),
        pytest.raises(RuntimeError, match="store failed"),
    ):
        await async_setup_entry(hass, entry)

    connection.close.assert_awaited_once_with()
    forward.assert_not_awaited()


async def test_unload_entry_persists_and_closes_connection(hass):
    """Persist derived state and close Modbus after successful platform unload."""
    entry = _entry()
    coordinator = SimpleNamespace(async_save_persistent_state=AsyncMock())
    connection = SimpleNamespace(close=AsyncMock())
    entry.runtime_data = OvumRuntime(connection, object(), coordinator)
    unload = AsyncMock(return_value=True)

    with patch.object(hass.config_entries, "async_unload_platforms", new=unload):
        assert await async_unload_entry(hass, entry) is True

    unload.assert_awaited_once_with(entry, PLATFORMS)
    coordinator.async_save_persistent_state.assert_awaited_once_with()
    connection.close.assert_awaited_once_with()


async def test_unload_entry_keeps_connection_when_platform_unload_fails(hass):
    """Keep runtime resources alive if Home Assistant cannot unload all platforms."""
    entry = _entry()
    coordinator = SimpleNamespace(async_save_persistent_state=AsyncMock())
    connection = SimpleNamespace(close=AsyncMock())
    entry.runtime_data = OvumRuntime(connection, object(), coordinator)

    with patch.object(
        hass.config_entries,
        "async_unload_platforms",
        new=AsyncMock(return_value=False),
    ):
        assert await async_unload_entry(hass, entry) is False

    coordinator.async_save_persistent_state.assert_not_awaited()
    connection.close.assert_not_awaited()
