from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, call, patch

from modbus_connection import ModbusTcpParams
import pytest
from homeassistant.components.modbus.connection import DATA_MODBUS_CONNECTIONS
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ovum_mira.const import DOMAIN
from custom_components.ovum_mira.ovum_mira_modbus import InstallationOptions
from custom_components.ovum_mira.runtime import (
    async_get_system,
    async_get_temporary_system,
)


async def test_get_system_rejects_invalid_wpm_count():
    """Reject invalid topology before acquiring a shared Modbus unit."""
    with (
        patch("custom_components.ovum_mira.runtime.async_get_unit") as get_unit,
        pytest.raises(ValueError, match="wpm_count"),
    ):
        await async_get_system(
            MagicMock(),
            MagicMock(),
            "192.0.2.10",
            502,
            0,
            login_code=None,
            options=InstallationOptions(),
        )

    get_unit.assert_not_called()


async def test_get_system_acquires_shared_units_and_initializes():
    """Acquire HSM/WPM units through Home Assistant and initialize MIRA."""
    hass = MagicMock()
    entry = MagicMock()
    get_unit = MagicMock(side_effect=lambda _hass, _entry, _params, unit_id: f"unit-{unit_id}")

    system = MagicMock()
    system.async_login = AsyncMock()
    system.async_setup = AsyncMock()
    system.async_update = AsyncMock()

    with (
        patch("custom_components.ovum_mira.runtime.async_get_unit", new=get_unit),
        patch(
            "custom_components.ovum_mira.runtime.OvumMiraSystem",
            return_value=system,
        ) as system_cls,
    ):
        returned_system = await async_get_system(
            hass,
            entry,
            "192.0.2.10",
            502,
            2,
            login_code=1234,
            options=InstallationOptions(),
        )

    params = ModbusTcpParams(host="192.0.2.10", port=502)
    assert get_unit.call_args_list == [
        call(hass, entry, params, 110),
        call(hass, entry, params, 111),
        call(hass, entry, params, 112),
    ]
    system_cls.assert_called_once_with(
        "unit-110",
        ["unit-111", "unit-112"],
        options=InstallationOptions(),
    )
    system.async_login.assert_awaited_once_with(1234)
    system.async_setup.assert_awaited_once_with()
    system.async_update.assert_awaited_once_with()
    assert returned_system is system


async def test_get_system_uses_one_ha_managed_connection_and_releases_it(hass):
    """Hold every OVUM unit on one central connection until entry unload."""
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)

    connection = MagicMock()
    connection.for_unit.side_effect = lambda unit_id: f"unit-{unit_id}"
    connection.close = AsyncMock()

    system = MagicMock()
    system.async_login = AsyncMock()
    system.async_setup = AsyncMock()
    system.async_update = AsyncMock()

    with (
        patch(
            "homeassistant.components.modbus.connection.ModbusConnection",
            return_value=connection,
        ) as connection_cls,
        patch(
            "custom_components.ovum_mira.runtime.OvumMiraSystem",
            return_value=system,
        ),
    ):
        await async_get_system(
            hass,
            entry,
            "192.0.2.10",
            502,
            2,
            login_code=None,
            options=InstallationOptions(),
        )

    connection_cls.assert_called_once_with(
        ModbusTcpParams(host="192.0.2.10", port=502)
    )
    assert [item.args[0] for item in connection.for_unit.call_args_list] == [
        110,
        111,
        112,
    ]
    [shared] = hass.data[DATA_MODBUS_CONNECTIONS].values()
    assert shared.units == {entry.entry_id: {110, 111, 112}}

    await entry._async_process_on_unload(hass)
    await hass.async_block_till_done()

    assert not hass.data[DATA_MODBUS_CONNECTIONS]
    connection.close.assert_awaited_once_with()


async def test_temporary_system_shares_and_releases_one_ha_connection(hass):
    """Keep config-flow units together and close after the probe context."""
    connection = MagicMock()
    connection.for_unit.side_effect = lambda unit_id: f"unit-{unit_id}"
    connection.close = AsyncMock()

    system = MagicMock()
    system.async_login = AsyncMock()
    system.async_setup = AsyncMock()
    system.async_update = AsyncMock()

    with (
        patch(
            "homeassistant.components.modbus.connection.ModbusConnection",
            return_value=connection,
        ) as connection_cls,
        patch(
            "custom_components.ovum_mira.runtime.OvumMiraSystem",
            return_value=system,
        ),
    ):
        async with async_get_temporary_system(
            hass,
            "192.0.2.10",
            502,
            2,
            login_code=None,
            options=InstallationOptions(),
        ):
            [shared] = hass.data[DATA_MODBUS_CONNECTIONS].values()
            assert shared.transient == 3
            connection.close.assert_not_awaited()

    connection_cls.assert_called_once_with(
        ModbusTcpParams(host="192.0.2.10", port=502)
    )
    assert not hass.data[DATA_MODBUS_CONNECTIONS]
    connection.close.assert_awaited_once_with()


async def test_temporary_system_releases_every_unit_after_probe():
    """Release temporary HSM/WPM holds in reverse acquisition order."""
    acquired: list[int] = []
    released: list[int] = []

    @asynccontextmanager
    async def temporary_unit(_hass, _params, unit_id):
        acquired.append(unit_id)
        try:
            yield f"unit-{unit_id}"
        finally:
            released.append(unit_id)

    system = MagicMock()
    system.async_login = AsyncMock()
    system.async_setup = AsyncMock()
    system.async_update = AsyncMock()

    with (
        patch(
            "custom_components.ovum_mira.runtime.async_get_temporary_unit",
            new=temporary_unit,
        ),
        patch(
            "custom_components.ovum_mira.runtime.OvumMiraSystem",
            return_value=system,
        ),
    ):
        async with async_get_temporary_system(
            MagicMock(),
            "192.0.2.10",
            502,
            2,
            login_code=None,
            options=InstallationOptions(),
        ) as returned_system:
            assert returned_system is system
            assert released == []

    assert acquired == [110, 111, 112]
    assert released == [112, 111, 110]
    system.async_login.assert_not_awaited()


async def test_temporary_system_releases_units_when_initialization_fails():
    """Never leak config-flow holds when the controller probe fails."""
    released: list[int] = []

    @asynccontextmanager
    async def temporary_unit(_hass, _params, unit_id):
        try:
            yield f"unit-{unit_id}"
        finally:
            released.append(unit_id)

    system = MagicMock()
    system.async_login = AsyncMock()
    system.async_setup = AsyncMock()
    system.async_update = AsyncMock(side_effect=OSError("offline"))

    with (
        patch(
            "custom_components.ovum_mira.runtime.async_get_temporary_unit",
            new=temporary_unit,
        ),
        patch(
            "custom_components.ovum_mira.runtime.OvumMiraSystem",
            return_value=system,
        ),
        pytest.raises(OSError, match="offline"),
    ):
        async with async_get_temporary_system(
            MagicMock(),
            "192.0.2.10",
            502,
            1,
            login_code=None,
            options=InstallationOptions(),
        ):
            pass

    assert released == [111, 110]
