from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from custom_components.ovum_mira import async_migrate_entry
from custom_components.ovum_mira.const import (
    CONF_BUFFER_SENSOR_COUNT,
    CONF_DHW_SENSOR_COUNT,
    CONF_HK1_ROOM_SENSOR,
    CONF_LOGIN_CODE,
    CONF_PV_SENSOR_MODULE,
    CONF_WPM_COUNT,
    CONF_WPM_UNIT,
)


async def test_migrate_v1_entry_preserves_connection_data_and_normalizes_schema(hass):
    entry = SimpleNamespace(
        version=1,
        data={
            "host": "192.0.2.10",
            "port": 502,
            CONF_LOGIN_CODE: "1234",
            CONF_WPM_UNIT: 111,
            "migrate_legacy": True,
            "custom_future_field": "keep-me",
        },
        options={},
    )
    update = MagicMock()

    with patch.object(hass.config_entries, "async_update_entry", new=update):
        assert await async_migrate_entry(hass, entry) is True

    update.assert_called_once()
    updated = update.call_args.kwargs
    assert updated["version"] == 5
    assert updated["minor_version"] == 0
    data = updated["data"]
    assert data["host"] == "192.0.2.10"
    assert data["port"] == 502
    assert data[CONF_LOGIN_CODE] == "1234"
    assert data[CONF_WPM_COUNT] == 1
    assert CONF_WPM_UNIT not in data
    assert "migrate_legacy" not in data
    assert data["custom_future_field"] == "keep-me"
    assert CONF_BUFFER_SENSOR_COUNT not in data
    assert CONF_DHW_SENSOR_COUNT not in data
    assert CONF_HK1_ROOM_SENSOR not in data
    assert CONF_PV_SENSOR_MODULE not in data
    assert updated["options"] == {
        CONF_BUFFER_SENSOR_COUNT: 1,
        CONF_DHW_SENSOR_COUNT: 1,
        CONF_HK1_ROOM_SENSOR: False,
        CONF_PV_SENSOR_MODULE: False,
    }


async def test_migrate_v4_moves_installation_settings_to_options(hass):
    entry = SimpleNamespace(
        version=4,
        data={
            "host": "192.0.2.10",
            "port": 502,
            CONF_LOGIN_CODE: "1234",
            CONF_WPM_COUNT: 2,
            CONF_BUFFER_SENSOR_COUNT: 2,
            CONF_DHW_SENSOR_COUNT: 1,
            CONF_HK1_ROOM_SENSOR: False,
            CONF_PV_SENSOR_MODULE: False,
            "custom_future_field": "keep-me",
        },
        options={
            CONF_DHW_SENSOR_COUNT: 2,
            CONF_HK1_ROOM_SENSOR: True,
        },
    )
    update = MagicMock()

    with patch.object(hass.config_entries, "async_update_entry", new=update):
        assert await async_migrate_entry(hass, entry) is True

    updated = update.call_args.kwargs
    assert updated["version"] == 5
    assert updated["data"] == {
        "host": "192.0.2.10",
        "port": 502,
        CONF_LOGIN_CODE: "1234",
        CONF_WPM_COUNT: 2,
        "custom_future_field": "keep-me",
    }
    # Existing options take precedence over old values in data.
    assert updated["options"] == {
        CONF_BUFFER_SENSOR_COUNT: 2,
        CONF_DHW_SENSOR_COUNT: 2,
        CONF_HK1_ROOM_SENSOR: True,
        CONF_PV_SENSOR_MODULE: False,
    }


async def test_current_schema_requires_no_migration(hass):
    entry = SimpleNamespace(
        version=5,
        data={"host": "192.0.2.10"},
        options={CONF_BUFFER_SENSOR_COUNT: 1},
    )
    update = MagicMock()

    with patch.object(hass.config_entries, "async_update_entry", new=update):
        assert await async_migrate_entry(hass, entry) is True

    update.assert_not_called()
