import struct
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from modbus_connection.model import FloatField, NumberField, StringField

from custom_components.ovum_mira.ovum_mira_modbus.enums import (
    HeatingCircuitTargetMode,
)
from custom_components.ovum_mira.ovum_mira_modbus.fields import ovum_boolean
from custom_components.ovum_mira.ovum_mira_modbus.hsm import (
    HeatingCircuit1RoomReadings,
    HeatingCircuitReadings,
    HeatingCircuitSettings,
    HotWaterReadings,
)
from custom_components.ovum_mira.ovum_mira_modbus.plus import (
    PlusCascadeReadings,
    PlusCoolingBufferCapabilities,
    PlusCoolingBufferReadings,
    PlusHeatingCircuitCapabilities,
    PlusHeatingCircuitExtendedSettings,
    PlusHeatingCircuitRoomReadings,
    PlusHeatingBufferReadings,
    PlusHotWaterReadings,
    PlusHotWaterSettings,
    PlusIdentity,
    PlusPvReleaseReadings,
)


PLUS_FIXED_COMPONENT_TYPES = (
    PlusIdentity,
    PlusHotWaterReadings,
    PlusHotWaterSettings,
    PlusHeatingBufferReadings,
    PlusCoolingBufferCapabilities,
    PlusCoolingBufferReadings,
    PlusCascadeReadings,
    PlusPvReleaseReadings,
)


OFFICIAL_PLUS_ADDRESSES = {
    55004,
    55012,
    55014,
    55015,
    55016,
    55017,
    55019,
    55022,
    55030,
    55040,
    55041,
    55043,
    55045,
    55058,
    55059,
    55060,
    55079,
    55081,
    55083,
    55085,
    56010,
    56053,
    56055,
    56063,
    56065,
    56070,
    56071,
    56072,
    56073,
    56075,
    56077,
    56078,
    56080,
    56081,
    56082,
    56083,
    56085,
    56087,
    56088,
    56150,
    56152,
    56154,
    56155,
    56156,
    56157,
    56158,
    56159,
    56160,
    56175,
    56177,
    56179,
    56180,
    56181,
    56182,
    56183,
    56184,
    56185,
    56200,
    56202,
    56204,
    56205,
    56206,
    56207,
    56208,
    56209,
    56210,
    56225,
    56227,
    56229,
    56230,
    56231,
    56232,
    56233,
    56234,
    56235,
}


def _addresses(component) -> set[int]:
    return {field.address for field in component.resolved_fields.values()}


def test_complete_official_plus_address_coverage():
    unit = object()
    addresses: set[int] = set()

    for component_type in PLUS_FIXED_COMPONENT_TYPES:
        addresses |= _addresses(component_type(unit))

    # Six Plus-table rows are Start values and remain defined in the Start model.
    hot_water = HotWaterReadings(unit, sensor_count=2)
    addresses.add(
        hot_water.resolved_fields["effective_target_temperature"].address
    )
    addresses |= _addresses(HeatingCircuit1RoomReadings(unit))

    for number in range(1, 5):
        addresses |= _addresses(
            HeatingCircuitReadings(unit, base_offset=(number - 1) * 10)
        )
        if number >= 3:
            addresses |= _addresses(
                PlusHeatingCircuitCapabilities(unit, base_offset=(number - 3) * 10)
            )
            addresses |= _addresses(
                HeatingCircuitSettings(unit, base_offset=(number - 1) * 10)
            )
        addresses |= _addresses(PlusHeatingCircuitRoomReadings(unit, index=number))
        addresses |= _addresses(
            PlusHeatingCircuitExtendedSettings(unit, index=number)
        )

    assert addresses == OFFICIAL_PLUS_ADDRESSES
    assert len(addresses) == 75


def test_plus_field_widths_follow_documented_data_types():
    unit = object()
    fields = {
        resolved.address: resolved.field
        for component_type in PLUS_FIXED_COMPONENT_TYPES
        for resolved in component_type(unit).resolved_fields.values()
    }

    assert isinstance(fields[56010], StringField)
    assert fields[56010].count == 10
    assert isinstance(fields[55017], FloatField)
    assert fields[55017].count == 2
    # The sheet says #Register=2 here, but s16 is explicitly one register.
    for address in (55079, 55081, 55083, 55085):
        assert isinstance(fields[address], NumberField)
        assert fields[address].count == 1


def test_all_41_new_plus_writes_are_declared_and_validated():
    unit = object()
    writable_fields = list(PlusHotWaterSettings(unit).resolved_fields.values())
    for number in (3, 4):
        writable_fields.extend(
            HeatingCircuitSettings(
                unit,
                base_offset=(number - 1) * 10,
            ).resolved_fields.values()
        )
    for number in range(1, 5):
        writable_fields.extend(
            PlusHeatingCircuitExtendedSettings(
                unit,
                index=number,
            ).resolved_fields.values()
        )

    assert len(writable_fields) == 41
    assert all(field.field.writable for field in writable_fields)
    for resolved in writable_fields:
        field = resolved.field
        if field.writable is True:
            assert isinstance(field, NumberField)
            assert field.convert is not None
        else:
            assert callable(field.writable)


def test_ovum_boolean_accepts_every_nonzero_value_as_true():
    field = ovum_boolean(10)

    assert field.decode([0]) is False
    assert field.decode([1]) is True
    assert field.decode([0xFFFF]) is True


async def test_plus_hot_water_parameter_uses_safe_write():
    component = PlusHotWaterSettings(object())

    with patch(
        "custom_components.ovum_mira.ovum_mira_modbus.plus.write_if_changed",
        new=AsyncMock(return_value=True),
    ) as write:
        changed = await component.async_set_fresh_water_target_temperature(48)

    assert changed is True
    write.assert_awaited_once_with(
        component,
        "fresh_water_target_temperature",
        48,
    )


async def test_extended_heating_circuit_parameters_use_safe_write():
    component = PlusHeatingCircuitExtendedSettings(object(), index=4)

    with patch(
        "custom_components.ovum_mira.ovum_mira_modbus.plus.write_if_changed",
        new=AsyncMock(return_value=True),
    ) as write:
        await component.async_set_cooling_room_target(20.26)
        await component.async_set_follows_vacation(True)
        await component.async_set_vacation_heating_target(16)
        await component.async_set_vacation_cooling_target(30)
        await component.async_set_target_mode(HeatingCircuitTargetMode.FIXED_HEATING)
        await component.async_set_fixed_heating_target(40)
        await component.async_set_fixed_cooling_target(18)
        await component.async_set_heating_limit(14.74)

    assert write.await_count == 8
    (
        cooling_call,
        vacation_call,
        vacation_heating_call,
        vacation_cooling_call,
        mode_call,
        fixed_heating_call,
        fixed_cooling_call,
        limit_call,
    ) = write.await_args_list
    assert cooling_call.args[:3] == (component, "cooling_room_target", 20.26)
    assert cooling_call.kwargs["normalize"](20.26) == 20.5
    assert vacation_call.args[1:] == ("follows_vacation", 1)
    assert vacation_heating_call.args[1:] == ("vacation_heating_target", 16)
    assert vacation_cooling_call.args[1:] == ("vacation_cooling_target", 30)
    assert mode_call.args[1:] == (
        "target_mode",
        HeatingCircuitTargetMode.FIXED_HEATING,
    )
    assert fixed_heating_call.args[1:] == ("fixed_heating_target", 40)
    assert fixed_cooling_call.args[1:] == ("fixed_cooling_target", 18)
    assert limit_call.args[:3] == (component, "heating_limit", 14.74)
    assert limit_call.kwargs["normalize"](14.74) == 14.5


async def test_plus_p_float_write_uses_one_fc16_transaction():
    unit = SimpleNamespace(write_registers=AsyncMock(), write_register=AsyncMock())
    component = PlusHeatingCircuitExtendedSettings(unit, index=4)

    await component.write("heating_limit", 14.5)

    expected = list(struct.unpack(">HH", struct.pack(">f", 14.5)))
    unit.write_registers.assert_awaited_once_with(56235, expected)
    unit.write_register.assert_not_awaited()


def test_extended_heating_circuit_stride_reaches_circuit_four():
    component = PlusHeatingCircuitExtendedSettings(object(), index=4)
    fields = component.resolved_fields

    assert fields["cooling_room_target"].address == 56225
    assert fields["follows_vacation"].address == 56229
    assert fields["heating_limit"].address == 56235
