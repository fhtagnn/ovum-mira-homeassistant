from dataclasses import dataclass

from modbus_connection import ModbusTcpParams
from modbus_connection.tmodbus import ModbusConnection

from .const import FIRST_WPM_UNIT, HSM_UNIT, MAX_WPM_COUNT
from .ovum_mira_modbus import InstallationOptions, OvumMiraSystem


@dataclass(slots=True)
class OvumRuntime:
    connection: ModbusConnection
    system: OvumMiraSystem
    coordinator: object | None = None
    legacy_migration: object | None = None


async def async_open_system(
    host: str,
    port: int,
    wpm_count: int,
    *,
    login_code: int | None,
    options: InstallationOptions,
) -> tuple[ModbusConnection, OvumMiraSystem]:
    """Open a TCP connection and initialize an OVUM MIRA system."""
    if not 1 <= wpm_count <= MAX_WPM_COUNT:
        raise ValueError(f"wpm_count must be between 1 and {MAX_WPM_COUNT}")

    connection = ModbusConnection(ModbusTcpParams(host=host, port=port))
    wpm_units = [
        connection.for_unit(FIRST_WPM_UNIT + index)
        for index in range(wpm_count)
    ]
    system = OvumMiraSystem(
        connection.for_unit(HSM_UNIT),
        wpm_units,
        options=options,
    )
    try:
        if login_code is not None:
            await system.async_login(login_code)
        await system.async_setup()
        await system.async_update()
    except Exception:
        await connection.close()
        raise
    return connection, system
