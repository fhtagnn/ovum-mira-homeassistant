from datetime import UTC, datetime
from types import SimpleNamespace

from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.helpers.entity import EntityCategory

from custom_components.ovum_mira.binary_sensor import async_setup_entry
from custom_components.ovum_mira.ovum_mira_modbus import WpmStatus


def _entry(status: WpmStatus | None):
    wpm = SimpleNamespace(
        _unit=SimpleNamespace(unit_id=111),
        identity=SimpleNamespace(system_name="WPM 1"),
        readings=SimpleNamespace(status=status),
    )
    coordinator = SimpleNamespace(
        system=SimpleNamespace(wpms=[wpm]),
        last_update_success=True,
        modbus_available=True,
        last_successful_modbus_update=datetime(2026, 9, 30, 20, 0, tzinfo=UTC),
    )
    return SimpleNamespace(
        entry_id="entry-id",
        runtime_data=SimpleNamespace(coordinator=coordinator),
    )


async def _entities(status: WpmStatus | None):
    entities = []
    await async_setup_entry(None, _entry(status), entities.extend)
    return entities


def _by_unique_id(entities, unique_id):
    return next(entity for entity in entities if entity.unique_id == unique_id)


async def test_binary_sensor_platform_exposes_blueprint_semantics():
    entities = await _entities(WpmStatus.HEATING)

    communication = _by_unique_id(entities, "entry-id_modbus_communication")
    assert communication.is_on is True
    assert communication.available is True
    assert communication.device_class is BinarySensorDeviceClass.CONNECTIVITY
    assert communication.entity_category is EntityCategory.DIAGNOSTIC
    assert communication.extra_state_attributes == {
        "last_successful_update": "2026-09-30T20:00:00+00:00"
    }

    problem = _by_unique_id(entities, "entry-id_wpm_111_problem")
    assert problem.is_on is False
    assert problem.device_class is BinarySensorDeviceClass.PROBLEM
    assert problem.entity_category is EntityCategory.DIAGNOSTIC

    running = _by_unique_id(entities, "entry-id_wpm_111_running")
    assert running.is_on is True
    assert running.device_class is BinarySensorDeviceClass.RUNNING
    assert running.entity_category is None
    assert running.extra_state_attributes == {
        "unit_id": 111,
        "wpm_status": "heating",
    }


async def test_problem_sensor_only_marks_explicit_fault_states():
    for status in (WpmStatus.FAULT, WpmStatus.INVERTER_OFFLINE):
        entities = await _entities(status)
        problem = _by_unique_id(entities, "entry-id_wpm_111_problem")
        assert problem.is_on is True
        assert problem.extra_state_attributes["wpm_status"] == status.name.lower()
        assert problem.extra_state_attributes["wpm_status_code"] == int(status)

    for status in (
        WpmStatus.LOCKOUT,
        WpmStatus.DEFROST,
        WpmStatus.BELOW_OPERATING_LIMIT,
    ):
        entities = await _entities(status)
        assert _by_unique_id(entities, "entry-id_wpm_111_problem").is_on is False


async def test_running_sensor_uses_existing_cycle_semantics():
    active = {
        WpmStatus.START,
        WpmStatus.HOT_WATER,
        WpmStatus.HEATING,
        WpmStatus.COOLING,
        WpmStatus.DEFROST,
        WpmStatus.MANUAL_DEFROST,
        WpmStatus.STOPPING,
    }
    for status in WpmStatus:
        entities = await _entities(status)
        running = _by_unique_id(entities, "entry-id_wpm_111_running")
        assert running.is_on is (status in active)


async def test_wpm_binary_sensors_are_unknown_without_a_valid_status():
    entities = await _entities(None)

    assert _by_unique_id(entities, "entry-id_wpm_111_problem").is_on is None
    assert _by_unique_id(entities, "entry-id_wpm_111_running").is_on is None


async def test_communication_sensor_stays_available_during_failed_poll():
    communication = (await _entities(WpmStatus.READY))[0]
    communication.coordinator.last_update_success = False
    communication.coordinator.modbus_available = False

    assert communication.available is True
    assert communication.is_on is False
