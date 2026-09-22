"""Typed Modbus model for the OVUM MIRA Plus feature level.

The official Plus table contains 75 rows. Six repeat Start-level registers and
remain owned by the existing Start model:

* WW_DESIREDTEMP
* HK1_DESIREDTEMP / HK1_ACTUALVALUE
* HK2_DESIREDTEMP / HK2_ACTUALVALUE
* HK1_ACTUALROOMTEMP

This module defines the remaining 69 Plus addresses. It deliberately does not
attach them to the live Home Assistant polling path; feature activation and
entities belong to a separate change so Start-only installations never poll
licensed addresses.

The spreadsheet marks the repeated HK1/HK2 process setpoint and actual-value
registers writable, while the manual's feature overview calls them read-only
and real controllers reject writes. The existing model therefore continues to
expose those four values read-only.
"""

from modbus_connection.model import Component, enum, float32, integer, string

from .enums import (
    BufferLoadingStatus,
    CoolingBufferLoadingStatus,
    DhwRequestStatus,
    FreshWaterDrawStatus,
    HeatingCircuitTargetMode,
    HeatingCircuitType,
    SwitchState,
)
from .fields import ovum_boolean
from .safe_write import write_if_changed
from .validators import range_validator, snap_step


class PlusIdentity(Component):
    """Identity available on HSM and WPM units with Plus enabled."""

    serial_number = string(56010, 10)


class PlusHotWaterReadings(Component):
    request_status = enum(55012, DhwRequestStatus, signed=True)
    fresh_water_draw_status = enum(55015, FreshWaterDrawStatus, signed=True)
    circulation_pump_active = ovum_boolean(55016)
    circulation_temperature = float32(55017, unit="°C")
    # This is whether DHW follows the central vacation state, not that state's value.
    follows_vacation = enum(55019, SwitchState)


class PlusHotWaterSettings(Component):
    fresh_water_target_temperature = integer(
        55014,
        writable=range_validator(10, 65),
        unit="°C",
    )

    async def async_set_fresh_water_target_temperature(self, temperature: int) -> bool:
        return await write_if_changed(
            self,
            "fresh_water_target_temperature",
            int(temperature),
        )


class PlusHeatingBufferReadings(Component):
    # Only 1=heating and 2=cooling are documented; keep this open for any
    # controller state not covered by that incomplete value list.
    mode = integer(55022)
    loading_status = enum(55030, BufferLoadingStatus, signed=True)


class PlusCoolingBufferCapabilities(Component):
    installed = enum(55040, SwitchState)


class PlusCoolingBufferReadings(Component):
    lower_temperature = float32(55041, unit="°C")
    effective_target_temperature = float32(55043, unit="°C")
    loading_status = enum(55045, CoolingBufferLoadingStatus, signed=True)


class PlusCascadeReadings(Component):
    hot_water_request = ovum_boolean(55058)
    heating_request = ovum_boolean(55059)
    cooling_request = ovum_boolean(55060)


class PlusPvReleaseReadings(Component):
    """PV release states.

    The spreadsheet's ``#Register`` column says two words for these values,
    while their documented data type is s16. The data-type definition is
    authoritative, so every value is represented by one register.
    """

    heat_pump_hot_water = integer(55079)
    heat_pump_heating = integer(55081)
    second_stage_hot_water = integer(55083)
    second_stage_heating = integer(55085)


class PlusHeatingCircuitCapabilities(Component):
    """Plus-only type detection for heating circuits 3 and 4."""

    circuit_type = enum(56070, HeatingCircuitType)


class PlusHeatingCircuitRoomReadings(Component):
    """Room reading shared by heating circuits 1 through 4 (25-register stride)."""

    actual_room_temperature = float32(56152, stride=25, unit="°C")


class PlusHeatingCircuitExtendedSettings(Component):
    """Plus settings shared by heating circuits 1 through 4."""

    cooling_room_target = float32(
        56150,
        stride=25,
        writable=range_validator(0, 50, step=0.5),
        unit="°C",
    )
    # These flags configure participation in vacation mode; they do not report
    # whether the central vacation mode is currently active.
    follows_vacation = enum(56154, SwitchState, stride=25, writable=True)
    vacation_heating_target = integer(
        56155,
        stride=25,
        writable=range_validator(0, 50),
        unit="°C",
    )
    vacation_cooling_target = integer(
        56156,
        stride=25,
        writable=range_validator(0, 50),
        unit="°C",
    )
    target_mode = enum(
        56157,
        HeatingCircuitTargetMode,
        stride=25,
        writable=True,
    )
    fixed_heating_target = integer(
        56158,
        stride=25,
        writable=range_validator(0, 100),
        unit="°C",
    )
    fixed_cooling_target = integer(
        56159,
        stride=25,
        writable=range_validator(0, 100),
        unit="°C",
    )
    heating_limit = float32(
        56160,
        stride=25,
        writable=range_validator(0, 100, step=0.5),
        unit="°C",
    )

    async def async_set_cooling_room_target(self, temperature: float) -> bool:
        return await self._async_set_half_degree("cooling_room_target", temperature)

    async def async_set_follows_vacation(self, follows: bool) -> bool:
        return await write_if_changed(
            self,
            "follows_vacation",
            SwitchState.ON if follows else SwitchState.OFF,
        )

    async def async_set_vacation_heating_target(self, temperature: int) -> bool:
        return await write_if_changed(
            self,
            "vacation_heating_target",
            int(temperature),
        )

    async def async_set_vacation_cooling_target(self, temperature: int) -> bool:
        return await write_if_changed(
            self,
            "vacation_cooling_target",
            int(temperature),
        )

    async def async_set_target_mode(self, mode: HeatingCircuitTargetMode) -> bool:
        return await write_if_changed(self, "target_mode", mode)

    async def async_set_fixed_heating_target(self, temperature: int) -> bool:
        return await write_if_changed(
            self,
            "fixed_heating_target",
            int(temperature),
        )

    async def async_set_fixed_cooling_target(self, temperature: int) -> bool:
        return await write_if_changed(
            self,
            "fixed_cooling_target",
            int(temperature),
        )

    async def async_set_heating_limit(self, temperature: float) -> bool:
        return await self._async_set_half_degree("heating_limit", temperature)

    async def _async_set_half_degree(self, field: str, value: float) -> bool:
        return await write_if_changed(
            self,
            field,
            value,
            normalize=lambda v: snap_step(float(v), low=0, step=0.5),
            abs_tol=0.01,
        )
