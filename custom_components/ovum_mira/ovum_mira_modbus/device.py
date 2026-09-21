from collections.abc import Sequence

from ..const import FIRST_WPM_UNIT, HSM_UNIT
from .config import InstallationOptions
from .hsm import OvumHsm
from .login import login_and_verify
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

    async def async_login(self, code: int) -> None:
        """Login separately to HSM and every WPM unit."""
        units = [(HSM_UNIT, self._hsm_unit)]
        units.extend(
            (FIRST_WPM_UNIT + index, unit)
            for index, unit in enumerate(self._wpm_units)
        )
        for unit_id, unit in units:
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

    async def async_setup(self) -> None:
        await self.hsm.async_setup()
        for wpm in self.wpms:
            await wpm.async_setup()

    async def async_update(self) -> None:
        await self.hsm.async_update()
        for wpm in self.wpms:
            await wpm.async_update()
