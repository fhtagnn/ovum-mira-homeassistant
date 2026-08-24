# These tests intentionally exercise the DHW prediction math without importing
# the Home Assistant integration package.


def test_expected_linear_prediction_math():
    current = 48.0
    trigger = 45.0
    slope = -0.5  # °C/h
    hours = (trigger - current) / slope
    assert hours == 6.0


def test_slope_sign_for_cooling():
    temps = [48.0, 47.5, 47.0]
    assert temps[-1] - temps[0] < 0
