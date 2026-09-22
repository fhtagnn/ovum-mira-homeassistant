from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from modbus_connection import ModbusConnectionError
import pytest

from homeassistant.exceptions import HomeAssistantError

from custom_components.ovum_mira.const import DOMAIN
from custom_components.ovum_mira.ovum_mira_modbus import SwitchState
from custom_components.ovum_mira.switch import OvumHotWaterMainSwitch


@pytest.mark.parametrize(
    "error",
    [
        ModbusConnectionError("connection lost"),
        ValueError("write verification failed"),
    ],
)
async def test_entity_write_failures_are_translated(error):
    """Platform actions expose device write failures as translated HA errors."""
    settings = SimpleNamespace(
        enabled=SwitchState.OFF,
        async_set_enabled=AsyncMock(side_effect=error),
    )
    coordinator = SimpleNamespace(
        system=SimpleNamespace(
            hsm=SimpleNamespace(hot_water=SimpleNamespace(settings=settings)),
            async_ensure_login=AsyncMock(),
        ),
        last_update_success=True,
        async_request_refresh=AsyncMock(),
    )
    entity = OvumHotWaterMainSwitch(coordinator, "entry-id")

    with pytest.raises(HomeAssistantError) as exc_info:
        await entity.async_turn_on()

    assert exc_info.value.translation_domain == DOMAIN
    assert exc_info.value.translation_key == "write_failed"
    assert exc_info.value.translation_placeholders == {"error": str(error)}
    coordinator.async_request_refresh.assert_not_awaited()


async def test_entity_renews_login_before_writing():
    events = []

    async def ensure_login():
        events.append("login")

    async def set_enabled(_enabled):
        events.append("write")

    settings = SimpleNamespace(
        enabled=SwitchState.OFF,
        async_set_enabled=AsyncMock(side_effect=set_enabled),
    )
    system = SimpleNamespace(
        hsm=SimpleNamespace(hot_water=SimpleNamespace(settings=settings)),
        async_ensure_login=AsyncMock(side_effect=ensure_login),
    )
    coordinator = SimpleNamespace(
        system=system,
        last_update_success=True,
        async_request_refresh=AsyncMock(),
    )

    await OvumHotWaterMainSwitch(coordinator, "entry-id").async_turn_on()

    assert events == ["login", "write"]
    coordinator.async_request_refresh.assert_awaited_once_with()


async def test_rejected_runtime_login_starts_reauthentication():
    entry = MagicMock()
    config_entries = SimpleNamespace(
        async_get_entry=MagicMock(return_value=entry),
    )
    hass = SimpleNamespace(config_entries=config_entries)
    settings = SimpleNamespace(
        enabled=SwitchState.OFF,
        async_set_enabled=AsyncMock(),
    )
    coordinator = SimpleNamespace(
        hass=hass,
        system=SimpleNamespace(
            hsm=SimpleNamespace(hot_water=SimpleNamespace(settings=settings)),
            async_ensure_login=AsyncMock(
                side_effect=PermissionError("login rejected")
            ),
        ),
        last_update_success=True,
        async_request_refresh=AsyncMock(),
    )

    with pytest.raises(HomeAssistantError) as exc_info:
        await OvumHotWaterMainSwitch(coordinator, "entry-id").async_turn_on()

    assert exc_info.value.translation_key == "write_failed"
    entry.async_start_reauth.assert_called_once_with(hass)
    settings.async_set_enabled.assert_not_awaited()
    coordinator.async_request_refresh.assert_not_awaited()
