from collections.abc import Mapping
from typing import Any

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.data_entry_flow import FlowResult
import voluptuous as vol

from .const import (
    CONF_BUFFER_SENSOR_COUNT,
    CONF_DHW_HOLIDAY_DETECTION,
    CONF_DHW_HOLIDAY_THRESHOLD,
    CONF_DHW_SENSOR_COUNT,
    CONF_HK1_ROOM_SENSOR,
    CONF_LOGIN_CODE,
    CONF_PV_SENSOR_MODULE,
    CONF_WPM_COUNT,
    DEFAULT_DHW_HOLIDAY_THRESHOLD,
    DEFAULT_PORT,
    DEFAULT_WPM_COUNT,
    DOMAIN,
    MAX_WPM_COUNT,
)
from .ovum_mira_modbus import BufferSystemType, HeatingCircuitType, InstallationOptions, SwitchState
from .runtime import async_open_system


def _installation_options_for_entry(entry: config_entries.ConfigEntry) -> InstallationOptions:
    """Build physical installation options from config-entry data and options."""
    cfg = {**entry.data, **entry.options}
    return InstallationOptions(
        heating_buffer_sensor_count=cfg.get(CONF_BUFFER_SENSOR_COUNT, 1),
        hot_water_sensor_count=cfg.get(CONF_DHW_SENSOR_COUNT, 1),
        heating_circuit_1_room_sensor=cfg.get(CONF_HK1_ROOM_SENSOR, False),
        pv_sensor_module_installed=cfg.get(CONF_PV_SENSOR_MODULE, False),
        enable_ems_writes=False,
    )


class OvumMiraConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for OVUM MIRA."""

    VERSION = 5
    MINOR_VERSION = 0

    def __init__(self) -> None:
        self._connection_data: dict[str, Any] = {}
        self._detected: dict[str, bool] = {}

    @staticmethod
    def async_get_options_flow(config_entry):
        return OvumMiraOptionsFlow()

    async def _async_test_entry_connection(
        self,
        entry: config_entries.ConfigEntry,
        *,
        host: str,
        port: int,
        wpm_count: int,
        login_text: str,
    ) -> dict[str, str]:
        """Validate changed connection or authentication data against the controller."""
        try:
            login_code = int(login_text) if login_text else None
        except ValueError:
            return {CONF_LOGIN_CODE: "invalid_login_code"}

        try:
            connection, _system = await async_open_system(
                host,
                port,
                wpm_count,
                login_code=login_code,
                options=_installation_options_for_entry(entry),
            )
        except PermissionError:
            return {"base": "invalid_auth"}
        except Exception:
            return {"base": "cannot_connect"}

        await connection.close()
        return {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            port = user_input[CONF_PORT]
            wpm_count = user_input[CONF_WPM_COUNT]
            login_text = user_input.get(CONF_LOGIN_CODE, "").strip()
            try:
                login_code = int(login_text) if login_text else None
            except ValueError:
                errors[CONF_LOGIN_CODE] = "invalid_login_code"
            else:
                await self.async_set_unique_id(f"{host}:{port}")
                self._abort_if_unique_id_configured()
                try:
                    connection, system = await async_open_system(
                        host,
                        port,
                        wpm_count,
                        login_code=login_code,
                        options=InstallationOptions(),
                    )
                except PermissionError:
                    errors["base"] = "invalid_auth"
                except Exception:
                    errors["base"] = "cannot_connect"
                else:
                    try:
                        caps = system.hsm.capabilities
                        self._detected = {
                            "buffer": caps.heating_buffer_type not in (None, BufferSystemType.NONE),
                            "dhw": caps.hot_water_installed == SwitchState.ON,
                            "hk1": caps.heating_circuit_1_type not in (None, HeatingCircuitType.NONE),
                        }
                    finally:
                        await connection.close()
                    self._connection_data = {
                        CONF_HOST: host,
                        CONF_PORT: port,
                        CONF_WPM_COUNT: wpm_count,
                        CONF_LOGIN_CODE: login_text,
                    }
                    return await self.async_step_installation()

        schema = vol.Schema(
            {
                vol.Required(CONF_HOST): str,
                vol.Required(CONF_PORT, default=DEFAULT_PORT): vol.All(int, vol.Range(min=1, max=65535)),
                vol.Required(CONF_WPM_COUNT, default=DEFAULT_WPM_COUNT): vol.In(
                    {count: str(count) for count in range(1, MAX_WPM_COUNT + 1)}
                ),
                vol.Optional(CONF_LOGIN_CODE, default=""): str,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_installation(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            options = {
                CONF_BUFFER_SENSOR_COUNT: user_input.get(CONF_BUFFER_SENSOR_COUNT, 1),
                CONF_DHW_SENSOR_COUNT: user_input.get(CONF_DHW_SENSOR_COUNT, 1),
                CONF_HK1_ROOM_SENSOR: user_input.get(CONF_HK1_ROOM_SENSOR, False),
                CONF_PV_SENSOR_MODULE: user_input.get(CONF_PV_SENSOR_MODULE, False),
            }
            return self.async_create_entry(
                title="OVUM MIRA",
                data=self._connection_data,
                options=options,
            )

        fields: dict[Any, Any] = {}
        if self._detected.get("buffer"):
            fields[vol.Required(CONF_BUFFER_SENSOR_COUNT, default=1)] = vol.In({1: "1", 2: "2"})
        if self._detected.get("dhw"):
            fields[vol.Required(CONF_DHW_SENSOR_COUNT, default=1)] = vol.In({1: "1", 2: "2"})
        if self._detected.get("hk1"):
            fields[vol.Required(CONF_HK1_ROOM_SENSOR, default=False)] = bool
        fields[vol.Required(CONF_PV_SENSOR_MODULE, default=False)] = bool
        return self.async_show_form(step_id="installation", data_schema=vol.Schema(fields))

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> FlowResult:
        """Start reauthentication after Home Assistant reports invalid credentials."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Validate and replace only the Modbus login code."""
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        login_text = ""

        if user_input is not None:
            login_text = user_input.get(CONF_LOGIN_CODE, "").strip()
            errors = await self._async_test_entry_connection(
                entry,
                host=entry.data[CONF_HOST],
                port=entry.data[CONF_PORT],
                wpm_count=entry.data.get(CONF_WPM_COUNT, DEFAULT_WPM_COUNT),
                login_text=login_text,
            )
            if not errors:
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates={CONF_LOGIN_CODE: login_text},
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {vol.Optional(CONF_LOGIN_CODE, default=login_text): str}
            ),
            errors=errors,
        )

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Change connection details and verify them before storing."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            port = user_input[CONF_PORT]
            wpm_count = user_input[CONF_WPM_COUNT]
            login_text = str(entry.data.get(CONF_LOGIN_CODE, "") or "").strip()
            errors = await self._async_test_entry_connection(
                entry,
                host=host,
                port=port,
                wpm_count=wpm_count,
                login_text=login_text,
            )
            if not errors:
                unique_id = f"{host}:{port}"
                if unique_id != entry.unique_id:
                    await self.async_set_unique_id(unique_id)
                    self._abort_if_unique_id_configured()
                return self.async_update_reload_and_abort(
                    entry,
                    unique_id=unique_id,
                    data_updates={
                        CONF_HOST: host,
                        CONF_PORT: port,
                        CONF_WPM_COUNT: wpm_count,
                    },
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_HOST): str,
                vol.Required(CONF_PORT): vol.All(int, vol.Range(min=1, max=65535)),
                vol.Required(CONF_WPM_COUNT): vol.In(
                    {count: str(count) for count in range(1, MAX_WPM_COUNT + 1)}
                ),
            }
        )
        suggested_values = user_input or entry.data
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(schema, suggested_values),
            errors=errors,
        )


class OvumMiraOptionsFlow(config_entries.OptionsFlowWithReload):
    """Allow installation details and local analytics to be configured."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        current = {**self.config_entry.data, **self.config_entry.options}
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_BUFFER_SENSOR_COUNT,
                    default=current.get(CONF_BUFFER_SENSOR_COUNT, 1),
                ): vol.In({1: "1", 2: "2"}),
                vol.Required(
                    CONF_DHW_SENSOR_COUNT,
                    default=current.get(CONF_DHW_SENSOR_COUNT, 1),
                ): vol.In({1: "1", 2: "2"}),
                vol.Required(
                    CONF_HK1_ROOM_SENSOR,
                    default=current.get(CONF_HK1_ROOM_SENSOR, False),
                ): bool,
                vol.Required(
                    CONF_PV_SENSOR_MODULE,
                    default=current.get(CONF_PV_SENSOR_MODULE, False),
                ): bool,
                vol.Required(
                    CONF_DHW_HOLIDAY_DETECTION,
                    default=current.get(CONF_DHW_HOLIDAY_DETECTION, False),
                ): bool,
                vol.Required(
                    CONF_DHW_HOLIDAY_THRESHOLD,
                    default=current.get(CONF_DHW_HOLIDAY_THRESHOLD, DEFAULT_DHW_HOLIDAY_THRESHOLD),
                ): vol.All(vol.Coerce(float), vol.Range(min=0, max=60)),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
