from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from homeassistant.components.climate import ClimateEntity, HVACMode

from custom_components.ovum_mira.climate import HeatingCircuitClimate, async_setup_entry


def _coordinator(*, with_room: bool = True):
    room_readings = (
        SimpleNamespace(actual_room_temperature=21.25) if with_room else None
    )
    settings = SimpleNamespace(
        room_target_heating=22.0,
        async_set_room_target_heating=AsyncMock(),
    )
    circuit = SimpleNamespace(room_readings=room_readings, settings=settings)
    system = SimpleNamespace(
        hsm=SimpleNamespace(heating_circuit_1=circuit),
        async_ensure_login=AsyncMock(),
    )
    return SimpleNamespace(
        system=system,
        last_update_success=True,
        async_request_refresh=AsyncMock(),
    )


def test_climate_exposes_room_and_target_temperature():
    coordinator = _coordinator()
    entity = HeatingCircuitClimate(coordinator, "entry-id")

    current_property = (
        "native_current_temperature"
        if hasattr(type(entity), "native_current_temperature")
        else "current_temperature"
    )
    target_property = (
        "native_target_temperature"
        if hasattr(type(entity), "native_target_temperature")
        else "target_temperature"
    )

    assert getattr(entity, current_property) == 21.25
    assert getattr(entity, target_property) == 22.0
    assert entity.hvac_mode == HVACMode.HEAT
    assert entity.hvac_modes == [HVACMode.HEAT]
    assert entity.unique_id == "entry-id_hk1_climate"
    assert entity.suggested_object_id == "ovum_heating_circuit_1_room"


def test_climate_uses_supported_temperature_api():
    """Use native names on 2026.11 without breaking the 2026.10 baseline."""
    class_attributes = vars(HeatingCircuitClimate)

    if hasattr(ClimateEntity, "native_temperature_unit"):
        assert "_attr_native_temperature_unit" in class_attributes
        assert "native_current_temperature" in class_attributes
        assert "native_target_temperature" in class_attributes
        assert "_attr_temperature_unit" not in class_attributes
        assert "current_temperature" not in class_attributes
        assert "target_temperature" not in class_attributes
    else:
        assert "_attr_temperature_unit" in class_attributes
        assert "current_temperature" in class_attributes
        assert "target_temperature" in class_attributes
        assert "_attr_native_temperature_unit" not in class_attributes
        assert "native_current_temperature" not in class_attributes
        assert "native_target_temperature" not in class_attributes


async def test_climate_sets_target_and_refreshes():
    coordinator = _coordinator()
    entity = HeatingCircuitClimate(coordinator, "entry-id")

    await entity.async_set_temperature(temperature=22.5)

    coordinator.system.hsm.heating_circuit_1.settings.async_set_room_target_heating.assert_awaited_once_with(
        22.5
    )
    coordinator.async_request_refresh.assert_awaited_once_with()


async def test_climate_ignores_missing_temperature():
    coordinator = _coordinator()
    entity = HeatingCircuitClimate(coordinator, "entry-id")

    await entity.async_set_temperature()

    coordinator.system.hsm.heating_circuit_1.settings.async_set_room_target_heating.assert_not_awaited()
    coordinator.async_request_refresh.assert_not_awaited()


def test_climate_current_temperature_is_unknown_without_room_reading():
    coordinator = _coordinator(with_room=False)
    entity = HeatingCircuitClimate(coordinator, "entry-id")

    current_property = (
        "native_current_temperature"
        if hasattr(type(entity), "native_current_temperature")
        else "current_temperature"
    )
    assert getattr(entity, current_property) is None


async def test_climate_platform_adds_entity_only_with_room_probe(hass):
    coordinator = _coordinator(with_room=True)
    entry = SimpleNamespace(
        entry_id="entry-id",
        runtime_data=SimpleNamespace(coordinator=coordinator),
    )
    add_entities = MagicMock()

    await async_setup_entry(hass, entry, add_entities)

    add_entities.assert_called_once()
    entities = list(add_entities.call_args.args[0])
    assert len(entities) == 1
    assert isinstance(entities[0], HeatingCircuitClimate)


async def test_climate_platform_skips_missing_room_probe(hass):
    coordinator = _coordinator(with_room=False)
    entry = SimpleNamespace(
        entry_id="entry-id",
        runtime_data=SimpleNamespace(coordinator=coordinator),
    )
    add_entities = MagicMock()

    await async_setup_entry(hass, entry, add_entities)

    add_entities.assert_not_called()
