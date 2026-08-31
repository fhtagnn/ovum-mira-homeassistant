from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call, patch

from custom_components.ovum_mira import select as select_platform
from custom_components.ovum_mira import switch as switch_platform
from custom_components.ovum_mira import water_heater as water_heater_platform
from custom_components.ovum_mira.ovum_mira_modbus.enums import (
    HeatingCircuitMode,
    SwitchState,
)
from custom_components.ovum_mira.ovum_mira_modbus.hsm import (
    HeatingBufferReadings,
    HeatingBufferSettings,
    HeatingCircuitSettings,
    HotWaterReadings,
    HotWaterSettings,
    OvumHsm,
)
from custom_components.ovum_mira.ovum_mira_modbus.safe_write import _same_value
from custom_components.ovum_mira.ovum_mira_modbus.validators import range_validator
from custom_components.ovum_mira.water_heater import OvumHotWater


def _entry_for_hsm(hsm):
    coordinator = SimpleNamespace(
        system=SimpleNamespace(hsm=hsm),
        last_update_success=True,
        async_request_refresh=AsyncMock(),
    )
    entry = SimpleNamespace(
        entry_id="entry-id",
        runtime_data=SimpleNamespace(coordinator=coordinator),
    )
    return entry, coordinator


def test_range_validator_without_step_returns_original_value():
    validator = range_validator(0, 10)

    assert validator(5) == 5


def test_same_value_handles_missing_and_non_numeric_float_comparison():
    assert _same_value(None, 1, abs_tol=0.1) is False
    assert _same_value(1.0, object(), abs_tol=0.1) is False


def test_hsm_one_sensor_readings_restrict_fields_and_expose_primary_value():
    hot_water = HotWaterReadings(object(), sensor_count=1)
    hot_water._values["upper_temperature"] = 47.5

    assert set(hot_water.resolved_fields) == {
        "effective_target_temperature",
        "upper_temperature",
    }
    assert hot_water.primary_temperature == 47.5

    buffer = HeatingBufferReadings(object(), sensor_count=1)
    buffer._values["lower_temperature"] = 31.25

    assert set(buffer.resolved_fields) == {
        "effective_target_temperature",
        "lower_temperature",
    }
    assert buffer.primary_temperature == 31.25


async def test_hsm_setting_helpers_delegate_to_change_only_writer():
    writer = AsyncMock(return_value=True)
    hot_water = HotWaterSettings(object())
    buffer = HeatingBufferSettings(object())
    circuit = HeatingCircuitSettings(object())

    with patch(
        "custom_components.ovum_mira.ovum_mira_modbus.hsm.write_if_changed",
        new=writer,
    ):
        assert await hot_water.async_set_enabled(True) is True
        assert await hot_water.async_set_target_temperature(51) is True
        assert await hot_water.async_set_pv_target_temperature(57) is True
        assert await buffer.async_set_pv_target_temperature(55) is True
        assert await circuit.async_set_mode(HeatingCircuitMode.AUTOMATIC) is True
        assert await circuit.async_set_room_target_heating(21.5) is True
        assert await circuit.async_set_pv_raise(4) is True
        assert await circuit.async_set_pv_reduce(-3) is True

    assert writer.await_args_list[:5] == [
        call(hot_water, "enabled", SwitchState.ON),
        call(hot_water, "target_temperature", 51),
        call(hot_water, "pv_target_temperature", 57),
        call(buffer, "pv_target_temperature", 55),
        call(circuit, "mode", HeatingCircuitMode.AUTOMATIC),
    ]
    room_call = writer.await_args_list[5]
    assert room_call.args[:3] == (circuit, "room_target_heating", 21.5)
    assert callable(room_call.kwargs["normalize"])
    assert room_call.kwargs["abs_tol"] == 0.01
    assert writer.await_args_list[6] == call(circuit, "pv_raise", 4)
    assert writer.await_args_list[7] == call(circuit, "pv_reduce", -3)


async def test_hsm_update_methods_initialize_when_called_before_setup():
    hsm = OvumHsm(object())
    reading_group = SimpleNamespace(async_update=AsyncMock())
    settings_group = SimpleNamespace(async_update=AsyncMock())
    hsm._reading_group = reading_group
    hsm._settings_group = settings_group

    async def mark_setup_complete():
        hsm._setup_complete = True

    hsm.async_setup = AsyncMock(side_effect=mark_setup_complete)

    await hsm.async_update_readings()
    hsm._setup_complete = False
    await hsm.async_update_settings()

    assert hsm.async_setup.await_count == 2
    reading_group.async_update.assert_awaited_once_with()
    settings_group.async_update.assert_awaited_once_with()


async def test_select_platform_setup_adds_only_installed_circuits():
    circuit = SimpleNamespace(settings=SimpleNamespace(mode=HeatingCircuitMode.AUTOMATIC))
    entry, _coordinator = _entry_for_hsm(
        SimpleNamespace(
            heating_circuit_1=circuit,
            heating_circuit_2=None,
        )
    )
    add_entities = MagicMock()

    await select_platform.async_setup_entry(None, entry, add_entities)

    entities = add_entities.call_args.args[0]
    assert len(entities) == 1
    assert entities[0].number == 1


async def test_switch_and_water_heater_platform_setup_add_dhw_entities():
    hot_water = SimpleNamespace(
        settings=SimpleNamespace(enabled=SwitchState.ON, target_temperature=50),
        readings=SimpleNamespace(primary_temperature=47.0),
    )
    entry, _coordinator = _entry_for_hsm(SimpleNamespace(hot_water=hot_water))
    add_switches = MagicMock()
    add_water_heaters = MagicMock()

    await switch_platform.async_setup_entry(None, entry, add_switches)
    await water_heater_platform.async_setup_entry(None, entry, add_water_heaters)

    assert len(add_switches.call_args.args[0]) == 1
    assert len(add_water_heaters.call_args.args[0]) == 1


def test_water_heater_unknown_enable_state_has_unknown_operation():
    hot_water = SimpleNamespace(
        settings=SimpleNamespace(enabled=None, target_temperature=50),
        readings=SimpleNamespace(primary_temperature=47.0),
    )
    _entry, coordinator = _entry_for_hsm(SimpleNamespace(hot_water=hot_water))

    assert OvumHotWater(coordinator, "entry-id").current_operation is None
