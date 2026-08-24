from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.ovum_mira.ovum_mira_modbus import InstallationOptions
from custom_components.ovum_mira.runtime import async_open_system


async def test_open_system_rejects_invalid_wpm_count():
    """Reject invalid topology before opening a Modbus connection."""
    with pytest.raises(ValueError, match="wpm_count"):
        await async_open_system(
            "192.0.2.10",
            502,
            0,
            login_code=None,
            options=InstallationOptions(),
        )


async def test_open_system_initializes_units_and_logs_in():
    """Open the expected HSM/WPM units and initialize the MIRA system."""
    connection = MagicMock()
    connection.for_unit.side_effect = lambda unit: f"unit-{unit}"
    connection.close = AsyncMock()

    system = MagicMock()
    system.async_login = AsyncMock()
    system.async_setup = AsyncMock()
    system.async_update = AsyncMock()

    with (
        patch("custom_components.ovum_mira.runtime.ModbusConnection", return_value=connection),
        patch("custom_components.ovum_mira.runtime.OvumMiraSystem", return_value=system) as system_cls,
    ):
        returned_connection, returned_system = await async_open_system(
            "192.0.2.10",
            502,
            2,
            login_code=1234,
            options=InstallationOptions(),
        )

    assert returned_connection is connection
    assert returned_system is system
    assert [call.args[0] for call in connection.for_unit.call_args_list] == [111, 112, 110]
    system_cls.assert_called_once()
    system.async_login.assert_awaited_once_with(1234)
    system.async_setup.assert_awaited_once_with()
    system.async_update.assert_awaited_once_with()
    connection.close.assert_not_awaited()


async def test_open_system_closes_connection_on_failure():
    """Ensure a failed initial update never leaks the Modbus connection."""
    connection = MagicMock()
    connection.for_unit.side_effect = lambda unit: f"unit-{unit}"
    connection.close = AsyncMock()

    system = MagicMock()
    system.async_login = AsyncMock()
    system.async_setup = AsyncMock()
    system.async_update = AsyncMock(side_effect=OSError("offline"))

    with (
        patch("custom_components.ovum_mira.runtime.ModbusConnection", return_value=connection),
        patch("custom_components.ovum_mira.runtime.OvumMiraSystem", return_value=system),
        pytest.raises(OSError, match="offline"),
    ):
        await async_open_system(
            "192.0.2.10",
            502,
            1,
            login_code=None,
            options=InstallationOptions(),
        )

    system.async_login.assert_not_awaited()
    connection.close.assert_awaited_once_with()
