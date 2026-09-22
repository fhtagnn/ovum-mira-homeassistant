from enum import IntEnum


class SwitchState(IntEnum):
    OFF = 0
    ON = 1


class BufferSystemType(IntEnum):
    NONE = 0
    BUFFER = 1
    CUBE_STORAGE = 2


class HeatingCircuitMode(IntEnum):
    # OVUM semantics: OFF still keeps frost protection active.
    OFF_FROST_PROTECTION = 0
    AUTOMATIC = 1
    WINTER_HEATING_ONLY = 2
    SUMMER_COOLING_ONLY = 3


class HeatingCircuitType(IntEnum):
    NONE = 0
    UNCONTROLLED = 1
    RETURN_CONTROLLED = 2
    MIXED = 3
    CUBE_DIRECT = 4


class PvStatus(IntEnum):
    NEUTRAL = 0
    RAISE = 1
    REDUCE = 2


class DhwRequestStatus(IntEnum):
    NONE = 0
    PLUS = 1
    PHOTOVOLTAIC = 2
    LEGIONELLA = 3
    NOMINAL = 4
    TURBO = 5
    FROST_PROTECTION = 6


class FreshWaterDrawStatus(IntEnum):
    NO_DRAW = 0
    STANDBY_FLOW = 1
    DRAW = 2


class BufferLoadingStatus(IntEnum):
    BELOW_FROST_PROTECTION = 0
    BELOW_SWITCH_ON = 1
    BELOW_TARGET = 2
    ABOVE_TARGET = 3
    ABOVE_SWITCH_OFF = 4
    NOT_CONFIGURED = 5


class CoolingBufferLoadingStatus(IntEnum):
    ABOVE_SWITCH_OFF = 0
    RESERVED = 1
    BELOW_TARGET_PLUS_HYSTERESIS = 2
    BELOW_TARGET = 3
    BELOW_TARGET_MINUS_HYSTERESIS = 4
    NOT_CONFIGURED = 5


class HeatingCircuitTargetMode(IntEnum):
    AUTOMATIC = 0
    FIXED_HEATING = 1
    FIXED_COOLING = 2


class WpmStatus(IntEnum):
    FAULT = 0
    INVERTER_OFFLINE = 1
    LOCKOUT = 3
    OIL_PREHEATING = 4
    READY = 5
    START = 6
    HOT_WATER = 7
    HEATING = 8
    COOLING = 9
    DEFROST = 10
    MANUAL_DEFROST = 11
    STOPPING = 12
    BELOW_OPERATING_LIMIT = 13
    INVERTER_RESET = 14
