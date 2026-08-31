from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from homeassistant.components.climate import HVACMode

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
    return SimpleNamespace(
        system=SimpleNamespace(
            hsm=SimpleNamespace(heating_circuit_1=circuit)
        ),
        last_update_success=True,
        async_request_refresh=AsyncMock(),
    )


def test_climate_exposes_room_and_target_temperature():
    coordinator = _coordinator()
    entity = HeatingCircuitClimate(coordinator, "entry-id")

    assert entity.current_temperature == 21.25
    assert entity.target_temperature == 22.0
    assert entity.hvac_mode == HVACMode.HEAT
    assert entity.hvac_modes == [HVACMode.HEAT]
    assert entity.unique_id == "entry-id_hk1_climate"
    assert entity.suggested_object_id == "ovum_heating_circuit_1_room"


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

    assert entity.current_temperature is None


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
