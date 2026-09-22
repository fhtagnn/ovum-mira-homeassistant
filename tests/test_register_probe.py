import json
import struct
from unittest.mock import AsyncMock

import pytest

from scripts.probe_optional_registers import (
    AccessResult,
    ProbeResult,
    RegisterProbe,
    build_report,
    decode_bool,
    decode_float32,
    decode_s16,
    inspect_access,
    parse_login_code,
    run_probes,
    write_report,
)


def _float_words(value: float) -> list[int]:
    return list(struct.unpack(">HH", struct.pack(">f", value)))


def test_register_decoders():
    assert decode_s16([0x7FFF]) == 32767
    assert decode_s16([0xFFFF]) == -1
    assert decode_bool([0]) is False
    assert decode_bool([1]) is True
    assert decode_float32(_float_words(42.5)) == pytest.approx(42.5)


@pytest.mark.parametrize(
    ("decoder", "words"),
    [
        (decode_s16, []),
        (decode_s16, [0x10000]),
        (decode_bool, [2]),
        (decode_float32, [0]),
        (decode_float32, [0x7F80, 0]),
    ],
)
def test_register_decoders_reject_invalid_values(decoder, words):
    with pytest.raises(ValueError):
        decoder(words)


async def test_run_probes_continues_after_unsupported_register():
    first = RegisterProbe(10, "FIRST", "first", 1, decode_s16, {7: "seven"})
    second = RegisterProbe(20, "SECOND", "second", 1, decode_s16)
    third = RegisterProbe(30, "THIRD", "third", 1, decode_s16, {9: "nine"})
    unit = AsyncMock()
    unit.read_holding_registers.side_effect = ([7], OSError("unsupported"), [8])

    results = await run_probes(unit, (first, second, third))

    assert results[0].value == 7
    assert results[0].value_name == "seven"
    assert results[1].value is None
    assert results[1].error == "OSError: unsupported"
    assert results[2].value == 8
    assert results[2].value_name == "unknown"
    assert unit.read_holding_registers.await_count == 3


async def test_probe_retains_raw_words_on_decode_error():
    probe = RegisterProbe(10, "BOOL", "boolean", 1, decode_bool)
    unit = AsyncMock()
    unit.read_holding_registers.return_value = [2]

    (result,) = await run_probes(unit, (probe,))

    assert result.raw_words == [2]
    assert result.value is None
    assert result.error == "decode error: expected boolean value 0 or 1, got 2"


async def test_access_without_code_never_writes():
    unit = AsyncMock()
    unit.read_holding_registers.return_value = [0]

    result = await inspect_access(unit, None)

    assert result == AccessResult(0, 0, False, False, None)
    unit.write_registers.assert_not_awaited()


async def test_access_already_granted_never_rewrites_code():
    unit = AsyncMock()
    unit.read_holding_registers.return_value = [1]

    result = await inspect_access(unit, 1234)

    assert result == AccessResult(1, 1, True, False, None)
    unit.write_registers.assert_not_awaited()


async def test_explicit_login_uses_one_fc16_write_and_verifies_status():
    unit = AsyncMock()
    unit.read_holding_registers.side_effect = ([0], [1])

    result = await inspect_access(unit, 0x12345678)

    assert result == AccessResult(0, 1, True, True, None)
    unit.write_registers.assert_awaited_once_with(101, [0x1234, 0x5678])
    assert unit.read_holding_registers.await_args_list == [
        ((100, 1),),
        ((100, 1),),
    ]


async def test_explicit_login_can_proceed_when_initial_status_read_fails():
    unit = AsyncMock()
    unit.read_holding_registers.side_effect = (OSError("initial read"), [1])

    result = await inspect_access(unit, 1234)

    assert result == AccessResult(None, 1, True, True, None)
    unit.write_registers.assert_awaited_once_with(101, [0, 1234])


def test_report_excludes_connection_and_redacts_host(tmp_path):
    host = "192.0.2.10"
    access = AccessResult(None, None, False, False, f"cannot reach {host}")
    result = ProbeResult(
        55019,
        "WW_URLAUB",
        "candidate",
        None,
        None,
        None,
        f"connection to {host} failed",
        False,
    )

    report = build_report(
        label=f"normal at {host}",
        unit_id=110,
        access=access,
        results=[result],
        redactions=(host,),
    )
    output = tmp_path / "snapshot.json"
    write_report(output, report)
    serialized = output.read_text(encoding="utf-8")

    assert host not in serialized
    assert "login_code" not in serialized
    assert "<redacted>" in serialized
    assert json.loads(serialized)["unit_id"] == 110


@pytest.mark.parametrize("value", ["", "abc", str(2**31), str(-(2**31) - 1)])
def test_parse_login_code_rejects_invalid_values(value):
    with pytest.raises(ValueError):
        parse_login_code(value)


def test_parse_login_code_accepts_signed_32_bit_value():
    assert parse_login_code(" 1234 ") == 1234
