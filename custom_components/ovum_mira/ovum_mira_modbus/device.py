from collections.abc import Sequence

from ..const import FIRST_WPM_UNIT, HSM_UNIT
from .config import InstallationOptions
from .hsm import OvumHsm
from .login import is_login_granted, login_and_verify
from .wpm import OvumWpm


class LoginConnectionError(OSError):
    """Raised when communication fails during login for a specific unit."""


class OvumMiraSystem:
    """One MIRA installation: HSM plus one or more WPM units."""

    def __init__(
        self,
        hsm_unit,
        wpm_units: Sequence,
        *,
        options: InstallationOptions | None = None,
    ) -> None:
        if not wpm_units:
            raise ValueError("At least WPM1 must be supplied")
        self.hsm = OvumHsm(hsm_unit, options=options)
        self.wpms = [OvumWpm(unit) for unit in wpm_units]
        self._hsm_unit = hsm_unit
        self._wpm_units = list(wpm_units)
        self._login_code: int | None = None

    def _login_units(self):
        """Yield configured unit IDs and connections in login order."""
        yield HSM_UNIT, self._hsm_unit
        for index, unit in enumerate(self._wpm_units):
            yield FIRST_WPM_UNIT + index, unit

    @staticmethod
    async def _async_login_unit(unit_id: int, unit, code: int) -> None:
        """Authenticate one unit and add its ID to any resulting error."""
        try:
            await login_and_verify(unit, code)
        except PermissionError as err:
            raise PermissionError(
                f"OVUM MIRA Modbus login rejected by Unit ID {unit_id}"
            ) from err
        except Exception as err:
            raise LoginConnectionError(
                f"OVUM MIRA Modbus login communication failed for Unit ID {unit_id}"
            ) from err

    async def async_login(self, code: int) -> None:
        """Login separately to HSM and every WPM unit."""
        for unit_id, unit in self._login_units():
            await self._async_login_unit(unit_id, unit, code)
        self._login_code = code

    async def async_ensure_login(self) -> None:
        """Renew expired authenticated access before a controller write."""
        if self._login_code is None:
            return

        for unit_id, unit in self._login_units():
            try:
                granted = await is_login_granted(unit)
            except Exception as err:
                raise LoginConnectionError(
                    f"Unable to check OVUM MIRA Modbus login for Unit ID {unit_id}"
                ) from err

            if not granted:
                await self._async_login_unit(unit_id, unit, self._login_code)

    async def async_setup(self) -> None:
        await self.hsm.async_setup()
        for wpm in self.wpms:
            await wpm.async_setup()

    async def async_update(self) -> None:
        await self.hsm.async_update()
        for wpm in self.wpms:
            await wpm.async_update()
