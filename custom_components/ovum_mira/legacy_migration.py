"""One-time migration from the legacy Modbus and Powercalc entities."""

from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import logging
import math
from typing import Any, override

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.core import Recorder
from homeassistant.components.recorder.db_schema import (
    States,
    StatesMeta,
    StatisticsMeta,
)
from homeassistant.components.recorder.tasks import RecorderTask
from homeassistant.components.recorder.util import session_scope
from homeassistant.const import (
    ATTR_UNIT_OF_MEASUREMENT,
    EVENT_HOMEASSISTANT_STARTED,
    UnitOfEnergy,
)
from homeassistant.core import CoreState, Event, HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.storage import Store
from homeassistant.util.unit_conversion import EnergyConverter

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)
_STORAGE_VERSION = 1
_LEGACY_PLATFORMS = {"modbus", "powercalc"}


@dataclass(frozen=True, slots=True)
class LegacyEntityMapping:
    """Map one legacy entity ID to its OVUM MIRA replacement."""

    source: str
    target: str
    platform: str


LEGACY_ENTITY_MAPPINGS = (
    LegacyEntityMapping(
        "sensor.ovum_ww_temp_soll",
        "sensor.ovum_hot_water_effective_target_temperature",
        "modbus",
    ),
    LegacyEntityMapping(
        "sensor.ovum_ww_temp_ist",
        "sensor.ovum_hot_water_temperature",
        "modbus",
    ),
    LegacyEntityMapping(
        "sensor.ovum_puffer_soll",
        "sensor.ovum_heating_buffer_effective_target_temperature",
        "modbus",
    ),
    LegacyEntityMapping(
        "sensor.ovum_puffer_temp",
        "sensor.ovum_heating_buffer_temperature",
        "modbus",
    ),
    LegacyEntityMapping(
        "sensor.ovum_leistungsaufnahme",
        "sensor.ovum_wpm_1_electrical_power",
        "modbus",
    ),
    LegacyEntityMapping(
        "sensor.ovum_heizleistung",
        "sensor.ovum_wpm_1_thermal_power",
        "modbus",
    ),
    LegacyEntityMapping(
        "sensor.ovum_kondensat_temp_ein",
        "sensor.ovum_wpm_1_condenser_inlet_temperature",
        "modbus",
    ),
    LegacyEntityMapping(
        "sensor.ovum_kondensat_temp_aus",
        "sensor.ovum_wpm_1_condenser_outlet_temperature",
        "modbus",
    ),
    LegacyEntityMapping(
        "sensor.ovum_kompressor_betriebsstunden",
        "sensor.ovum_wpm_1_compressor_runtime",
        "modbus",
    ),
    LegacyEntityMapping(
        "sensor.ovum_aussentemp",
        "sensor.ovum_outdoor_temperature",
        "modbus",
    ),
    LegacyEntityMapping(
        "sensor.ovum_hk_sollwert",
        "sensor.ovum_heating_circuit_1_effective_target_temperature",
        "modbus",
    ),
    LegacyEntityMapping(
        "sensor.ovum_hk_fuhler",
        "sensor.ovum_heating_circuit_1_temperature",
        "modbus",
    ),
    LegacyEntityMapping(
        "sensor.ovum_hk_raumsoll",
        "number.ovum_heating_circuit_1_room_target_heating",
        "modbus",
    ),
    LegacyEntityMapping(
        "switch.ovum_warmwasser_hauptschalter",
        "switch.ovum_hot_water_main_switch",
        "modbus",
    ),
    LegacyEntityMapping(
        "sensor.ovum_verbrauch_energy",
        "sensor.ovum_wpm_1_electrical_energy_total",
        "powercalc",
    ),
    LegacyEntityMapping(
        "sensor.ovum_warmeenergie",
        "sensor.ovum_wpm_1_thermal_energy_total",
        "powercalc",
    ),
)


def _metadata(
    session: Session,
    model: type[StatesMeta] | type[StatisticsMeta],
    id_column,
    entity_id: str,
) -> StatesMeta | StatisticsMeta | None:
    return session.scalar(select(model).where(id_column == entity_id))


def _unique_archive_statistic_id(
    session: Session,
    target: str,
    entry_id: str,
    timestamp: str,
) -> str:
    """Return an unused entity-shaped statistic ID."""
    domain, object_id = target.split(".", 1)
    token = entry_id[-6:].lower()
    base = f"{domain}.ovum_archive_{token}_{timestamp}_{object_id}"
    candidate = base
    suffix = 2
    while _metadata(
        session,
        StatisticsMeta,
        StatisticsMeta.statistic_id,
        candidate,
    ) is not None:
        candidate = f"{base}_{suffix}"
        suffix += 1
    return candidate


def _migrate_mapping(
    session: Session,
    mapping: LegacyEntityMapping,
    entry_id: str,
    timestamp: str,
) -> dict[str, Any]:
    """Migrate one entity's state history and statistics metadata."""
    source_states = _metadata(
        session,
        StatesMeta,
        StatesMeta.entity_id,
        mapping.source,
    )
    target_states = _metadata(
        session,
        StatesMeta,
        StatesMeta.entity_id,
        mapping.target,
    )
    state_action = "source_missing"
    state_rows_merged = 0
    if source_states is not None and target_states is not None:
        source_metadata_id = source_states.metadata_id
        target_metadata_id = target_states.metadata_id
        result = session.execute(
            update(States)
            .where(States.metadata_id == target_metadata_id)
            .values(metadata_id=source_metadata_id)
        )
        state_rows_merged = result.rowcount or 0
        session.delete(target_states)
        session.flush()
        source_states.entity_id = mapping.target
        state_action = "merged_target_into_source"
    elif source_states is not None:
        source_states.entity_id = mapping.target
        state_action = "renamed_source"
    elif target_states is not None:
        state_action = "already_on_target"

    source_statistics = _metadata(
        session,
        StatisticsMeta,
        StatisticsMeta.statistic_id,
        mapping.source,
    )
    target_statistics = _metadata(
        session,
        StatisticsMeta,
        StatisticsMeta.statistic_id,
        mapping.target,
    )
    statistics_action = "source_missing"
    archive_statistic_id = None
    if source_statistics is not None and target_statistics is not None:
        archive_statistic_id = _unique_archive_statistic_id(
            session,
            mapping.target,
            entry_id,
            timestamp,
        )
        target_statistics.statistic_id = archive_statistic_id
        session.flush()
        source_statistics.statistic_id = mapping.target
        statistics_action = "archived_target_and_renamed_source"
    elif source_statistics is not None:
        source_statistics.statistic_id = mapping.target
        statistics_action = "renamed_source"
    elif target_statistics is not None:
        statistics_action = "already_on_target"

    return {
        **asdict(mapping),
        "state_action": state_action,
        "state_rows_merged": state_rows_merged,
        "statistics_action": statistics_action,
        "archive_statistic_id": archive_statistic_id,
    }


def _migrate_recorder_metadata_with_session(
    instance: Recorder,
    session: Session,
    mappings: tuple[LegacyEntityMapping, ...],
    entry_id: str,
    timestamp: str,
) -> dict[str, Any]:
    """Perform the complete recorder migration in one transaction."""
    items = [
        _migrate_mapping(session, mapping, entry_id, timestamp)
        for mapping in mappings
    ]
    session.flush()

    # The metadata swaps are atomic, so clear every recorder cache which may
    # still point to the pre-migration metadata IDs before processing new states.
    instance.states_manager.reset()
    instance.states_meta_manager.reset()
    instance.statistics_meta_manager.reset()
    instance.states_manager.load_from_db(session)
    return {"status": "completed", "items": items}


def _migrate_recorder_metadata(
    instance: Recorder,
    mappings: tuple[LegacyEntityMapping, ...],
    entry_id: str,
    timestamp: str,
) -> dict[str, Any]:
    with session_scope(session=instance.get_session()) as session:
        return _migrate_recorder_metadata_with_session(
            instance,
            session,
            mappings,
            entry_id,
            timestamp,
        )


@dataclass(slots=True)
class LegacyRecorderMigrationTask(RecorderTask):
    """Run the recorder migration without allowing state events to interleave."""

    mappings: tuple[LegacyEntityMapping, ...]
    entry_id: str
    timestamp: str
    on_done: Callable[[dict[str, Any]], None]

    @override
    def run(self, instance: Recorder) -> None:
        try:
            result = _migrate_recorder_metadata(
                instance,
                self.mappings,
                self.entry_id,
                self.timestamp,
            )
        except Exception as err:  # pragma: no cover - defensive recorder boundary
            _LOGGER.exception("Legacy recorder migration failed")
            result = {"status": "failed", "error": str(err), "items": []}
        instance.hass.loop.call_soon_threadsafe(self.on_done, result)


def _energy_state_kwh(hass: HomeAssistant, entity_id: str) -> float | None:
    state = hass.states.get(entity_id)
    if state is None:
        return None
    try:
        value = float(state.state)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(value) or value < 0:
        return None
    unit = state.attributes.get(
        ATTR_UNIT_OF_MEASUREMENT,
        UnitOfEnergy.KILO_WATT_HOUR,
    )
    try:
        return EnergyConverter.convert(
            value,
            unit,
            UnitOfEnergy.KILO_WATT_HOUR,
        )
    except ValueError:
        return None


class LegacyMigrationManager:
    """Coordinate energy seeding and the one-time recorder migration."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        coordinator,
    ) -> None:
        self.hass = hass
        self.entry_id = entry_id
        self.coordinator = coordinator
        self.requested = False
        self.state: dict[str, Any] = {}
        self._store: Store[dict[str, Any]] = Store(
            hass,
            _STORAGE_VERSION,
            f"{DOMAIN}.{entry_id}.legacy_migration",
        )
        self._unsub_started: Callable[[], None] | None = None

    async def async_initialize(self, requested: bool) -> None:
        """Load prior progress and record whether migration is requested."""
        self.requested = requested
        self.state = await self._store.async_load() or {}
        self.state["requested"] = requested
        if not requested:
            self.state["status"] = "not_requested"
        elif self.state.get("status") != "completed":
            self.state["status"] = "scheduled"
        await self._store.async_save(self.state)

    @callback
    def async_start(self) -> None:
        """Run after all legacy integrations had a chance to create states."""
        if not self.requested or self.state.get("status") == "completed":
            return
        if self.hass.state is CoreState.running:
            self.hass.async_create_task(
                self._async_attempt_migration(),
                f"{DOMAIN} legacy migration",
            )
            return

        @callback
        def _async_started(_event: Event) -> None:
            self._unsub_started = None
            self.hass.async_create_task(
                self._async_attempt_migration(),
                f"{DOMAIN} legacy migration",
            )

        self._unsub_started = self.hass.bus.async_listen_once(
            EVENT_HOMEASSISTANT_STARTED,
            _async_started,
        )

    @callback
    def async_stop(self) -> None:
        """Remove a pending startup listener."""
        if self._unsub_started is not None:
            self._unsub_started()
            self._unsub_started = None

    async def _async_capture_energy(self) -> None:
        electrical = _energy_state_kwh(
            self.hass,
            "sensor.ovum_verbrauch_energy",
        )
        thermal = _energy_state_kwh(
            self.hass,
            "sensor.ovum_warmeenergie",
        )
        if electrical is None and thermal is None:
            return
        self.state["energy_import"] = (
            await self.coordinator.async_import_legacy_energy_totals(
                electrical_kwh=electrical,
                thermal_kwh=thermal,
            )
        )

    async def _async_attempt_migration(self) -> None:
        await self._async_capture_energy()
        active_sources = sorted(
            mapping.source
            for mapping in LEGACY_ENTITY_MAPPINGS
            if self.hass.states.get(mapping.source) is not None
        )
        if active_sources:
            self.state.update(
                {
                    "status": "waiting_for_legacy_removal",
                    "active_sources": active_sources,
                }
            )
            await self._store.async_save(self.state)
            return

        try:
            instance = get_instance(self.hass)
        except KeyError:
            self.state.update(
                {
                    "status": "failed",
                    "error": "recorder_not_loaded",
                }
            )
            await self._store.async_save(self.state)
            return

        await instance.async_recorder_ready.wait()
        result_future = self.hass.loop.create_future()

        @callback
        def _async_done(result: dict[str, Any]) -> None:
            if not result_future.done():
                result_future.set_result(result)

        timestamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
        instance.queue_task(
            LegacyRecorderMigrationTask(
                LEGACY_ENTITY_MAPPINGS,
                self.entry_id,
                timestamp,
                _async_done,
            )
        )
        result = await result_future
        self.state.update(result)
        finished_at = datetime.now(UTC).isoformat()
        self.state["attempted_at"] = finished_at
        self.state["active_sources"] = []
        if result.get("status") == "completed":
            self.state["completed_at"] = finished_at
            self.state["removed_registry_entries"] = (
                self._async_remove_legacy_registry_entries()
            )
        await self._store.async_save(self.state)

    @callback
    def _async_remove_legacy_registry_entries(self) -> list[str]:
        registry = er.async_get(self.hass)
        removed: list[str] = []
        for mapping in LEGACY_ENTITY_MAPPINGS:
            if (
                (entry := registry.async_get(mapping.source)) is not None
                and entry.platform in _LEGACY_PLATFORMS
            ):
                registry.async_remove(mapping.source)
                removed.append(mapping.source)
        return removed

    def diagnostics(self) -> dict[str, Any]:
        """Return serializable migration progress."""
        return dict(self.state)
