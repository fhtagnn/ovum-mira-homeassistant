from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from . import OvumConfigEntry
from .const import CONF_LOGIN_CODE, INTEGRATION_VERSION

_TO_REDACT = {CONF_LOGIN_CODE}


def _energy_export(coordinator) -> dict[str, Any]:
    return {
        str(unit_id): accumulator.as_storage_dict()
        for unit_id, accumulator in coordinator.energy.by_unit.items()
    }


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: OvumConfigEntry,
) -> dict[str, Any]:
    """Return a user-downloadable diagnostics/analysis export."""
    coordinator = entry.runtime_data.coordinator
    return {
        "integration_version": INTEGRATION_VERSION,
        "entry_data": async_redact_data(dict(entry.data), _TO_REDACT),
        "entry_options": dict(entry.options),
        "energy": _energy_export(coordinator),
        "dhw_analytics": coordinator.dhw_analytics.diagnostics(),
        "analysis_history": coordinator.history.export_dict(),
        "notes": {
            "history_purpose": "Compact synchronized samples for DHW-cycle and circulation analysis.",
            "history_is_independent_of_recorder": True,
            "dhw_prediction_method": "Linear regression of recent non-DHW temperature samples, extrapolated to the median temperature observed at recent WPM HOT_WATER start transitions.",
            "thermal_energy_is_not_metering_grade": True,
        },
    }
