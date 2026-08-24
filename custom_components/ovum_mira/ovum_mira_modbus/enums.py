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
