from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ovum_mira.const import (
    CONF_BUFFER_SENSOR_COUNT,
    CONF_DHW_SENSOR_COUNT,
    CONF_HK1_ROOM_SENSOR,
    CONF_LOGIN_CODE,
    CONF_MIGRATE_LEGACY,
    CONF_PV_SENSOR_MODULE,
    CONF_WPM_COUNT,
    DOMAIN,
)
from custom_components.ovum_mira.ovum_mira_modbus import BufferSystemType, HeatingCircuitType, SwitchState

HOST = "192.0.2.10"
PORT = 502


def _open_result(*, buffer=True, dhw=True, hk1=True):
    connection = SimpleNamespace(close=AsyncMock())
    capabilities = SimpleNamespace(
        heating_buffer_type=BufferSystemType.BUFFER if buffer else BufferSystemType.NONE,
        hot_water_installed=SwitchState.ON if dhw else SwitchState.OFF,
        heating_circuit_1_type=HeatingCircuitType.MIXED if hk1 else HeatingCircuitType.NONE,
    )
    system = SimpleNamespace(hsm=SimpleNamespace(capabilities=capabilities))
    return connection, system


async def _start_user_flow(hass):
    return await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})


async def _submit_connection(hass, flow_id, *, login="", wpm_count=1):
    return await hass.config_entries.flow.async_configure(
        flow_id,
        {
            CONF_HOST: HOST,
            CONF_PORT: PORT,
            CONF_WPM_COUNT: wpm_count,
            CONF_LOGIN_CODE: login,
        },
    )


async def test_full_user_flow(hass):
    """Test a successful setup including detected installation options."""
    result = await _start_user_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    connection, system = _open_result()
    with patch(
        "custom_components.ovum_mira.config_flow.async_open_system",
        new=AsyncMock(return_value=(connection, system)),
    ):
        result = await _submit_connection(hass, result["flow_id"], login="1234", wpm_count=2)

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "installation"
    assert connection.close.await_count == 1

    # Creating a config entry triggers Home Assistant to set the integration up.
    # Keep this config-flow test isolated from the real Modbus transport; setup
    # and unload behavior are tested separately.
    with patch(
        "custom_components.ovum_mira.async_setup_entry",
        new=AsyncMock(return_value=True),
    ) as setup_entry:
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_BUFFER_SENSOR_COUNT: 1,
                CONF_DHW_SENSOR_COUNT: 2,
                CONF_HK1_ROOM_SENSOR: True,
                CONF_PV_SENSOR_MODULE: False,
                CONF_MIGRATE_LEGACY: True,
            },
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "OVUM MIRA"
    assert result["data"] == {
        CONF_HOST: HOST,
        CONF_PORT: PORT,
        CONF_WPM_COUNT: 2,
        CONF_LOGIN_CODE: "1234",
    }
    assert dict(result["result"].options) == {
        CONF_BUFFER_SENSOR_COUNT: 1,
        CONF_DHW_SENSOR_COUNT: 2,
        CONF_HK1_ROOM_SENSOR: True,
        CONF_PV_SENSOR_MODULE: False,
        CONF_MIGRATE_LEGACY: True,
    }
    assert result["result"].version == 5
    assert result["result"].unique_id == f"{HOST}:{PORT}"
    setup_entry.assert_awaited_once()


async def test_invalid_login_code_can_be_corrected(hass):
    """Test validation and recovery for a non-numeric login code."""
    result = await _start_user_flow(hass)
    result = await _submit_connection(hass, result["flow_id"], login="not-a-number")

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_LOGIN_CODE: "invalid_login_code"}

    with patch(
        "custom_components.ovum_mira.config_flow.async_open_system",
        new=AsyncMock(return_value=_open_result()),
    ):
        result = await _submit_connection(hass, result["flow_id"], login="")

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "installation"


async def test_connection_error_can_be_retried(hass):
    """Test recovery from a temporary connection error."""
    result = await _start_user_flow(hass)
    opener = AsyncMock(side_effect=[OSError("offline"), _open_result()])

    with patch("custom_components.ovum_mira.config_flow.async_open_system", new=opener):
        result = await _submit_connection(hass, result["flow_id"])
        assert result["type"] is FlowResultType.FORM
        assert result["errors"] == {"base": "cannot_connect"}

        result = await _submit_connection(hass, result["flow_id"])

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "installation"
    assert opener.await_count == 2


async def test_auth_error_can_be_retried(hass):
    """Test recovery from a rejected Modbus login code."""
    result = await _start_user_flow(hass)
    opener = AsyncMock(side_effect=[PermissionError("denied"), _open_result()])

    with patch("custom_components.ovum_mira.config_flow.async_open_system", new=opener):
        result = await _submit_connection(hass, result["flow_id"], login="1234")
        assert result["errors"] == {"base": "invalid_auth"}
        result = await _submit_connection(hass, result["flow_id"], login="1234")

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "installation"


async def test_duplicate_device_is_rejected(hass):
    """Test that the same host and port cannot be configured twice."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=f"{HOST}:{PORT}",
        data={CONF_HOST: HOST, CONF_PORT: PORT},
    )
    entry.add_to_hass(hass)

    result = await _start_user_flow(hass)
    with patch("custom_components.ovum_mira.config_flow.async_open_system") as opener:
        result = await _submit_connection(hass, result["flow_id"])

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    opener.assert_not_called()


async def test_installation_form_only_shows_detected_features(hass):
    """Test conditional installation fields when optional systems are absent."""
    result = await _start_user_flow(hass)
    with patch(
        "custom_components.ovum_mira.config_flow.async_open_system",
        new=AsyncMock(return_value=_open_result(buffer=False, dhw=False, hk1=False)),
    ):
        result = await _submit_connection(hass, result["flow_id"])

    schema_keys = {key.schema for key in result["data_schema"].schema}
    assert schema_keys == {CONF_PV_SENSOR_MODULE, CONF_MIGRATE_LEGACY}


async def test_options_flow(hass):
    """Test updating physical installation options and automatic reload."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_HOST: HOST,
            CONF_PORT: PORT,
            CONF_WPM_COUNT: 1,
        },
        options={
            CONF_BUFFER_SENSOR_COUNT: 1,
            CONF_DHW_SENSOR_COUNT: 1,
            CONF_HK1_ROOM_SENSOR: False,
            CONF_PV_SENSOR_MODULE: False,
            CONF_MIGRATE_LEGACY: False,
        },
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"

    with patch.object(hass.config_entries, "async_schedule_reload") as schedule_reload:
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {
                CONF_BUFFER_SENSOR_COUNT: 2,
                CONF_DHW_SENSOR_COUNT: 2,
                CONF_HK1_ROOM_SENSOR: True,
                CONF_PV_SENSOR_MODULE: True,
                CONF_MIGRATE_LEGACY: True,
            },
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_BUFFER_SENSOR_COUNT] == 2
    assert entry.options[CONF_DHW_SENSOR_COUNT] == 2
    assert entry.options[CONF_MIGRATE_LEGACY] is True
    assert entry.options[CONF_HK1_ROOM_SENSOR] is True
    assert entry.options[CONF_PV_SENSOR_MODULE] is True
    schedule_reload.assert_called_once_with(entry.entry_id)
