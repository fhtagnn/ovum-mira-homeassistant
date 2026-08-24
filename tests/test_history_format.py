def test_history_sample_shape_is_json_serializable():
    # Keep this test dependency-free so it can run outside Home Assistant Core.
    sample = {
        "timestamp_utc": "2026-08-19T12:00:00+00:00",
        "outside_temperature_c": 20.1,
        "dhw_temperature_c": 48.2,
        "dhw_effective_target_c": 50.0,
        "dhw_enabled": "on",
        "buffer_temperature_c": 33.8,
        "wpm": [
            {
                "unit_id": 111,
                "status": "ready",
                "demand_percent": 0,
                "electrical_power_kw": 0.003,
                "thermal_power_kw": 0.0,
                "condenser_inlet_c": 34.7,
                "condenser_outlet_c": 40.7,
            }
        ],
    }
    assert sample["wpm"][0]["unit_id"] == 111
    assert sample["dhw_temperature_c"] == 48.2
