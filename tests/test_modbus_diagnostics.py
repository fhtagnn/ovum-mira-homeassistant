from __future__ import annotations

from unittest.mock import AsyncMock, call

from custom_components.ovum_mira.ovum_mira_modbus.diagnostics import (
    RegisterDump,
    RegisterRange,
    async_read_holding_ranges,
)


def test_register_dump_serializes_to_plain_dict():
    dump = RegisterDump(name="status", address=56025, count=2, words=[4, 5])

    assert dump.as_dict() == {
        "name": "status",
        "address": 56025,
        "count": 2,
        "words": [4, 5],
    }


async def test_read_holding_ranges_preserves_range_metadata_and_words():
    unit = AsyncMock()
    unit.read_holding_registers.side_effect = [(1, 2), [3, 4, 5]]
    ranges = [
        RegisterRange("first", 100, 2),
        RegisterRange("second", 200, 3),
    ]

    result = await async_read_holding_ranges(unit, ranges)

    assert result == [
        RegisterDump("first", 100, 2, [1, 2]),
        RegisterDump("second", 200, 3, [3, 4, 5]),
    ]
    assert unit.read_holding_registers.await_args_list == [
        call(100, 2),
        call(200, 3),
    ]
