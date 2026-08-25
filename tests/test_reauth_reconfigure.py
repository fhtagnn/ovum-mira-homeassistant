from __future__ import annotations

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
    CONF_PV_SENSOR_MODULE,
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
            CONF_PV_SENSOR_MODULE: False,
        },
    )


def _open_result():
    return SimpleNamespace(close=AsyncMock()), SimpleNamespace()


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

    connection, system = _open_result()
    opener = AsyncMock(return_value=(connection, system))
    with (
        patch("custom_components.ovum_mira.config_flow.async_open_system", new=opener),
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
    connection.close.assert_awaited_once_with()
    assert opener.await_args.kwargs["login_code"] == 2222
    assert opener.await_args.kwargs["options"].hot_water_sensor_count == 2
    assert opener.await_args.kwargs["options"].heating_circuit_1_room_sensor is True
    schedule_reload.assert_called_once_with(entry.entry_id)


async def test_reauth_invalid_login_can_be_corrected(hass):
    entry = _entry(login="1111")
    entry.add_to_hass(hass)
    result = await _start_reauth(hass, entry)

    with patch("custom_components.ovum_mira.config_flow.async_open_system") as opener:
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_LOGIN_CODE: "not-a-number"},
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_LOGIN_CODE: "invalid_login_code"}
    opener.assert_not_called()

    connection, system = _open_result()
    with (
        patch(
            "custom_components.ovum_mira.config_flow.async_open_system",
            new=AsyncMock(return_value=(connection, system)),
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
        "custom_components.ovum_mira.config_flow.async_open_system",
        new=AsyncMock(side_effect=PermissionError("denied")),
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

    connection, system = _open_result()
    opener = AsyncMock(return_value=(connection, system))
    new_host = "192.0.2.20"
    new_port = 1502
    with (
        patch("custom_components.ovum_mira.config_flow.async_open_system", new=opener),
        patch.object(hass.config_entries, "async_schedule_reload") as schedule_reload,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_HOST: new_host,
                CONF_PORT: new_port,
                CONF_WPM_COUNT: 2,
            },
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_HOST] == new_host
    assert entry.data[CONF_PORT] == new_port
    assert entry.data[CONF_WPM_COUNT] == 2
    assert entry.data[CONF_LOGIN_CODE] == "1234"
    assert entry.unique_id == f"{new_host}:{new_port}"
    connection.close.assert_awaited_once_with()
    assert opener.await_args.args == (new_host, new_port, 2)
    assert opener.await_args.kwargs["login_code"] == 1234
    schedule_reload.assert_called_once_with(entry.entry_id)


async def test_reconfigure_connection_error_can_be_retried(hass):
    entry = _entry()
    entry.add_to_hass(hass)
    result = await _start_reconfigure(hass, entry)
    opener = AsyncMock(side_effect=[OSError("offline"), _open_result()])

    with (
        patch("custom_components.ovum_mira.config_flow.async_open_system", new=opener),
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
    assert opener.await_count == 2


async def test_reconfigure_rejects_host_port_used_by_another_entry(hass):
    entry = _entry()
    entry.add_to_hass(hass)
    other = _entry(host="192.0.2.30", port=1502)
    other.add_to_hass(hass)
    result = await _start_reconfigure(hass, entry)

    connection, system = _open_result()
    with patch(
        "custom_components.ovum_mira.config_flow.async_open_system",
        new=AsyncMock(return_value=(connection, system)),
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
    connection.close.assert_awaited_once_with()
