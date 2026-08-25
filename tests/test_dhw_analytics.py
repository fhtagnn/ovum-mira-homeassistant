from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from custom_components.ovum_mira.dhw_analytics import (
    DhwAnalytics,
    DhwStartEvent,
    linear_regression_slope_c_per_hour,
    predict_crossing_time,
)
from custom_components.ovum_mira.history import HistorySample
from custom_components.ovum_mira.ovum_mira_modbus import WpmStatus


def _system(*, status: WpmStatus, temperature: float | None = 48.0):
    return SimpleNamespace(
        wpms=[SimpleNamespace(readings=SimpleNamespace(status=status))],
        hsm=SimpleNamespace(
            hot_water=SimpleNamespace(
                readings=SimpleNamespace(primary_temperature=temperature)
            )
        ),
    )


def _history_sample(timestamp: datetime, temperature: float, *, status: str = "ready"):
    return HistorySample(
        timestamp_utc=timestamp.isoformat(),
        outside_temperature_c=20.0,
        dhw_temperature_c=temperature,
        dhw_effective_target_c=50.0,
        dhw_enabled="on",
        buffer_temperature_c=33.0,
        wpm=[{"unit_id": 111, "status": status}],
    )


def test_linear_regression_slope_and_degenerate_inputs():
    start = datetime(2026, 8, 25, 6, 0, tzinfo=UTC)
    points = [
        (start, 48.0),
        (start + timedelta(minutes=30), 47.75),
        (start + timedelta(hours=1), 47.5),
    ]

    assert linear_regression_slope_c_per_hour(points) == pytest.approx(-0.5)
    assert linear_regression_slope_c_per_hour([]) is None
    assert linear_regression_slope_c_per_hour([(start, 48.0)]) is None
    assert linear_regression_slope_c_per_hour([(start, 48.0), (start, 47.0)]) is None


def test_predict_crossing_time_handles_limits():
    now = datetime(2026, 8, 25, 8, 0, tzinfo=UTC)

    assert predict_crossing_time(
        now=now,
        current_temperature_c=48.0,
        trigger_temperature_c=45.0,
        slope_c_per_hour=-0.5,
    ) == now + timedelta(hours=6)

    assert predict_crossing_time(
        now=now,
        current_temperature_c=44.0,
        trigger_temperature_c=45.0,
        slope_c_per_hour=-0.5,
    ) == now

    assert predict_crossing_time(
        now=now,
        current_temperature_c=48.0,
        trigger_temperature_c=45.0,
        slope_c_per_hour=-0.005,
    ) is None

    assert predict_crossing_time(
        now=now,
        current_temperature_c=50.0,
        trigger_temperature_c=45.0,
        slope_c_per_hour=-0.05,
    ) is None


async def test_load_filters_invalid_rows_and_caps_events(hass):
    analytics = DhwAnalytics(hass, "entry-id")
    rows = [
        {
            "timestamp_utc": (
                datetime(2026, 8, 24, 0, 0, tzinfo=UTC) + timedelta(hours=index)
            ).isoformat(),
            "temperature_c": 44 + index / 10,
        }
        for index in range(14)
    ]
    rows += [
        {"timestamp_utc": "not-a-date", "temperature_c": 99},
        {"timestamp_utc": None, "temperature_c": 99},
        "not-a-row",
    ]
    analytics._store.async_load = AsyncMock(return_value={"start_events": rows})

    await analytics.async_load()

    assert len(analytics.start_events) == 12
    assert analytics.start_events[0].temperature_c == pytest.approx(44.2)
    assert analytics.start_events[-1].temperature_c == pytest.approx(45.3)
    assert analytics.last_start == datetime(2026, 8, 24, 13, 0, tzinfo=UTC)
    assert analytics.estimated_trigger_temperature_c == pytest.approx(45.1)


async def test_load_ignores_non_mapping_storage(hass):
    analytics = DhwAnalytics(hass, "entry-id")
    analytics._store.async_load = AsyncMock(side_effect=[None, {"start_events": "bad"}])

    await analytics.async_load()
    await analytics.async_load()

    assert analytics.start_events == []
    assert analytics.last_start is None
    assert analytics.estimated_trigger_temperature_c is None


def test_initialize_live_state_prevents_false_restart_event(hass):
    analytics = DhwAnalytics(hass, "entry-id")
    system = _system(status=WpmStatus.HOT_WATER)

    analytics.initialize_live_state(system)
    analytics.update(system, SimpleNamespace(samples=[]))

    assert analytics.start_events == []


def test_transition_into_hot_water_records_start_once(hass):
    analytics = DhwAnalytics(hass, "entry-id")
    system = _system(status=WpmStatus.READY, temperature=44.5)
    analytics.initialize_live_state(system)
    now = datetime(2026, 8, 25, 8, 15, tzinfo=UTC)

    with (
        patch(
            "custom_components.ovum_mira.dhw_analytics.dt_util.utcnow",
            return_value=now,
        ),
        patch.object(analytics._store, "async_delay_save") as delay_save,
    ):
        system.wpms[0].readings.status = WpmStatus.HOT_WATER
        analytics.update(system, SimpleNamespace(samples=[]))
        analytics.update(system, SimpleNamespace(samples=[]))

    assert analytics.start_events == [
        DhwStartEvent(timestamp_utc=now.isoformat(), temperature_c=44.5)
    ]
    delay_save.assert_called_once_with(analytics.as_storage_dict, 5)
    assert analytics.current_slope_c_per_hour is None
    assert analytics.predicted_next_start is None
    assert analytics.slope_samples_used == 0


def test_forecast_uses_recent_non_dhw_cooling_samples(hass):
    analytics = DhwAnalytics(hass, "entry-id")
    analytics.start_events = [
        DhwStartEvent(
            timestamp_utc=datetime(2026, 8, 24, 6, 0, tzinfo=UTC).isoformat(),
            temperature_c=45.0,
        )
    ]
    system = _system(status=WpmStatus.READY, temperature=48.0)
    analytics.initialize_live_state(system)
    now = datetime(2026, 8, 25, 8, 0, tzinfo=UTC)
    samples = [
        _history_sample(
            now - timedelta(minutes=60 - index * 10),
            48.5 - index * (0.5 / 6),
        )
        for index in range(7)
    ]
    # This point is recent but explicitly belongs to a DHW cycle and must be ignored.
    samples.append(_history_sample(now - timedelta(minutes=5), 60.0, status="hot_water"))

    with patch(
        "custom_components.ovum_mira.dhw_analytics.dt_util.utcnow",
        return_value=now,
    ):
        analytics.update(system, SimpleNamespace(samples=samples))

    assert analytics.current_slope_c_per_hour == pytest.approx(-0.5)
    assert analytics.slope_samples_used == 7
    assert analytics.predicted_next_start == now + timedelta(hours=6)


def test_forecast_requires_enough_time_and_samples(hass):
    analytics = DhwAnalytics(hass, "entry-id")
    analytics.start_events = [
        DhwStartEvent(
            timestamp_utc=datetime(2026, 8, 24, 6, 0, tzinfo=UTC).isoformat(),
            temperature_c=45.0,
        )
    ]
    system = _system(status=WpmStatus.READY, temperature=48.0)
    analytics.initialize_live_state(system)
    now = datetime(2026, 8, 25, 8, 0, tzinfo=UTC)

    short_samples = [
        _history_sample(now - timedelta(minutes=25 - index * 5), 48.5 - index * 0.05)
        for index in range(6)
    ]
    with patch(
        "custom_components.ovum_mira.dhw_analytics.dt_util.utcnow",
        return_value=now,
    ):
        analytics.update(system, SimpleNamespace(samples=short_samples))

    assert analytics.current_slope_c_per_hour is None
    assert analytics.predicted_next_start is None
    assert analytics.slope_samples_used == 0


def test_diagnostics_and_storage_export(hass):
    analytics = DhwAnalytics(hass, "entry-id")
    timestamp = datetime(2026, 8, 25, 7, 0, tzinfo=UTC)
    analytics.start_events = [
        DhwStartEvent(timestamp_utc=timestamp.isoformat(), temperature_c=44.0),
        DhwStartEvent(
            timestamp_utc=(timestamp + timedelta(hours=1)).isoformat(),
            temperature_c=46.0,
        ),
    ]
    analytics.current_slope_c_per_hour = -0.4
    analytics.predicted_next_start = timestamp + timedelta(hours=8)
    analytics.slope_samples_used = 12

    assert analytics.as_storage_dict()["start_events"][0]["temperature_c"] == 44.0
    diagnostics = analytics.diagnostics()
    assert diagnostics["last_start_utc"] == (timestamp + timedelta(hours=1)).isoformat()
    assert diagnostics["estimated_trigger_temperature_c"] == 45.0
    assert diagnostics["current_slope_c_per_hour"] == -0.4
    assert diagnostics["predicted_next_start_utc"] == (
        timestamp + timedelta(hours=8)
    ).isoformat()
    assert diagnostics["slope_samples_used"] == 12


async def test_explicit_save_persists_current_events(hass):
    analytics = DhwAnalytics(hass, "entry-id")
    analytics.start_events = [
        DhwStartEvent(
            timestamp_utc=datetime(2026, 8, 25, 7, 0, tzinfo=UTC).isoformat(),
            temperature_c=45.0,
        )
    ]
    analytics._store.async_save = AsyncMock()

    await analytics.async_save()

    analytics._store.async_save.assert_awaited_once_with(analytics.as_storage_dict())
