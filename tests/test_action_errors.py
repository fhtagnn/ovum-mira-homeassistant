from types import SimpleNamespace
from unittest.mock import AsyncMock

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
        system=SimpleNamespace(hsm=SimpleNamespace(hot_water=SimpleNamespace(settings=settings))),
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
