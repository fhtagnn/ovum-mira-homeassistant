from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from custom_components.ovum_mira import async_migrate_entry
from custom_components.ovum_mira.const import (
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
    )
    update = MagicMock()

    with patch.object(hass.config_entries, "async_update_entry", new=update):
        assert await async_migrate_entry(hass, entry) is True

    update.assert_called_once()
    updated = update.call_args.kwargs
    assert updated["version"] == 4
    assert updated["minor_version"] == 0
    data = updated["data"]
    assert data["host"] == "192.0.2.10"
    assert data["port"] == 502
    assert data[CONF_LOGIN_CODE] == "1234"
    assert data[CONF_WPM_COUNT] == 1
    assert data[CONF_PV_SENSOR_MODULE] is False
    assert CONF_WPM_UNIT not in data
    assert "migrate_legacy" not in data
    assert data["custom_future_field"] == "keep-me"


async def test_current_schema_requires_no_migration(hass):
    entry = SimpleNamespace(version=4, data={"host": "192.0.2.10"})
    update = MagicMock()

    with patch.object(hass.config_entries, "async_update_entry", new=update):
        assert await async_migrate_entry(hass, entry) is True

    update.assert_not_called()
