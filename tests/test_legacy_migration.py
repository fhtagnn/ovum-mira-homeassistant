from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from homeassistant.components.recorder.db_schema import (
    Base,
    States,
    StatesMeta,
    Statistics,
    StatisticsMeta,
    StatisticsShortTerm,
)
from homeassistant.components.recorder.models import StatisticMeanType
from homeassistant.const import ATTR_UNIT_OF_MEASUREMENT, UnitOfEnergy

from custom_components.ovum_mira.legacy_migration import (
    LEGACY_ENTITY_MAPPINGS,
    LegacyEntityMapping,
    LegacyMigrationManager,
    _energy_state_kwh,
    _migrate_recorder_metadata_with_session,
)


def _recorder_instance():
    return SimpleNamespace(
        states_manager=SimpleNamespace(
            reset=MagicMock(),
            load_from_db=MagicMock(),
        ),
        states_meta_manager=SimpleNamespace(reset=MagicMock()),
        statistics_meta_manager=SimpleNamespace(reset=MagicMock()),
    )


def _statistics_meta(statistic_id: str) -> StatisticsMeta:
    return StatisticsMeta(
        statistic_id=statistic_id,
        source="recorder",
        unit_of_measurement="kWh",
        unit_class="energy",
        has_mean=False,
        has_sum=True,
        name=None,
        mean_type=StatisticMeanType.NONE,
    )


def test_recorder_migration_merges_states_and_preserves_continuous_statistics():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    mapping = LegacyEntityMapping(
        "sensor.ovum_verbrauch_energy",
        "sensor.ovum_wpm_1_electrical_energy_total",
        "powercalc",
    )
    instance = _recorder_instance()

    with Session(engine) as session:
        source_states = StatesMeta(entity_id=mapping.source)
        target_states = StatesMeta(entity_id=mapping.target)
        source_statistics = _statistics_meta(mapping.source)
        target_statistics = _statistics_meta(mapping.target)
        session.add_all(
            [
                source_states,
                target_states,
                source_statistics,
                target_statistics,
            ]
        )
        session.flush()
        source_states_id = source_states.metadata_id
        target_states_id = target_states.metadata_id
        source_statistics_id = source_statistics.id
        target_statistics_id = target_statistics.id
        session.add_all(
            [
                States(
                    metadata_id=source_states_id,
                    state="10",
                    last_updated_ts=1.0,
                ),
                States(
                    metadata_id=target_states_id,
                    state="11",
                    last_updated_ts=2.0,
                ),
                Statistics(
                    metadata_id=source_statistics_id,
                    start_ts=3600.0,
                    state=10.0,
                    sum=10.0,
                ),
                Statistics(
                    metadata_id=target_statistics_id,
                    start_ts=7200.0,
                    state=11.0,
                    sum=0.5,
                ),
                StatisticsShortTerm(
                    metadata_id=source_statistics_id,
                    start_ts=300.0,
                    state=10.0,
                    sum=10.0,
                ),
                StatisticsShortTerm(
                    metadata_id=target_statistics_id,
                    start_ts=600.0,
                    state=11.0,
                    sum=0.5,
                ),
            ]
        )
        session.flush()

        result = _migrate_recorder_metadata_with_session(
            instance,
            session,
            (mapping,),
            "01M0FJ8695BX1DENYZ3F74Q3PE",
            "20260831223000",
        )

        target_state_meta = session.scalar(
            select(StatesMeta).where(StatesMeta.entity_id == mapping.target)
        )
        assert target_state_meta.metadata_id == source_states_id
        assert session.scalar(
            select(StatesMeta).where(StatesMeta.entity_id == mapping.source)
        ) is None
        assert {
            row.metadata_id
            for row in session.scalars(select(States)).all()
        } == {source_states_id}

        canonical_statistics = session.scalar(
            select(StatisticsMeta).where(
                StatisticsMeta.statistic_id == mapping.target
            )
        )
        assert canonical_statistics.id == source_statistics_id
        archive_id = result["items"][0]["archive_statistic_id"]
        assert archive_id.startswith("sensor.ovum_archive_")
        archived_statistics = session.scalar(
            select(StatisticsMeta).where(
                StatisticsMeta.statistic_id == archive_id
            )
        )
        assert archived_statistics.id == target_statistics_id
        assert session.scalar(
            select(StatisticsMeta).where(
                StatisticsMeta.statistic_id == mapping.source
            )
        ) is None

    instance.states_manager.reset.assert_called_once_with()
    instance.states_manager.load_from_db.assert_called_once()
    instance.states_meta_manager.reset.assert_called_once_with()
    instance.statistics_meta_manager.reset.assert_called_once_with()


def test_legacy_mapping_contract_covers_modbus_and_powercalc_entities():
    assert sum(item.platform == "modbus" for item in LEGACY_ENTITY_MAPPINGS) == 14
    assert sum(item.platform == "powercalc" for item in LEGACY_ENTITY_MAPPINGS) == 2
    assert {
        item.target for item in LEGACY_ENTITY_MAPPINGS
    } >= {
        "sensor.ovum_hot_water_temperature",
        "sensor.ovum_heating_buffer_temperature",
        "sensor.ovum_wpm_1_electrical_energy_total",
        "sensor.ovum_wpm_1_thermal_energy_total",
    }


def test_energy_state_is_converted_to_kwh(hass):
    hass.states.async_set(
        "sensor.ovum_verbrauch_energy",
        "11646.3",
        {ATTR_UNIT_OF_MEASUREMENT: UnitOfEnergy.WATT_HOUR},
    )

    assert _energy_state_kwh(
        hass,
        "sensor.ovum_verbrauch_energy",
    ) == 11.6463


async def test_manager_waits_until_legacy_entities_are_removed(hass):
    coordinator = SimpleNamespace(
        async_import_legacy_energy_totals=AsyncMock(return_value={"ok": True})
    )
    manager = LegacyMigrationManager(hass, "entry-id", coordinator)
    manager._store.async_load = AsyncMock(return_value=None)
    manager._store.async_save = AsyncMock()
    await manager.async_initialize(True)
    hass.states.async_set(
        "sensor.ovum_verbrauch_energy",
        "11.6463",
        {ATTR_UNIT_OF_MEASUREMENT: UnitOfEnergy.KILO_WATT_HOUR},
    )

    await manager._async_attempt_migration()

    assert manager.state["status"] == "waiting_for_legacy_removal"
    assert manager.state["active_sources"] == [
        "sensor.ovum_verbrauch_energy"
    ]
    coordinator.async_import_legacy_energy_totals.assert_awaited_once_with(
        electrical_kwh=11.6463,
        thermal_kwh=None,
    )
