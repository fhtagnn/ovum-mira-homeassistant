from dataclasses import dataclass

from modbus_connection.model import Component, ComponentGroup, enum, float32, int32, integer, string

from .config import InstallationOptions
from .enums import BufferSystemType, HeatingCircuitMode, HeatingCircuitType, PvStatus, SwitchState
from .safe_write import write_if_changed
from .validators import range_validator, snap_step


class HsmCapabilities(Component):
    """Configuration values used once during setup/capability detection."""

    system_name = string(56000, 10)
    hot_water_installed = enum(55003, SwitchState)
    heating_buffer_type = enum(55020, BufferSystemType)
    heating_circuit_1_type = enum(56050, HeatingCircuitType)
    heating_circuit_2_type = enum(56060, HeatingCircuitType)


class HsmCommonReadings(Component):
    outside_temperature = float32(56048, unit="°C")


class HotWaterReadings(Component):
    effective_target_temperature = float32(55004, unit="°C")
    # With one DHW probe OVUM says the "upper" input is physically placed in
    # the lower third. With two probes it moves to the upper third.
    upper_temperature = float32(55007, unit="°C")
    lower_temperature = float32(55009, unit="°C")

    def __init__(self, unit, *, sensor_count: int) -> None:
        super().__init__(unit)
        if sensor_count == 1:
            self.restrict_fields(("effective_target_temperature", "upper_temperature"))

    @property
    def primary_temperature(self) -> float | None:
        return self.upper_temperature


class HotWaterSettings(Component):
    enabled = enum(55000, SwitchState, writable=True)
    target_temperature = integer(55001, writable=range_validator(0, 62), unit="°C")
    pv_target_temperature = integer(55002, writable=range_validator(0, 67), unit="°C")

    async def async_set_enabled(self, enabled: bool) -> bool:
        return await write_if_changed(self, "enabled", SwitchState.ON if enabled else SwitchState.OFF)

    async def async_set_target_temperature(self, temperature: int) -> bool:
        return await write_if_changed(self, "target_temperature", int(temperature))

    async def async_set_pv_target_temperature(self, temperature: int) -> bool:
        return await write_if_changed(self, "pv_target_temperature", int(temperature))


class HeatingBufferReadings(Component):
    effective_target_temperature = float32(55023, unit="°C")
    upper_temperature = float32(55026, unit="°C")
    lower_temperature = float32(55028, unit="°C")

    def __init__(self, unit, *, sensor_count: int) -> None:
        super().__init__(unit)
        # OVUM explicitly documents HPUF_PUOT as available only with two probes.
        if sensor_count == 1:
            self.restrict_fields(("effective_target_temperature", "lower_temperature"))

    @property
    def primary_temperature(self) -> float | None:
        # HPUF_PUUT is the regular/always-present buffer probe in the supplied map.
        return self.lower_temperature


class HeatingBufferSettings(Component):
    pv_target_temperature = integer(55021, writable=range_validator(0, 70), unit="°C")

    async def async_set_pv_target_temperature(self, temperature: int) -> bool:
        return await write_if_changed(self, "pv_target_temperature", int(temperature))


class HeatingCircuitReadings(Component):
    # Protocol marks these process values RW, but the XLS describes them as
    # "current setpoint" and sensor actual value. We intentionally expose them
    # read-only until OVUM documents a safe external-write use case.
    effective_target_temperature = float32(56053, unit="°C")
    actual_value = float32(56055, unit="°C")


class HeatingCircuitSettings(Component):
    pv_raise = integer(56051, writable=range_validator(0, 25), unit="K")
    pv_reduce = integer(56052, writable=range_validator(-25, 0), unit="K")
    mode = enum(56057, HeatingCircuitMode, writable=True)
    room_target_heating = float32(
        56058,
        writable=range_validator(0, 50, step=0.5),
        unit="°C",
    )

    async def async_set_mode(self, mode: HeatingCircuitMode) -> bool:
        return await write_if_changed(self, "mode", mode)

    async def async_set_room_target_heating(self, temperature: float) -> bool:
        return await write_if_changed(
            self,
            "room_target_heating",
            temperature,
            normalize=lambda v: snap_step(float(v), low=0, step=0.5),
            abs_tol=0.01,
        )

    async def async_set_pv_raise(self, delta_k: int) -> bool:
        return await write_if_changed(self, "pv_raise", int(delta_k))

    async def async_set_pv_reduce(self, delta_k: int) -> bool:
        return await write_if_changed(self, "pv_reduce", int(delta_k))


class HeatingCircuit1RoomReadings(Component):
    actual_room_temperature = float32(56152, unit="°C")


class EmsProcessValues(Component):
    """Externally supplied EMS process values.

    These are intentionally non-P_* process registers and may be updated cyclically.
    They only have an effect when the corresponding MIRA source parameters are set
    to EMS. Those source parameters are not present in the supplied register sheet.
    """

    pv_status = enum(55070, PvStatus, writable=True)
    battery_soc = integer(55071, writable=range_validator(0, 100), unit="%")
    grid_power = int32(55072, writable=True, unit="W")
    inverter_power = int32(55074, writable=True, unit="W")
    requested_power = int32(55076, writable=True, unit="W")


@dataclass(slots=True)
class HotWater:
    readings: HotWaterReadings
    settings: HotWaterSettings


@dataclass(slots=True)
class HeatingBuffer:
    readings: HeatingBufferReadings
    settings: HeatingBufferSettings


@dataclass(slots=True)
class HeatingCircuit:
    number: int
    circuit_type: HeatingCircuitType
    readings: HeatingCircuitReadings
    settings: HeatingCircuitSettings
    room_readings: HeatingCircuit1RoomReadings | None = None


class OvumHsm:
    """Typed model of OVUM's HSM unit (normally Modbus unit 110)."""

    def __init__(self, unit, *, options: InstallationOptions | None = None) -> None:
        self._unit = unit
        self.options = options or InstallationOptions()
        self.capabilities = HsmCapabilities(unit)
        self.common = HsmCommonReadings(unit)
        self.hot_water: HotWater | None = None
        self.heating_buffer: HeatingBuffer | None = None
        self.heating_circuit_1: HeatingCircuit | None = None
        self.heating_circuit_2: HeatingCircuit | None = None
        self.ems: EmsProcessValues | None = None
        self._reading_group: ComponentGroup | None = None
        self._settings_group: ComponentGroup | None = None
        self._setup_complete = False

    async def async_setup(self) -> None:
        if self._setup_complete:
            return
        await self.capabilities.async_update(notify=False)

        if self.capabilities.hot_water_installed == SwitchState.ON:
            self.hot_water = HotWater(
                readings=HotWaterReadings(
                    self._unit, sensor_count=self.options.hot_water_sensor_count
                ),
                settings=HotWaterSettings(self._unit),
            )

        if self.capabilities.heating_buffer_type not in (None, BufferSystemType.NONE):
            self.heating_buffer = HeatingBuffer(
                readings=HeatingBufferReadings(
                    self._unit,
                    sensor_count=self.options.heating_buffer_sensor_count,
                ),
                settings=HeatingBufferSettings(self._unit),
            )

        self.heating_circuit_1 = self._make_circuit(
            1,
            self.capabilities.heating_circuit_1_type,
            room_sensor=self.options.heating_circuit_1_room_sensor,
        )
        self.heating_circuit_2 = self._make_circuit(
            2,
            self.capabilities.heating_circuit_2_type,
            room_sensor=False,
        )

        if self.options.enable_ems_writes:
            self.ems = EmsProcessValues(self._unit)

        readings = [self.common]
        settings = []
        for subsystem in (self.hot_water, self.heating_buffer):
            if subsystem is not None:
                readings.append(subsystem.readings)
                settings.append(subsystem.settings)
        for circuit in (self.heating_circuit_1, self.heating_circuit_2):
            if circuit is not None:
                readings.append(circuit.readings)
                settings.append(circuit.settings)
                if circuit.room_readings is not None:
                    readings.append(circuit.room_readings)
        if self.ems is not None:
            # EMS values are process values; include in readings only when explicitly enabled.
            readings.append(self.ems)

        self._reading_group = ComponentGroup(self._unit, readings)
        self._settings_group = ComponentGroup(self._unit, settings) if settings else None
        self._setup_complete = True

    def _make_circuit(
        self,
        number: int,
        circuit_type: HeatingCircuitType | None,
        *,
        room_sensor: bool,
    ) -> HeatingCircuit | None:
        if circuit_type in (None, HeatingCircuitType.NONE):
            return None
        offset = (number - 1) * 10
        room = HeatingCircuit1RoomReadings(self._unit) if number == 1 and room_sensor else None
        return HeatingCircuit(
            number=number,
            circuit_type=circuit_type,
            readings=HeatingCircuitReadings(self._unit, base_offset=offset),
            settings=HeatingCircuitSettings(self._unit, base_offset=offset),
            room_readings=room,
        )

    async def async_update_readings(self) -> None:
        if not self._setup_complete:
            await self.async_setup()
        assert self._reading_group is not None
        await self._reading_group.async_update()

    async def async_update_settings(self) -> None:
        if not self._setup_complete:
            await self.async_setup()
        if self._settings_group is not None:
            await self._settings_group.async_update()

    async def async_update(self) -> None:
        await self.async_update_readings()
        await self.async_update_settings()
