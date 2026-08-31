from collections.abc import Callable
from numbers import Real
from typing import TypeVar

T = TypeVar("T")


def range_validator(low: float, high: float, *, step: float | None = None) -> Callable[[T], T]:
    """Return a modbus-connection write validator with optional step snapping."""

    def validate(value: T) -> T:
        if not isinstance(value, Real):
            raise ValueError(f"{value!r} is not numeric")
        number = float(value)
        if not low <= number <= high:
            raise ValueError(f"{value} outside allowed range {low}..{high}")
        if step is not None:
            number = round(round((number - low) / step) * step + low, 6)
            if isinstance(value, int):
                return int(number)  # type: ignore[return-value]
            return number  # type: ignore[return-value]
        return value

    return validate


def snap_step(value: float, *, low: float, step: float) -> float:
    return round(round((value - low) / step) * step + low, 6)
