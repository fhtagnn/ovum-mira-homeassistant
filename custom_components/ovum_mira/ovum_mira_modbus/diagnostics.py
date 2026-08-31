from dataclasses import asdict, dataclass
from typing import Any, Iterable


@dataclass(frozen=True, slots=True)
class RegisterRange:
    """A named read-only holding-register range for diagnostics."""

    name: str
    address: int
    count: int


@dataclass(frozen=True, slots=True)
class RegisterDump:
    """Raw words returned for one diagnostic range."""

    name: str
    address: int
    count: int
    words: list[int]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


async def async_read_holding_ranges(unit, ranges: Iterable[RegisterRange]) -> list[RegisterDump]:
    """Read selected raw holding-register ranges without writing anything."""

    result: list[RegisterDump] = []
    for item in ranges:
        words = await unit.read_holding_registers(item.address, item.count)
        result.append(
            RegisterDump(
                name=item.name,
                address=item.address,
                count=item.count,
                words=list(words),
            )
        )
    return result
