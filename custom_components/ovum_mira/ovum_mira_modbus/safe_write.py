from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any

from modbus_connection.model import Component


async def write_if_changed(
    component: Component,
    field: str,
    value: Any,
    *,
    normalize: Callable[[Any], Any] | None = None,
    verify: bool = True,
    abs_tol: float = 1e-4,
) -> bool:
    """Write a setting only if the decoded value actually changes.

    OVUM P_* values are persisted in flash and must never be rewritten cyclically.
    This helper therefore reads before writing and optionally verifies by readback.
    """

    requested = normalize(value) if normalize is not None else value
    await component.async_update(notify=False)
    current = getattr(component, field)

    if _same_value(current, requested, abs_tol=abs_tol):
        return False

    await component.write(field, requested)

    if verify:
        await component.async_update(notify=False)
        actual = getattr(component, field)
        if not _same_value(actual, requested, abs_tol=abs_tol):
            raise ValueError(
                f"OVUM write verification failed for {field}: "
                f"requested={requested!r}, read={actual!r}"
            )
    component.notify()
    return True


def _same_value(a: Any, b: Any, *, abs_tol: float) -> bool:
    if a is None:
        return False
    if isinstance(a, float) or isinstance(b, float):
        try:
            return math.isclose(float(a), float(b), rel_tol=0.0, abs_tol=abs_tol)
        except (TypeError, ValueError):
            return False
    return a == b
