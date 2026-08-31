from types import SimpleNamespace
from unittest.mock import MagicMock

from custom_components.ovum_mira.const import CONF_LOGIN_CODE
from custom_components.ovum_mira.diagnostics import async_get_config_entry_diagnostics


async def test_diagnostics_redacts_login_and_includes_analysis_history(hass):
    accumulator = SimpleNamespace(as_storage_dict=MagicMock(return_value={"total_electrical_kwh": 12.3}))
    analytics = SimpleNamespace(
        diagnostics=MagicMock(return_value={"last_start": "2026-08-24T10:00:00+00:00"})
    )
    history = SimpleNamespace(
        export_dict=MagicMock(return_value={"samples": [{"timestamp_utc": "2026-08-24T10:00:00+00:00"}]})
    )
    coordinator = SimpleNamespace(
        energy=SimpleNamespace(by_unit={111: accumulator}),
        dhw_analytics=analytics,
        history=history,
    )
    entry = SimpleNamespace(
        data={"host": "192.0.2.10", CONF_LOGIN_CODE: "1234"},
        options={"hot_water_sensor_count": 1},
        runtime_data=SimpleNamespace(coordinator=coordinator),
    )

    result = await async_get_config_entry_diagnostics(hass, entry)

    assert result["entry_data"]["host"] == "192.0.2.10"
    assert result["entry_data"][CONF_LOGIN_CODE] != "1234"
    assert result["entry_options"] == {"hot_water_sensor_count": 1}
    assert result["energy"] == {"111": {"total_electrical_kwh": 12.3}}
    assert result["dhw_analytics"] == {"last_start": "2026-08-24T10:00:00+00:00"}
    assert result["analysis_history"] == {
        "samples": [{"timestamp_utc": "2026-08-24T10:00:00+00:00"}]
    }
    assert result["notes"]["history_is_independent_of_recorder"] is True

    accumulator.as_storage_dict.assert_called_once_with()
    analytics.diagnostics.assert_called_once_with()
    history.export_dict.assert_called_once_with()
