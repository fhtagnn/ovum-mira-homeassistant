from datetime import datetime, timedelta, timezone
import importlib.util
import sys
from pathlib import Path

MODULE = Path(__file__).parents[1] / "custom_components" / "ovum_mira" / "energy.py"
spec = importlib.util.spec_from_file_location("ovum_energy", MODULE)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)
EnergyAccumulator = mod.EnergyAccumulator


def test_one_hour_constant_power():
    acc = EnergyAccumulator()
    t0 = datetime(2026, 8, 19, 10, 0, tzinfo=timezone.utc)
    acc.set_baseline(now_utc=t0, local_now=t0, electrical_kw=2, thermal_kw=8)
    # 30-second samples for one hour stay below the anti-gap threshold.
    for i in range(1, 121):
        now = t0 + timedelta(seconds=30 * i)
        acc.update(now_utc=now, local_now=now, electrical_kw=2, thermal_kw=8)
    assert abs(acc.total_electrical_kwh - 2.0) < 1e-9
    assert abs(acc.total_thermal_kwh - 8.0) < 1e-9
    assert abs(acc.total_work_factor - 4.0) < 1e-9
    assert abs(acc.instantaneous_cop - 4.0) < 1e-9


def test_long_gap_is_not_integrated():
    acc = EnergyAccumulator()
    t0 = datetime(2026, 8, 19, 10, 0, tzinfo=timezone.utc)
    acc.set_baseline(now_utc=t0, local_now=t0, electrical_kw=2, thermal_kw=8)
    t1 = t0 + timedelta(minutes=10)
    acc.update(now_utc=t1, local_now=t1, electrical_kw=2, thermal_kw=8)
    assert acc.total_electrical_kwh == 0
    assert acc.total_thermal_kwh == 0


def test_daily_and_weekly_reset():
    acc = EnergyAccumulator(
        daily_electrical_kwh=3,
        daily_thermal_kwh=9,
        weekly_electrical_kwh=4,
        weekly_thermal_kwh=12,
        day_key="2026-08-18",
        week_key="2026-W33",
    )
    now = datetime(2026, 8, 24, 0, 1, tzinfo=timezone.utc)  # ISO week 35? key only needs change
    acc.ensure_period(now)
    assert acc.daily_electrical_kwh == 0
    assert acc.daily_thermal_kwh == 0
    assert acc.weekly_electrical_kwh == 0
    assert acc.weekly_thermal_kwh == 0


def test_cop_hidden_at_standby_power():
    acc = EnergyAccumulator()
    t0 = datetime(2026, 8, 19, 10, 0, tzinfo=timezone.utc)
    acc.set_baseline(now_utc=t0, local_now=t0, electrical_kw=0.003, thermal_kw=0)
    assert acc.instantaneous_cop is None
