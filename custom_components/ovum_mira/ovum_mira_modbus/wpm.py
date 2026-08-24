from __future__ import annotations

from modbus_connection.model import Component, enum, float32, int32, integer, string

from .enums import WpmStatus


class WpmIdentity(Component):
    system_name = string(56000, 10)


class WpmReadings(Component):
    demand_percent = integer(56020, unit="%")
    electrical_power = float32(56021, unit="kW")
    # OVUM explicitly notes that thermal power is not a calibrated measurement.
    thermal_power = float32(56023, unit="kW")
    status = enum(56025, WpmStatus, signed=True)
    condenser_inlet_temperature = float32(56026, unit="°C")
    condenser_outlet_temperature = float32(56028, unit="°C")
    # XLS names this "Betriebsstunden", but Type-Information explicitly says unit "min".
    compressor_runtime_minutes = int32(56030, unit="min")

    @property
    def compressor_on_time(self) -> int | None:
        """Backward-compatible alias; value is minutes, not hours."""
        return self.compressor_runtime_minutes


class OvumWpm:
    """Typed model of one WPM unit (111..118)."""

    def __init__(self, unit) -> None:
        self._unit = unit
        self.identity = WpmIdentity(unit)
        self.readings = WpmReadings(unit)

    async def async_setup(self) -> None:
        await self.identity.async_update()

    async def async_update(self) -> None:
        await self.readings.async_update()
