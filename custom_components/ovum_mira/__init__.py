from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady

from .const import (
    CONF_BUFFER_SENSOR_COUNT,
    CONF_DHW_SENSOR_COUNT,
    CONF_HK1_ROOM_SENSOR,
    CONF_LOGIN_CODE,
    CONF_PV_SENSOR_MODULE,
    CONF_WPM_COUNT,
    CONF_WPM_UNIT,
    PLATFORMS,
)
from .coordinator import OvumMiraCoordinator
from .ovum_mira_modbus import InstallationOptions
from .runtime import OvumRuntime, async_open_system


type OvumConfigEntry = ConfigEntry[OvumRuntime]

_INSTALLATION_DEFAULTS = {
    CONF_BUFFER_SENSOR_COUNT: 1,
    CONF_DHW_SENSOR_COUNT: 1,
    CONF_HK1_ROOM_SENSOR: False,
    CONF_PV_SENSOR_MODULE: False,
}


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate older config entries without discarding user data."""
    if entry.version >= 5:
        return True

    data = dict(entry.data)
    options = dict(entry.options)

    if entry.version == 1:
        data.pop(CONF_WPM_UNIT, None)
        data[CONF_WPM_COUNT] = 1

    data.pop("migrate_legacy", None)

    # Since schema v5, physical installation settings live in options rather
    # than connection data. Existing option values win over legacy data.
    for key, default in _INSTALLATION_DEFAULTS.items():
        if key not in options:
            options[key] = data.get(key, default)
        data.pop(key, None)

    hass.config_entries.async_update_entry(
        entry,
        data=data,
        options=options,
        version=5,
        minor_version=0,
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: OvumConfigEntry) -> bool:
    """Set up OVUM MIRA from a config entry."""
    cfg = {**entry.data, **entry.options}
    options = InstallationOptions(
        heating_buffer_sensor_count=cfg.get(CONF_BUFFER_SENSOR_COUNT, 1),
        hot_water_sensor_count=cfg.get(CONF_DHW_SENSOR_COUNT, 1),
        heating_circuit_1_room_sensor=cfg.get(CONF_HK1_ROOM_SENSOR, False),
        pv_sensor_module_installed=cfg.get(CONF_PV_SENSOR_MODULE, False),
        enable_ems_writes=False,
    )
    login = entry.data.get(CONF_LOGIN_CODE)

    try:
        connection, system = await async_open_system(
            entry.data[CONF_HOST],
            entry.data[CONF_PORT],
            entry.data.get(CONF_WPM_COUNT, 1),
            login_code=int(login) if login not in (None, "") else None,
            options=options,
        )
    except PermissionError as err:
        raise ConfigEntryAuthFailed("OVUM MIRA login was rejected") from err
    except OSError as err:
        raise ConfigEntryNotReady(f"Unable to connect to OVUM MIRA: {err}") from err

    coordinator = OvumMiraCoordinator(hass, system, entry.entry_id)
    try:
        await coordinator.async_initialize()
    except Exception:
        await connection.close()
        raise

    entry.runtime_data = OvumRuntime(connection, system, coordinator)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: OvumConfigEntry) -> bool:
    """Unload OVUM MIRA and close the Modbus connection."""
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False
    await entry.runtime_data.coordinator.async_save_persistent_state()
    await entry.runtime_data.connection.close()
    return True
