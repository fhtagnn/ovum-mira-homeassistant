from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class InstallationOptions:
    """Physical installation details that the MIRA register map does not expose safely.

    These are intentionally explicit user choices. We do not infer whether a probe
    exists from implausible temperature values.
    """

    heating_buffer_sensor_count: int = 1
    hot_water_sensor_count: int = 1
    heating_circuit_1_room_sensor: bool = False
    pv_sensor_module_installed: bool = False
    enable_ems_writes: bool = False

    def __post_init__(self) -> None:
        if self.heating_buffer_sensor_count not in (1, 2):
            raise ValueError("heating_buffer_sensor_count must be 1 or 2")
        if self.hot_water_sensor_count not in (1, 2):
            raise ValueError("hot_water_sensor_count must be 1 or 2")
