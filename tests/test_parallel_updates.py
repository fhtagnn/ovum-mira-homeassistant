from custom_components.ovum_mira import (
    binary_sensor,
    climate,
    number,
    select,
    sensor,
    switch,
    water_heater,
)


def test_platform_parallel_updates_are_explicit():
    """Every entity platform explicitly declares its request parallelism."""
    assert binary_sensor.PARALLEL_UPDATES == 0
    assert sensor.PARALLEL_UPDATES == 0
    assert climate.PARALLEL_UPDATES == 1
    assert number.PARALLEL_UPDATES == 1
    assert select.PARALLEL_UPDATES == 1
    assert switch.PARALLEL_UPDATES == 1
    assert water_heater.PARALLEL_UPDATES == 1
