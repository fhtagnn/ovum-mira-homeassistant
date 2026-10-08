from collections.abc import AsyncIterator, Sequence
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass

from modbus_connection import ModbusTcpParams, ModbusUnit

from homeassistant.components.modbus import async_get_temporary_unit, async_get_unit
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_BUFFER_SENSOR_COUNT,
    CONF_DHW_SENSOR_COUNT,
    CONF_HK1_ROOM_SENSOR,
    FIRST_WPM_UNIT,
    HSM_UNIT,
    MAX_WPM_COUNT,
)
from .ovum_mira_modbus import InstallationOptions, OvumMiraSystem


@dataclass(slots=True)
class OvumRuntime:
    system: OvumMiraSystem
    coordinator: object | None = None


def installation_options_from_entry(entry: ConfigEntry) -> InstallationOptions:
    """Build physical installation options from one config entry."""
    config = {**entry.data, **entry.options}
    return InstallationOptions(
        heating_buffer_sensor_count=config.get(CONF_BUFFER_SENSOR_COUNT, 1),
        hot_water_sensor_count=config.get(CONF_DHW_SENSOR_COUNT, 1),
        heating_circuit_1_room_sensor=config.get(CONF_HK1_ROOM_SENSOR, False),
    )


def _wpm_unit_ids(wpm_count: int) -> tuple[int, ...]:
    """Return configured WPM unit IDs after validating the topology."""
    if not 1 <= wpm_count <= MAX_WPM_COUNT:
        raise ValueError(f"wpm_count must be between 1 and {MAX_WPM_COUNT}")
    return tuple(FIRST_WPM_UNIT + index for index in range(wpm_count))


async def _async_initialize_system(
    hsm_unit: ModbusUnit,
    wpm_units: Sequence[ModbusUnit],
    *,
    login_code: int | None,
    options: InstallationOptions,
) -> OvumMiraSystem:
    """Initialize an OVUM system over already acquired Modbus units."""
    system = OvumMiraSystem(hsm_unit, wpm_units, options=options)
    if login_code is not None:
        await system.async_login(login_code)
    await system.async_setup()
    await system.async_update()
    return system


async def async_get_system(
    hass: HomeAssistant,
    entry: ConfigEntry,
    host: str,
    port: int,
    wpm_count: int,
    *,
    login_code: int | None,
    options: InstallationOptions,
) -> OvumMiraSystem:
    """Initialize OVUM over Home Assistant's shared Modbus connection."""
    wpm_unit_ids = _wpm_unit_ids(wpm_count)
    params = ModbusTcpParams(host=host, port=port)
    hsm_unit = async_get_unit(hass, entry, params, HSM_UNIT)
    wpm_units = [
        async_get_unit(hass, entry, params, unit_id) for unit_id in wpm_unit_ids
    ]
    return await _async_initialize_system(
        hsm_unit,
        wpm_units,
        login_code=login_code,
        options=options,
    )


@asynccontextmanager
async def async_get_temporary_system(
    hass: HomeAssistant,
    host: str,
    port: int,
    wpm_count: int,
    *,
    login_code: int | None,
    options: InstallationOptions,
) -> AsyncIterator[OvumMiraSystem]:
    """Probe OVUM over temporary units released when the config flow is done."""
    wpm_unit_ids = _wpm_unit_ids(wpm_count)
    params = ModbusTcpParams(host=host, port=port)
    async with AsyncExitStack() as stack:
        hsm_unit = await stack.enter_async_context(
            async_get_temporary_unit(hass, params, HSM_UNIT)
        )
        wpm_units = [
            await stack.enter_async_context(
                async_get_temporary_unit(hass, params, unit_id)
            )
            for unit_id in wpm_unit_ids
        ]
        yield await _async_initialize_system(
            hsm_unit,
            wpm_units,
            login_code=login_code,
            options=options,
        )
