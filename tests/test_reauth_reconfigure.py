from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.selector import TextSelector
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ovum_mira.const import (
    CONF_BUFFER_SENSOR_COUNT,
    CONF_DHW_SENSOR_COUNT,
    CONF_HK1_ROOM_SENSOR,
    CONF_LOGIN_CODE,
    CONF_WPM_COUNT,
    DOMAIN,
)

HOST = "192.0.2.10"
PORT = 502


def _entry(*, host=HOST, port=PORT, login="1234", wpm_count=1):
    return MockConfigEntry(
        domain=DOMAIN,
        title="OVUM MIRA",
        unique_id=f"{host}:{port}",
        data={
            CONF_HOST: host,
            CONF_PORT: port,
            CONF_WPM_COUNT: wpm_count,
            CONF_LOGIN_CODE: login,
            CONF_BUFFER_SENSOR_COUNT: 1,
            CONF_DHW_SENSOR_COUNT: 2,
            CONF_HK1_ROOM_SENSOR: True,
        },
    )


def _temporary_system_mock(*outcomes):
    """Return a recorded factory for temporary-system async contexts."""
    remaining = iter(outcomes)
    opener = MagicMock()

    @asynccontextmanager
    async def temporary_system(*args, **kwargs):
        outcome = next(remaining)
        if isinstance(outcome, BaseException):
            raise outcome
        yield outcome

    opener.side_effect = temporary_system
    return opener


async def _start_reauth(hass, entry):
    return await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_REAUTH,
            "entry_id": entry.entry_id,
        },
        data=dict(entry.data),
    )


async def _start_reconfigure(hass, entry):
    return await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_RECONFIGURE,
            "entry_id": entry.entry_id,
        },
    )


async def test_reauth_success_updates_only_login_code(hass):
    entry = _entry(login="1111")
    entry.add_to_hass(hass)
    result = await _start_reauth(hass, entry)

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"

    opener = _temporary_system_mock(SimpleNamespace())
    with (
        patch(
            "custom_components.ovum_mira.config_flow.async_get_temporary_system",
            new=opener,
        ),
        patch.object(hass.config_entries, "async_schedule_reload") as schedule_reload,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_LOGIN_CODE: "2222"},
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_LOGIN_CODE] == "2222"
    assert entry.data[CONF_HOST] == HOST
    assert entry.data[CONF_PORT] == PORT
    assert opener.call_args.kwargs["login_code"] == 2222
    assert opener.call_args.kwargs["options"].hot_water_sensor_count == 2
    assert opener.call_args.kwargs["options"].heating_circuit_1_room_sensor is True
    schedule_reload.assert_called_once_with(entry.entry_id)


async def test_reauth_invalid_login_can_be_corrected(hass):
    entry = _entry(login="1111")
    entry.add_to_hass(hass)
    result = await _start_reauth(hass, entry)

    with patch(
        "custom_components.ovum_mira.config_flow.async_get_temporary_system"
    ) as opener:
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_LOGIN_CODE: "not-a-number"},
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_LOGIN_CODE: "invalid_login_code"}
    opener.assert_not_called()

    with (
        patch(
            "custom_components.ovum_mira.config_flow.async_get_temporary_system",
            new=_temporary_system_mock(SimpleNamespace()),
        ),
        patch.object(hass.config_entries, "async_schedule_reload"),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_LOGIN_CODE: "3333"},
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_LOGIN_CODE] == "3333"


async def test_reauth_auth_error_is_reported(hass):
    entry = _entry()
    entry.add_to_hass(hass)
    result = await _start_reauth(hass, entry)

    with patch(
        "custom_components.ovum_mira.config_flow.async_get_temporary_system",
        new=_temporary_system_mock(PermissionError("denied")),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_LOGIN_CODE: "9999"},
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"
    assert result["errors"] == {"base": "invalid_auth"}
    assert entry.data[CONF_LOGIN_CODE] == "1234"


async def test_reconfigure_success_updates_connection_and_unique_id(hass):
    entry = _entry()
    entry.add_to_hass(hass)
    result = await _start_reconfigure(hass, entry)

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"
    login_field, login_selector = next(
        (key, value)
        for key, value in result["data_schema"].schema.items()
        if key.schema == CONF_LOGIN_CODE
    )
    assert isinstance(login_selector, TextSelector)
    assert login_selector.config["type"] == "password"
    assert login_field.description == {"suggested_value": "1234"}

    opener = _temporary_system_mock(SimpleNamespace())
    new_host = "192.0.2.20"
    new_port = 1502
    with (
        patch(
            "custom_components.ovum_mira.config_flow.async_get_temporary_system",
            new=opener,
        ),
        patch.object(hass.config_entries, "async_schedule_reload") as schedule_reload,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_HOST: new_host,
                CONF_PORT: new_port,
                CONF_WPM_COUNT: 2,
                CONF_LOGIN_CODE: "5678",
            },
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_HOST] == new_host
    assert entry.data[CONF_PORT] == new_port
    assert entry.data[CONF_WPM_COUNT] == 2
    assert entry.data[CONF_LOGIN_CODE] == "5678"
    assert entry.unique_id == f"{new_host}:{new_port}"
    assert opener.call_args.args[1:] == (new_host, new_port, 2)
    assert opener.call_args.kwargs["login_code"] == 5678
    schedule_reload.assert_called_once_with(entry.entry_id)


async def test_reconfigure_connection_error_can_be_retried(hass):
    entry = _entry()
    entry.add_to_hass(hass)
    result = await _start_reconfigure(hass, entry)
    opener = _temporary_system_mock(OSError("offline"), SimpleNamespace())

    with (
        patch(
            "custom_components.ovum_mira.config_flow.async_get_temporary_system",
            new=opener,
        ),
        patch.object(hass.config_entries, "async_schedule_reload"),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_HOST: HOST,
                CONF_PORT: PORT,
                CONF_WPM_COUNT: 1,
            },
        )
        assert result["type"] is FlowResultType.FORM
        assert result["errors"] == {"base": "cannot_connect"}

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_HOST: HOST,
                CONF_PORT: PORT,
                CONF_WPM_COUNT: 2,
            },
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_WPM_COUNT] == 2
    assert opener.call_count == 2


async def test_reconfigure_invalid_login_does_not_replace_working_configuration(hass):
    entry = _entry(login="1234")
    entry.add_to_hass(hass)
    result = await _start_reconfigure(hass, entry)

    with patch(
        "custom_components.ovum_mira.config_flow.async_get_temporary_system"
    ) as opener:
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_HOST: HOST,
                CONF_PORT: PORT,
                CONF_WPM_COUNT: 1,
                CONF_LOGIN_CODE: "not-a-number",
            },
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_LOGIN_CODE: "invalid_login_code"}
    assert entry.data[CONF_LOGIN_CODE] == "1234"
    opener.assert_not_called()


async def test_reconfigure_rejected_login_does_not_replace_working_configuration(hass):
    entry = _entry(login="1234")
    entry.add_to_hass(hass)
    result = await _start_reconfigure(hass, entry)

    with patch(
        "custom_components.ovum_mira.config_flow.async_get_temporary_system",
        new=_temporary_system_mock(PermissionError("denied")),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_HOST: HOST,
                CONF_PORT: PORT,
                CONF_WPM_COUNT: 1,
                CONF_LOGIN_CODE: "9999",
            },
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}
    assert entry.data[CONF_LOGIN_CODE] == "1234"


async def test_reconfigure_can_disable_login(hass):
    entry = _entry(login="1234")
    entry.add_to_hass(hass)
    result = await _start_reconfigure(hass, entry)
    opener = _temporary_system_mock(SimpleNamespace())

    with (
        patch(
            "custom_components.ovum_mira.config_flow.async_get_temporary_system",
            new=opener,
        ),
        patch.object(hass.config_entries, "async_schedule_reload"),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_HOST: HOST,
                CONF_PORT: PORT,
                CONF_WPM_COUNT: 1,
                CONF_LOGIN_CODE: "",
            },
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_LOGIN_CODE] == ""
    assert opener.call_args.kwargs["login_code"] is None


async def test_reconfigure_rejects_host_port_used_by_another_entry(hass):
    entry = _entry()
    entry.add_to_hass(hass)
    other = _entry(host="192.0.2.30", port=1502)
    other.add_to_hass(hass)
    result = await _start_reconfigure(hass, entry)

    opener = _temporary_system_mock(SimpleNamespace())
    with patch(
        "custom_components.ovum_mira.config_flow.async_get_temporary_system",
        new=opener,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_HOST: "192.0.2.30",
                CONF_PORT: 1502,
                CONF_WPM_COUNT: 1,
            },
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert entry.data[CONF_HOST] == HOST
    assert entry.data[CONF_PORT] == PORT
    assert entry.unique_id == f"{HOST}:{PORT}"
    assert opener.call_count == 1
