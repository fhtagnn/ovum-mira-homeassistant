from types import SimpleNamespace
from unittest.mock import AsyncMock

from homeassistant.components.water_heater import STATE_HEAT_PUMP
from homeassistant.const import STATE_OFF

from custom_components.ovum_mira.const import DOMAIN
from custom_components.ovum_mira.entity import OvumMiraEntity, OvumWpmEntity
from custom_components.ovum_mira.number import OvumTemperatureNumber
from custom_components.ovum_mira.ovum_mira_modbus import HeatingCircuitMode, SwitchState
from custom_components.ovum_mira.select import HeatingCircuitModeSelect
from custom_components.ovum_mira.switch import OvumHotWaterMainSwitch
from custom_components.ovum_mira.water_heater import OvumHotWater


def _coordinator(system, *, available=True):
    return SimpleNamespace(
        system=system,
        last_update_success=available,
        async_request_refresh=AsyncMock(),
    )


def test_base_entity_identity_device_info_and_availability():
    coordinator = _coordinator(SimpleNamespace(wpms=[]))
    entity = OvumMiraEntity(coordinator, "entry-id", "outside_temperature")

    assert entity.unique_id == "entry-id_outside_temperature"
    assert entity.suggested_object_id == "ovum_outdoor_temperature"
    assert entity.device_info["identifiers"] == {(DOMAIN, "entry-id")}
    assert entity.device_info["manufacturer"] == "OVUM"
    assert entity.device_info["model"] == "MIRA"
    assert entity.available is True

    coordinator.last_update_success = False
    assert entity.available is False


def test_wpm_entity_uses_child_device_and_controller_name():
    wpm = SimpleNamespace(
        _unit=SimpleNamespace(unit_id=111),
        identity=SimpleNamespace(system_name="AC312P"),
    )
    coordinator = _coordinator(SimpleNamespace(wpms=[wpm]))
    entity = OvumWpmEntity(coordinator, "entry-id", 111, "electrical_power")

    assert entity.unique_id == "entry-id_wpm_111_electrical_power"
    assert entity.suggested_object_id == "ovum_wpm_1_electrical_power"
    assert entity.device_info["identifiers"] == {(DOMAIN, "entry-id_wpm_111")}
    assert entity.device_info["via_device"] == (DOMAIN, "entry-id")
    assert entity.device_info["name"] == "AC312P"
    assert entity.device_info["model"] == "MIRA WPM"


async def test_hot_water_switch_reads_writes_and_refreshes():
    settings = SimpleNamespace(
        enabled=SwitchState.ON,
        async_set_enabled=AsyncMock(),
    )
    hot_water = SimpleNamespace(settings=settings)
    coordinator = _coordinator(SimpleNamespace(hsm=SimpleNamespace(hot_water=hot_water)))
    entity = OvumHotWaterMainSwitch(coordinator, "entry-id")

    assert entity.is_on is True

    await entity.async_turn_off()
    settings.async_set_enabled.assert_awaited_once_with(False)
    coordinator.async_request_refresh.assert_awaited_once_with()

    settings.async_set_enabled.reset_mock()
    coordinator.async_request_refresh.reset_mock()
    settings.enabled = SwitchState.OFF
    assert entity.is_on is False

    await entity.async_turn_on()
    settings.async_set_enabled.assert_awaited_once_with(True)
    coordinator.async_request_refresh.assert_awaited_once_with()


def test_hot_water_switch_unknown_state_is_unknown():
    hot_water = SimpleNamespace(settings=SimpleNamespace(enabled=None))
    coordinator = _coordinator(SimpleNamespace(hsm=SimpleNamespace(hot_water=hot_water)))
    assert OvumHotWaterMainSwitch(coordinator, "entry-id").is_on is None


async def test_heating_circuit_select_maps_mode_and_refreshes():
    settings = SimpleNamespace(
        mode=HeatingCircuitMode.AUTOMATIC,
        async_set_mode=AsyncMock(),
    )
    circuit = SimpleNamespace(settings=settings)
    coordinator = _coordinator(SimpleNamespace(hsm=SimpleNamespace(heating_circuit_1=circuit)))
    entity = HeatingCircuitModeSelect(coordinator, "entry-id", 1)

    assert entity.current_option == "automatic"
    assert entity.options == [
        "off_frost_protection",
        "automatic",
        "winter_heating_only",
        "summer_cooling_only",
    ]

    await entity.async_select_option("winter_heating_only")
    settings.async_set_mode.assert_awaited_once_with(HeatingCircuitMode.WINTER_HEATING_ONLY)
    coordinator.async_request_refresh.assert_awaited_once_with()


async def test_temperature_number_exposes_limits_and_writes_value():
    system = SimpleNamespace(value=21.5)
    setter = AsyncMock()
    coordinator = _coordinator(system)
    entity = OvumTemperatureNumber(
        coordinator,
        "entry-id",
        "test_temperature",
        "test_temperature",
        lambda s: s.value,
        setter,
        10,
        30,
        0.5,
    )

    assert entity.native_value == 21.5
    assert entity.native_min_value == 10
    assert entity.native_max_value == 30
    assert entity.native_step == 0.5

    await entity.async_set_native_value(22.5)
    setter.assert_awaited_once_with(system, 22.5)
    coordinator.async_request_refresh.assert_awaited_once_with()


async def test_water_heater_exposes_state_and_controls():
    settings = SimpleNamespace(
        enabled=SwitchState.ON,
        target_temperature=50,
        async_set_target_temperature=AsyncMock(),
        async_set_enabled=AsyncMock(),
    )
    hot_water = SimpleNamespace(
        settings=settings,
        readings=SimpleNamespace(primary_temperature=47.5),
    )
    coordinator = _coordinator(SimpleNamespace(hsm=SimpleNamespace(hot_water=hot_water)))
    entity = OvumHotWater(coordinator, "entry-id")

    assert entity.current_temperature == 47.5
    assert entity.target_temperature == 50
    assert entity.current_operation == STATE_HEAT_PUMP

    await entity.async_set_temperature(temperature=50.6)
    settings.async_set_target_temperature.assert_awaited_once_with(51)
    coordinator.async_request_refresh.assert_awaited_once_with()

    settings.enabled = SwitchState.OFF
    assert entity.current_operation == STATE_OFF

    settings.async_set_enabled.reset_mock()
    coordinator.async_request_refresh.reset_mock()
    await entity.async_turn_on()
    settings.async_set_enabled.assert_awaited_once_with(True)
    coordinator.async_request_refresh.assert_awaited_once_with()

    settings.async_set_enabled.reset_mock()
    coordinator.async_request_refresh.reset_mock()
    await entity.async_turn_off()
    settings.async_set_enabled.assert_awaited_once_with(False)
    coordinator.async_request_refresh.assert_awaited_once_with()


async def test_water_heater_ignores_missing_temperature():
    settings = SimpleNamespace(
        enabled=SwitchState.ON,
        target_temperature=50,
        async_set_target_temperature=AsyncMock(),
    )
    hot_water = SimpleNamespace(
        settings=settings,
        readings=SimpleNamespace(primary_temperature=47.5),
    )
    coordinator = _coordinator(SimpleNamespace(hsm=SimpleNamespace(hot_water=hot_water)))
    entity = OvumHotWater(coordinator, "entry-id")

    await entity.async_set_temperature()

    settings.async_set_target_temperature.assert_not_awaited()
    coordinator.async_request_refresh.assert_not_awaited()
