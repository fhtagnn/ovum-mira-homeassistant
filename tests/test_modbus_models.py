from types import SimpleNamespace
from unittest.mock import AsyncMock, call, patch

import pytest

from custom_components.ovum_mira.ovum_mira_modbus.config import InstallationOptions
from custom_components.ovum_mira.ovum_mira_modbus.device import OvumMiraSystem
from custom_components.ovum_mira.ovum_mira_modbus.enums import (
    BufferSystemType,
    HeatingCircuitType,
    SwitchState,
)
from custom_components.ovum_mira.ovum_mira_modbus.hsm import OvumHsm
from custom_components.ovum_mira.ovum_mira_modbus.login import login_and_verify
from custom_components.ovum_mira.ovum_mira_modbus.validators import (
    range_validator,
    snap_step,
)
from custom_components.ovum_mira.ovum_mira_modbus.wpm import OvumWpm


def test_installation_options_validate_sensor_counts():
    assert InstallationOptions().heating_buffer_sensor_count == 1
    assert InstallationOptions(hot_water_sensor_count=2).hot_water_sensor_count == 2

    with pytest.raises(ValueError, match="heating_buffer_sensor_count"):
        InstallationOptions(heating_buffer_sensor_count=0)
    with pytest.raises(ValueError, match="hot_water_sensor_count"):
        InstallationOptions(hot_water_sensor_count=3)


def test_range_validator_accepts_rejects_and_snaps():
    validator = range_validator(0, 50, step=0.5)

    assert validator(21.24) == 21.0
    assert validator(21.26) == 21.5
    assert validator(21) == 21

    with pytest.raises(ValueError, match="not numeric"):
        validator("21")
    with pytest.raises(ValueError, match="outside allowed range"):
        validator(50.5)


def test_snap_step_rounds_to_controller_increment():
    assert snap_step(21.24, low=0, step=0.5) == 21.0
    assert snap_step(21.26, low=0, step=0.5) == 21.5


async def test_login_and_verify_writes_fc16_component_and_accepts_status():
    login = SimpleNamespace(
        status=True,
        write=AsyncMock(),
        async_update=AsyncMock(),
    )
    unit = object()

    with patch(
        "custom_components.ovum_mira.ovum_mira_modbus.login.Login",
        return_value=login,
    ) as login_class:
        await login_and_verify(unit, 1234)

    login_class.assert_called_once_with(unit)
    login.write.assert_awaited_once_with("code", 1234)
    login.async_update.assert_awaited_once_with(notify=False)


async def test_login_and_verify_rejects_failed_status():
    login = SimpleNamespace(
        status=False,
        write=AsyncMock(),
        async_update=AsyncMock(),
    )

    with (
        patch(
            "custom_components.ovum_mira.ovum_mira_modbus.login.Login",
            return_value=login,
        ),
        pytest.raises(PermissionError, match="login rejected"),
    ):
        await login_and_verify(object(), 9999)


async def test_wpm_setup_and_update_delegate_to_components():
    identity = SimpleNamespace(async_update=AsyncMock())
    readings = SimpleNamespace(async_update=AsyncMock())
    unit = object()

    with (
        patch(
            "custom_components.ovum_mira.ovum_mira_modbus.wpm.WpmIdentity",
            return_value=identity,
        ) as identity_class,
        patch(
            "custom_components.ovum_mira.ovum_mira_modbus.wpm.WpmReadings",
            return_value=readings,
        ) as readings_class,
    ):
        wpm = OvumWpm(unit)
        await wpm.async_setup()
        await wpm.async_update()

    identity_class.assert_called_once_with(unit)
    readings_class.assert_called_once_with(unit)
    identity.async_update.assert_awaited_once_with()
    readings.async_update.assert_awaited_once_with()


async def test_system_requires_wpm_and_orchestrates_all_units():
    with pytest.raises(ValueError, match="At least WPM1"):
        OvumMiraSystem(object(), [])

    hsm = SimpleNamespace(async_setup=AsyncMock(), async_update=AsyncMock())
    wpm1 = SimpleNamespace(async_setup=AsyncMock(), async_update=AsyncMock())
    wpm2 = SimpleNamespace(async_setup=AsyncMock(), async_update=AsyncMock())
    hsm_unit = object()
    wpm_units = [object(), object()]

    with (
        patch(
            "custom_components.ovum_mira.ovum_mira_modbus.device.OvumHsm",
            return_value=hsm,
        ) as hsm_class,
        patch(
            "custom_components.ovum_mira.ovum_mira_modbus.device.OvumWpm",
            side_effect=[wpm1, wpm2],
        ) as wpm_class,
        patch(
            "custom_components.ovum_mira.ovum_mira_modbus.device.login_and_verify",
            new=AsyncMock(),
        ) as login,
    ):
        system = OvumMiraSystem(
            hsm_unit,
            wpm_units,
            options=InstallationOptions(hot_water_sensor_count=2),
        )
        await system.async_login(1234)
        await system.async_setup()
        await system.async_update()

    hsm_class.assert_called_once()
    assert hsm_class.call_args.args == (hsm_unit,)
    assert hsm_class.call_args.kwargs["options"].hot_water_sensor_count == 2
    assert wpm_class.call_args_list == [call(wpm_units[0]), call(wpm_units[1])]
    assert login.await_args_list == [
        call(hsm_unit, 1234),
        call(wpm_units[0], 1234),
        call(wpm_units[1], 1234),
    ]
    hsm.async_setup.assert_awaited_once_with()
    wpm1.async_setup.assert_awaited_once_with()
    wpm2.async_setup.assert_awaited_once_with()
    hsm.async_update.assert_awaited_once_with()
    wpm1.async_update.assert_awaited_once_with()
    wpm2.async_update.assert_awaited_once_with()


class _FakeComponent:
    def __init__(self, *, kind: str, **metadata) -> None:
        self.kind = kind
        self.metadata = metadata
        self.async_update = AsyncMock()


class _FakeGroup:
    def __init__(self, components) -> None:
        self.components = list(components)
        self.async_update = AsyncMock()


async def test_hsm_setup_builds_detected_subsystems_and_update_groups():
    capabilities = SimpleNamespace(
        hot_water_installed=SwitchState.ON,
        heating_buffer_type=BufferSystemType.BUFFER,
        heating_circuit_1_type=HeatingCircuitType.MIXED,
        heating_circuit_2_type=HeatingCircuitType.NONE,
        async_update=AsyncMock(),
    )
    common = _FakeComponent(kind="common")
    created: dict[str, list[_FakeComponent]] = {}
    groups: list[_FakeGroup] = []

    def factory(kind):
        def create(_unit, **kwargs):
            component = _FakeComponent(kind=kind, **kwargs)
            created.setdefault(kind, []).append(component)
            return component

        return create

    def create_group(_unit, components):
        group = _FakeGroup(components)
        groups.append(group)
        return group

    options = InstallationOptions(
        heating_buffer_sensor_count=2,
        hot_water_sensor_count=2,
        heating_circuit_1_room_sensor=True,
        enable_ems_writes=True,
    )

    with patch.multiple(
        "custom_components.ovum_mira.ovum_mira_modbus.hsm",
        HsmCapabilities=lambda _unit: capabilities,
        HsmCommonReadings=lambda _unit: common,
        HotWaterReadings=factory("hot_water_readings"),
        HotWaterSettings=factory("hot_water_settings"),
        HeatingBufferReadings=factory("buffer_readings"),
        HeatingBufferSettings=factory("buffer_settings"),
        HeatingCircuitReadings=factory("circuit_readings"),
        HeatingCircuitSettings=factory("circuit_settings"),
        HeatingCircuit1RoomReadings=factory("room_readings"),
        EmsProcessValues=factory("ems"),
        ComponentGroup=create_group,
    ):
        hsm = OvumHsm(object(), options=options)
        await hsm.async_setup()
        await hsm.async_setup()
        await hsm.async_update()

    capabilities.async_update.assert_awaited_once_with(notify=False)
    assert hsm.hot_water is not None
    assert hsm.heating_buffer is not None
    assert hsm.heating_circuit_1 is not None
    assert hsm.heating_circuit_1.room_readings is not None
    assert hsm.heating_circuit_2 is None
    assert hsm.ems is not None
    assert created["hot_water_readings"][0].metadata == {"sensor_count": 2}
    assert created["buffer_readings"][0].metadata == {"sensor_count": 2}
    assert created["circuit_readings"][0].metadata == {"base_offset": 0}
    assert created["circuit_settings"][0].metadata == {"base_offset": 0}
    assert len(groups) == 2
    groups[0].async_update.assert_awaited_once_with()
    groups[1].async_update.assert_awaited_once_with()


async def test_hsm_without_optional_features_has_no_settings_group():
    capabilities = SimpleNamespace(
        hot_water_installed=SwitchState.OFF,
        heating_buffer_type=BufferSystemType.NONE,
        heating_circuit_1_type=HeatingCircuitType.NONE,
        heating_circuit_2_type=HeatingCircuitType.NONE,
        async_update=AsyncMock(),
    )
    common = _FakeComponent(kind="common")
    groups: list[_FakeGroup] = []

    def create_group(_unit, components):
        group = _FakeGroup(components)
        groups.append(group)
        return group

    with patch.multiple(
        "custom_components.ovum_mira.ovum_mira_modbus.hsm",
        HsmCapabilities=lambda _unit: capabilities,
        HsmCommonReadings=lambda _unit: common,
        ComponentGroup=create_group,
    ):
        hsm = OvumHsm(object())
        await hsm.async_setup()
        await hsm.async_update_settings()
        await hsm.async_update_readings()

    assert hsm.hot_water is None
    assert hsm.heating_buffer is None
    assert hsm.heating_circuit_1 is None
    assert hsm.heating_circuit_2 is None
    assert hsm.ems is None
    assert len(groups) == 1
    groups[0].async_update.assert_awaited_once_with()
