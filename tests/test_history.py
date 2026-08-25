from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from custom_components.ovum_mira.history import HistoryBook, HistorySample, _enum_name
from custom_components.ovum_mira.ovum_mira_modbus import SwitchState, WpmStatus


def _system(*, with_dhw: bool = True, with_buffer: bool = True):
    hot_water = None
    if with_dhw:
        hot_water = SimpleNamespace(
            readings=SimpleNamespace(
                primary_temperature=48.2,
                effective_target_temperature=50.0,
            ),
            settings=SimpleNamespace(enabled=SwitchState.ON),
        )
    buffer = None
    if with_buffer:
        buffer = SimpleNamespace(
            readings=SimpleNamespace(primary_temperature=33.8)
        )
    wpm = SimpleNamespace(
        readings=SimpleNamespace(
            status=WpmStatus.READY,
            demand_percent=25,
            electrical_power=0.75,
            thermal_power=3.2,
            condenser_inlet_temperature=31.5,
            condenser_outlet_temperature=36.0,
        )
    )
    return SimpleNamespace(
        hsm=SimpleNamespace(
            common=SimpleNamespace(outside_temperature=17.4),
            hot_water=hot_water,
            heating_buffer=buffer,
        ),
        wpms=[wpm],
    )


def _sample(timestamp: datetime) -> dict:
    return {
        "timestamp_utc": timestamp.isoformat(),
        "outside_temperature_c": 20.0,
        "dhw_temperature_c": 48.0,
        "dhw_effective_target_c": 50.0,
        "dhw_enabled": "on",
        "buffer_temperature_c": 33.0,
        "wpm": [],
    }


def test_enum_name_handles_enum_string_and_none():
    assert _enum_name(WpmStatus.READY) == "ready"
    assert _enum_name("custom") == "custom"
    assert _enum_name(None) is None


async def test_load_prunes_old_and_invalid_samples(hass):
    book = HistoryBook(hass, "entry-id")
    now = datetime(2026, 8, 25, 8, 0, tzinfo=UTC)
    rows = [
        _sample(now - timedelta(days=15)),
        _sample(now - timedelta(days=1)),
        {**_sample(now), "timestamp_utc": "bad-timestamp"},
        {"missing": "required fields"},
        "not-a-row",
    ]
    book._store.async_load = AsyncMock(return_value={"samples": rows})

    with patch(
        "custom_components.ovum_mira.history.dt_util.utcnow",
        return_value=now,
    ):
        await book.async_load()

    assert len(book.samples) == 1
    assert book.samples[0].timestamp_utc == (now - timedelta(days=1)).isoformat()
    assert book._last_sample_utc == now - timedelta(days=1)


async def test_load_handles_empty_or_invalid_storage(hass):
    book = HistoryBook(hass, "entry-id")
    book._store.async_load = AsyncMock(side_effect=[None, {"samples": "bad"}])

    await book.async_load()
    await book.async_load()

    assert book.samples == []
    assert book._last_sample_utc is None


def test_maybe_sample_records_synchronized_state_and_throttles(hass):
    book = HistoryBook(hass, "entry-id")
    system = _system()
    now = datetime(2026, 8, 25, 8, 0, tzinfo=UTC)

    with (
        patch(
            "custom_components.ovum_mira.history.dt_util.utcnow",
            return_value=now,
        ),
        patch.object(book._store, "async_delay_save") as delay_save,
    ):
        book.maybe_sample(system)
        book.maybe_sample(system)

    assert len(book.samples) == 1
    sample = book.samples[0]
    assert sample.timestamp_utc == now.isoformat()
    assert sample.outside_temperature_c == 17.4
    assert sample.dhw_temperature_c == 48.2
    assert sample.dhw_effective_target_c == 50.0
    assert sample.dhw_enabled == "on"
    assert sample.buffer_temperature_c == 33.8
    assert sample.wpm == [
        {
            "unit_id": 111,
            "status": "ready",
            "demand_percent": 25,
            "electrical_power_kw": 0.75,
            "thermal_power_kw": 3.2,
            "condenser_inlet_c": 31.5,
            "condenser_outlet_c": 36.0,
        }
    ]
    delay_save.assert_called_once_with(book.as_storage_dict, 600)


def test_maybe_sample_supports_missing_optional_subsystems(hass):
    book = HistoryBook(hass, "entry-id")
    system = _system(with_dhw=False, with_buffer=False)
    now = datetime(2026, 8, 25, 8, 0, tzinfo=UTC)

    with patch(
        "custom_components.ovum_mira.history.dt_util.utcnow",
        return_value=now,
    ):
        book.maybe_sample(system)

    sample = book.samples[0]
    assert sample.dhw_temperature_c is None
    assert sample.dhw_effective_target_c is None
    assert sample.dhw_enabled is None
    assert sample.buffer_temperature_c is None


def test_prune_keeps_only_recent_valid_timestamps(hass):
    book = HistoryBook(hass, "entry-id")
    now = datetime(2026, 8, 25, 8, 0, tzinfo=UTC)
    book.samples = [
        HistorySample(**_sample(now - timedelta(days=14, seconds=1))),
        HistorySample(**_sample(now - timedelta(days=14))),
        HistorySample(**{**_sample(now), "timestamp_utc": "invalid"}),
        HistorySample(**_sample(now)),
    ]

    book._prune(now)

    assert [sample.timestamp_utc for sample in book.samples] == [
        (now - timedelta(days=14)).isoformat(),
        now.isoformat(),
    ]


def test_storage_and_export_metadata(hass):
    book = HistoryBook(hass, "entry-id")
    now = datetime(2026, 8, 25, 8, 0, tzinfo=UTC)
    book.samples = [HistorySample(**_sample(now))]

    storage = book.as_storage_dict()
    assert storage["samples"][0]["timestamp_utc"] == now.isoformat()

    exported = book.export_dict()
    assert exported["format"] == "ovum_mira_analysis_history_v1"
    assert exported["sample_interval_seconds"] == 60
    assert exported["retention_days"] == 14
    assert exported["sample_count"] == 1
    assert exported["samples"] == storage["samples"]


async def test_explicit_save_persists_samples(hass):
    book = HistoryBook(hass, "entry-id")
    now = datetime(2026, 8, 25, 8, 0, tzinfo=UTC)
    book.samples = [HistorySample(**_sample(now))]
    book._store.async_save = AsyncMock()

    await book.async_save()

    book._store.async_save.assert_awaited_once_with(book.as_storage_dict())
