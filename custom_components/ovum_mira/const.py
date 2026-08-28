from __future__ import annotations

from datetime import timedelta

from homeassistant.const import Platform

DOMAIN = "ovum_mira"
INTEGRATION_VERSION = "0.1.0-beta.2"
PLATFORMS = [
    Platform.SENSOR,
    Platform.SELECT,
    Platform.NUMBER,
    Platform.CLIMATE,
    Platform.WATER_HEATER,
    Platform.SWITCH,
]

DEFAULT_PORT = 502
DEFAULT_WPM_COUNT = 1
HSM_UNIT = 110
FIRST_WPM_UNIT = 111
MAX_WPM_COUNT = 8
DEFAULT_SCAN_INTERVAL = timedelta(seconds=15)

CONF_WPM_COUNT = "wpm_count"
# Deprecated v0.1 key. Kept temporarily so existing config entries can migrate cleanly.
CONF_WPM_UNIT = "wpm_unit"
CONF_LOGIN_CODE = "login_code"
CONF_BUFFER_SENSOR_COUNT = "heating_buffer_sensor_count"
CONF_DHW_SENSOR_COUNT = "hot_water_sensor_count"
CONF_HK1_ROOM_SENSOR = "heating_circuit_1_room_sensor"
CONF_PV_SENSOR_MODULE = "pv_sensor_module_installed"
