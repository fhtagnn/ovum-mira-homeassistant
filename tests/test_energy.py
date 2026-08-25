from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from custom_components.ovum_mira.energy import (
    EnergyAccumulator,
    EnergyBook,
    _clean_power,
)


def test_clean_power_rejects_invalid_values():
    assert _clean_power(None) == 0.0
    assert _clean_power("bad") == 0.0
    assert _clean_power(float("nan")) == 0.0
    assert _clean_power(float("inf")) == 0.0
    assert _clean_power(-1) == 0.0
    assert _clean_power(2.5) == 2.5


def test_period_rollover_resets_only_changed_periods():
    now = datetime(2026, 8, 25, 12, 0, tzinfo=UTC)
    acc = EnergyAccumulator()
    acc.ensure_period(now)
    acc.daily_electrical_kwh = 1.0
    acc.daily_thermal_kwh = 4.0
    acc.weekly_electrical_kwh = 2.0
    acc.weekly_thermal_kwh = 8.0

    acc.ensure_period(now + timedelta(days=1))

    assert acc.daily_electrical_kwh == 0.0
    assert acc.daily_thermal_kwh == 0.0
    assert acc.weekly_electrical_kwh == 2.0
    assert acc.weekly_thermal_kwh == 8.0

    acc.ensure_period(now + timedelta(days=7))
    assert acc.weekly_electrical_kwh == 0.0
    assert acc.weekly_thermal_kwh == 0.0


def test_energy_integration_uses_trapezoid_and_skips_long_gaps():
    start = datetime(2026, 8, 25, 8, 0, tzinfo=UTC)
    acc = EnergyAccumulator()
    acc.set_baseline(
        now_utc=start,
        local_now=start,
        electrical_kw=1.0,
        thermal_kw=2.0,
    )

    acc.update(
        now_utc=start + timedelta(seconds=60),
        local_now=start + timedelta(seconds=60),
        electrical_kw=3.0,
        thermal_kw=4.0,
    )

    assert acc.total_electrical_kwh == pytest.approx(2.0 / 60.0)
    assert acc.total_thermal_kwh == pytest.approx(3.0 / 60.0)
    first_electrical = acc.total_electrical_kwh
    first_thermal = acc.total_thermal_kwh

    acc.update(
        now_utc=start + timedelta(seconds=600),
        local_now=start + timedelta(seconds=600),
        electrical_kw=5.0,
        thermal_kw=6.0,
    )
    assert acc.total_electrical_kwh == first_electrical
    assert acc.total_thermal_kwh == first_thermal

    acc.update(
        now_utc=start + timedelta(seconds=660),
        local_now=start + timedelta(seconds=660),
        electrical_kw=5.0,
        thermal_kw=6.0,
    )
    assert acc.total_electrical_kwh == pytest.approx(first_electrical + 5.0 / 60.0)
    assert acc.total_thermal_kwh == pytest.approx(first_thermal + 6.0 / 60.0)


def test_cop_and_work_factor_guardrails():
    acc = EnergyAccumulator()
    acc._last_electrical_kw = 1.0
    acc._last_thermal_kw = 4.0
    assert acc.instantaneous_cop == 4.0

    acc._last_electrical_kw = 0.01
    assert acc.instantaneous_cop is None
    acc._last_electrical_kw = 0.1
    acc._last_thermal_kw = 0.0
    assert acc.instantaneous_cop is None
    acc._last_thermal_kw = 3.0
    assert acc.instantaneous_cop is None

    acc.daily_electrical_kwh = 1.0
    acc.daily_thermal_kwh = 4.0
    acc.weekly_electrical_kwh = 2.0
    acc.weekly_thermal_kwh = 7.0
    acc.total_electrical_kwh = 3.0
    acc.total_thermal_kwh = 9.0
    assert acc.daily_work_factor == 4.0
    assert acc.weekly_work_factor == 3.5
    assert acc.total_work_factor == 3.0

    assert EnergyAccumulator._ratio(1.0, 0.001) is None
    assert EnergyAccumulator._ratio(-1.0, 1.0) is None
    assert EnergyAccumulator._ratio(30.0, 1.0) is None


def test_energy_storage_round_trip_excludes_transient_samples():
    start = datetime(2026, 8, 25, 8, 0, tzinfo=UTC)
    acc = EnergyAccumulator(
        total_electrical_kwh=12.3,
        total_thermal_kwh=45.6,
        day_key="2026-08-25",
        week_key="2026-W35",
    )
    acc.set_baseline(
        now_utc=start,
        local_now=start,
        electrical_kw=1.5,
        thermal_kw=4.5,
    )

    stored = acc.as_storage_dict()
    assert "_last_utc" not in stored
    assert "_last_electrical_kw" not in stored
    assert "_last_thermal_kw" not in stored

    restored = EnergyAccumulator.from_storage_dict({**stored, "ignored": 123})
    assert restored.total_electrical_kwh == 12.3
    assert restored.total_thermal_kwh == 45.6
    assert restored._last_utc is None
    assert EnergyAccumulator.from_storage_dict(None) == EnergyAccumulator()


def test_energy_book_load_store_and_aggregate():
    book = EnergyBook([111, 112])
    book.load(
        {
            "units": {
                "111": {
                    "total_electrical_kwh": 10.0,
                    "total_thermal_kwh": 30.0,
                    "daily_electrical_kwh": 1.0,
                    "daily_thermal_kwh": 3.0,
                    "weekly_electrical_kwh": 4.0,
                    "weekly_thermal_kwh": 12.0,
                    "day_key": "2026-08-25",
                    "week_key": "2026-W35",
                },
                "112": {
                    "total_electrical_kwh": 20.0,
                    "total_thermal_kwh": 70.0,
                    "daily_electrical_kwh": 2.0,
                    "daily_thermal_kwh": 7.0,
                    "weekly_electrical_kwh": 5.0,
                    "weekly_thermal_kwh": 18.0,
                    "day_key": "2026-08-25",
                    "week_key": "2026-W35",
                },
            }
        }
    )
    book.by_unit[111]._last_electrical_kw = 1.0
    book.by_unit[111]._last_thermal_kw = 3.0
    book.by_unit[112]._last_electrical_kw = 2.0
    book.by_unit[112]._last_thermal_kw = 7.0

    total = book.aggregate()
    assert total.total_electrical_kwh == 30.0
    assert total.total_thermal_kwh == 100.0
    assert total.daily_electrical_kwh == 3.0
    assert total.weekly_thermal_kwh == 30.0
    assert total.day_key == "2026-08-25"
    assert total.week_key == "2026-W35"
    assert total.instantaneous_cop == pytest.approx(10.0 / 3.0)

    stored = book.as_storage_dict()
    assert set(stored["units"]) == {"111", "112"}
    assert EnergyBook([]).aggregate() == EnergyAccumulator()
