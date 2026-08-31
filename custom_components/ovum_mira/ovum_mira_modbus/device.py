from collections.abc import Sequence

from .config import InstallationOptions
from .hsm import OvumHsm
from .login import login_and_verify
from .wpm import OvumWpm


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
        await login_and_verify(self._hsm_unit, code)
        for unit in self._wpm_units:
            await login_and_verify(unit, code)

    async def async_setup(self) -> None:
        await self.hsm.async_setup()
        for wpm in self.wpms:
            await wpm.async_setup()

    async def async_update(self) -> None:
        await self.hsm.async_update()
        for wpm in self.wpms:
            await wpm.async_update()
