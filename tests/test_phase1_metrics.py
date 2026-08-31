from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from custom_components.ovum_mira.dhw_analytics import DhwAnalytics, DhwStartEvent
from custom_components.ovum_mira.energy import (
    MODE_HEATING,
    MODE_HOT_WATER,
    MODE_OTHER,
    EnergyAccumulator,
    EnergyBook,
    classify_interval_mode,
)
from custom_components.ovum_mira.ovum_mira_modbus import WpmStatus


def test_interval_mode_classification_handles_transitions_and_defrost():
    mode, remembered = classify_interval_mode(
        WpmStatus.START,
        WpmStatus.HOT_WATER,
        None,
    )
    assert mode == MODE_HOT_WATER
    assert remembered == MODE_HOT_WATER

    mode, remembered = classify_interval_mode(
        WpmStatus.HOT_WATER,
        WpmStatus.STOPPING,
        remembered,
    )
    assert mode == MODE_HOT_WATER
    assert remembered == MODE_HOT_WATER

    mode, remembered = classify_interval_mode(
        WpmStatus.HEATING,
        WpmStatus.DEFROST,
        MODE_HEATING,
    )
    assert mode == MODE_HEATING
    assert remembered == MODE_HEATING

    mode, _ = classify_interval_mode(
        WpmStatus.HEATING,
        WpmStatus.MANUAL_DEFROST,
        MODE_HEATING,
    )
    assert mode == MODE_OTHER


def test_energy_accumulator_tracks_mode_energy_and_one_compressor_cycle():
    start = datetime(2026, 8, 28, 8, 0, tzinfo=UTC)
    acc = EnergyAccumulator()
    acc.set_baseline(
        now_utc=start,
        local_now=start,
        electrical_kw=0.0,
        thermal_kw=0.0,
        status=WpmStatus.READY,
        compressor_runtime_minutes=100,
    )

    acc.update(
        now_utc=start + timedelta(minutes=1),
        local_now=start + timedelta(minutes=1),
        electrical_kw=1.0,
        thermal_kw=4.0,
        status=WpmStatus.START,
        compressor_runtime_minutes=100,
    )
    acc.update(
        now_utc=start + timedelta(minutes=2),
        local_now=start + timedelta(minutes=2),
        electrical_kw=1.0,
        thermal_kw=4.0,
        status=WpmStatus.HEATING,
        compressor_runtime_minutes=101,
    )
    acc.update(
        now_utc=start + timedelta(minutes=3),
        local_now=start + timedelta(minutes=3),
        electrical_kw=1.0,
        thermal_kw=4.0,
        status=WpmStatus.STOPPING,
        compressor_runtime_minutes=102,
    )
    acc.update(
        now_utc=start + timedelta(minutes=4),
        local_now=start + timedelta(minutes=4),
        electrical_kw=0.0,
        thermal_kw=0.0,
        status=WpmStatus.READY,
        compressor_runtime_minutes=103,
    )

    assert acc.compressor_starts_total == 1
    assert acc.compressor_starts_today == 1
    assert acc.compressor_starts_week == 1
    assert acc.completed_cycles == 1
    assert acc.average_cycle_runtime_minutes == pytest.approx(3.0)
    assert acc.modes[MODE_HEATING].total_electrical_kwh > 0
    assert acc.modes[MODE_HEATING].total_thermal_kwh > 0
    assert sum(bucket.total_electrical_kwh for bucket in acc.modes.values()) == pytest.approx(
        acc.total_electrical_kwh
    )
    assert sum(bucket.total_thermal_kwh for bucket in acc.modes.values()) == pytest.approx(
        acc.total_thermal_kwh
    )


def test_rolling_start_average_includes_today_and_observed_zero_start_days():
    today = datetime(2026, 8, 28, 12, 0, tzinfo=UTC)
    acc = EnergyAccumulator()
    acc.ensure_period(today - timedelta(days=2))
    acc.ensure_period(today - timedelta(days=1))
    acc.ensure_period(today)
    acc.start_counts_by_day[today.date().isoformat()] = 6

    assert acc.start_counts_by_day[(today - timedelta(days=1)).date().isoformat()] == 0
    assert acc.start_counts_by_day[(today - timedelta(days=2)).date().isoformat()] == 0
    assert acc.average_starts_per_day_7d == pytest.approx(2.0)


def test_v1_migration_preserves_authoritative_totals_and_assigns_residual_to_other():
    start = datetime(2026, 8, 28, 8, 0, tzinfo=UTC)
    samples = [
        SimpleNamespace(
            timestamp_utc=(start + timedelta(minutes=index)).isoformat(),
            wpm=[
                {
                    "unit_id": 111,
                    "status": "hot_water" if index < 2 else "ready",
                    "electrical_power_kw": 1.0 if index < 2 else 0.0,
                    "thermal_power_kw": 4.0 if index < 2 else 0.0,
                }
            ],
        )
        for index in range(3)
    ]
    v1 = {
        "units": {
            "111": {
                "total_electrical_kwh": 10.0,
                "total_thermal_kwh": 40.0,
                "daily_electrical_kwh": 2.0,
                "daily_thermal_kwh": 8.0,
                "weekly_electrical_kwh": 5.0,
                "weekly_thermal_kwh": 20.0,
                "day_key": "2026-08-28",
                "week_key": "2026-W35",
            }
        }
    }

    migrated = EnergyBook.migrate_v1_storage(v1, samples, localize=lambda value: value)
    acc = EnergyAccumulator.from_storage_dict(migrated["units"]["111"])

    assert acc.total_electrical_kwh == 10.0
    assert acc.total_thermal_kwh == 40.0
    assert acc.daily_electrical_kwh == 2.0
    assert acc.weekly_thermal_kwh == 20.0
    assert sum(bucket.total_electrical_kwh for bucket in acc.modes.values()) == pytest.approx(10.0)
    assert sum(bucket.total_thermal_kwh for bucket in acc.modes.values()) == pytest.approx(40.0)
    assert acc.modes[MODE_HOT_WATER].total_electrical_kwh > 0
    assert acc.modes[MODE_OTHER].total_electrical_kwh > 0


def test_dhw_interval_statistics_require_two_fully_covered_valid_intervals(hass):
    analytics = DhwAnalytics(hass, "entry-id")
    start = datetime(2026, 8, 28, 0, 0, tzinfo=UTC)
    analytics.start_events = [
        DhwStartEvent(timestamp_utc=start.isoformat(), temperature_c=45.0),
        DhwStartEvent(
            timestamp_utc=(start + timedelta(hours=3)).isoformat(),
            temperature_c=45.0,
        ),
        DhwStartEvent(
            timestamp_utc=(start + timedelta(hours=6)).isoformat(),
            temperature_c=45.0,
        ),
    ]
    samples = [
        SimpleNamespace(timestamp_utc=(start + timedelta(minutes=index)).isoformat())
        for index in range(6 * 60 + 1)
    ]
    history = SimpleNamespace(samples=samples)

    analytics._update_interval_statistics(history)

    assert analytics.valid_heating_intervals == 2
    assert analytics.average_heating_interval_hours == pytest.approx(3.0)
    assert analytics.median_heating_interval_hours == pytest.approx(3.0)

    history.samples = [
        sample
        for sample in samples
        if not (
            start + timedelta(hours=1)
            < datetime.fromisoformat(sample.timestamp_utc)
            < start + timedelta(hours=1, minutes=5)
        )
    ]
    analytics._interval_cache_marker = None
    analytics._update_interval_statistics(history)

    assert analytics.valid_heating_intervals == 1
    assert analytics.average_heating_interval_hours is None
    assert analytics.median_heating_interval_hours is None
