#!/usr/bin/env python3
"""Read candidate OVUM MIRA registers without loading Home Assistant."""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from getpass import getpass
import json
import math
from pathlib import Path
import struct
import sys
from typing import Any

from modbus_connection import ModbusError, ModbusTcpParams
from modbus_connection.encode import encode_int32
from modbus_connection.tmodbus import ModbusConnection


DEFAULT_PORT = 502
DEFAULT_UNIT_ID = 110
LOGIN_STATUS_REGISTER = 100
LOGIN_CODE_REGISTER = 101

type Decoder = Callable[[Sequence[int]], int | float | bool]


@dataclass(frozen=True, slots=True)
class RegisterProbe:
    """Definition of one isolated holding-register read."""

    address: int
    name: str
    description: str
    word_count: int
    decoder: Decoder
    values: Mapping[int, str] | None = None
    reference: bool = False


@dataclass(frozen=True, slots=True)
class ProbeResult:
    """Raw and decoded result for one register probe."""

    address: int
    name: str
    description: str
    raw_words: list[int] | None
    value: int | float | bool | None
    value_name: str | None
    error: str | None
    reference: bool


@dataclass(frozen=True, slots=True)
class AccessResult:
    """Observed login state and any explicitly requested login attempt."""

    status_before: int | None
    status_after: int | None
    login_requested: bool
    login_written: bool
    error: str | None


def decode_s16(words: Sequence[int]) -> int:
    """Decode one big-endian signed 16-bit register."""
    _require_words(words, 1)
    word = words[0]
    _require_word(word)
    return word if word < 0x8000 else word - 0x10000


def decode_bool(words: Sequence[int]) -> bool:
    """Decode a strict OVUM boolean register."""
    value = decode_s16(words)
    if value not in (0, 1):
        raise ValueError(f"expected boolean value 0 or 1, got {value}")
    return bool(value)


def decode_float32(words: Sequence[int]) -> float:
    """Decode an OVUM big-endian IEEE-754 float from two registers."""
    _require_words(words, 2)
    for word in words:
        _require_word(word)
    value = struct.unpack(">f", struct.pack(">HH", words[0], words[1]))[0]
    if not math.isfinite(value):
        raise ValueError(f"expected a finite float, got {value}")
    return value


def _require_words(words: Sequence[int], expected: int) -> None:
    if len(words) != expected:
        raise ValueError(f"expected {expected} register word(s), got {len(words)}")


def _require_word(word: int) -> None:
    if not 0 <= word <= 0xFFFF:
        raise ValueError(f"register word outside u16 range: {word}")


HOT_WATER_REQUEST_VALUES = {
    0: "none",
    1: "plus",
    2: "photovoltaic",
    3: "legionella",
    4: "nominal",
    5: "turbo",
    6: "frost",
}

VACATION_VALUES = {0: "no", 1: "yes"}

BUFFER_LOADING_VALUES = {
    0: "below_frost",
    1: "below_switch_on",
    2: "below_target",
    3: "above_target",
    4: "above_switch_off",
    5: "no_buffer",
}

PROBES: tuple[RegisterProbe, ...] = (
    RegisterProbe(
        55004,
        "WW_DESIREDTEMP",
        "Effective DHW target (reference)",
        2,
        decode_float32,
        reference=True,
    ),
    RegisterProbe(
        55012,
        "WW_ANFSTATUS",
        "DHW request status",
        1,
        decode_s16,
        HOT_WATER_REQUEST_VALUES,
    ),
    RegisterProbe(
        55016,
        "WW_ZIRKPUMP",
        "DHW circulation-pump status",
        1,
        decode_bool,
    ),
    RegisterProbe(
        55017,
        "WW_ZIRKT",
        "DHW circulation-pump temperature",
        2,
        decode_float32,
    ),
    RegisterProbe(
        55019,
        "WW_URLAUB",
        "DHW vacation status candidate",
        1,
        decode_s16,
        VACATION_VALUES,
    ),
    RegisterProbe(
        55030,
        "HPUF_LADESTATUS",
        "Heating-buffer loading status",
        1,
        decode_s16,
        BUFFER_LOADING_VALUES,
    ),
    RegisterProbe(
        56154,
        "HK1_URLAUB",
        "Heating-circuit 1 vacation status candidate",
        1,
        decode_s16,
        VACATION_VALUES,
    ),
    RegisterProbe(
        56179,
        "HK2_URLAUB",
        "Heating-circuit 2 vacation status candidate",
        1,
        decode_s16,
        VACATION_VALUES,
    ),
)


def _error_text(error: BaseException) -> str:
    detail = str(error).strip()
    return type(error).__name__ if not detail else f"{type(error).__name__}: {detail}"


async def probe_register(unit: Any, probe: RegisterProbe) -> ProbeResult:
    """Read and decode one probe, retaining raw words on decode failures."""
    try:
        raw_words = list(
            await unit.read_holding_registers(probe.address, probe.word_count)
        )
    except (ModbusError, OSError, ValueError) as error:
        return ProbeResult(
            probe.address,
            probe.name,
            probe.description,
            None,
            None,
            None,
            _error_text(error),
            probe.reference,
        )

    try:
        value = probe.decoder(raw_words)
    except (struct.error, ValueError) as error:
        return ProbeResult(
            probe.address,
            probe.name,
            probe.description,
            raw_words,
            None,
            None,
            f"decode error: {error}",
            probe.reference,
        )

    value_name = None
    if probe.values is not None and isinstance(value, int):
        value_name = probe.values.get(value, "unknown")
    return ProbeResult(
        probe.address,
        probe.name,
        probe.description,
        raw_words,
        value,
        value_name,
        None,
        probe.reference,
    )


async def run_probes(
    unit: Any,
    probes: Sequence[RegisterProbe] = PROBES,
) -> list[ProbeResult]:
    """Run isolated reads so one unsupported register does not stop the probe."""
    return [await probe_register(unit, probe) for probe in probes]


async def inspect_access(unit: Any, login_code: int | None) -> AccessResult:
    """Read access status and write only the explicitly supplied login code."""
    before: int | None = None
    before_error: str | None = None
    try:
        before_words = await unit.read_holding_registers(LOGIN_STATUS_REGISTER, 1)
        before = decode_s16(before_words)
    except (ModbusError, OSError, ValueError) as error:
        before_error = _error_text(error)

    if login_code is None or before == 1:
        return AccessResult(
            status_before=before,
            status_after=before,
            login_requested=login_code is not None,
            login_written=False,
            error=before_error,
        )

    try:
        await unit.write_registers(LOGIN_CODE_REGISTER, encode_int32(login_code))
        after_words = await unit.read_holding_registers(LOGIN_STATUS_REGISTER, 1)
        after = decode_s16(after_words)
    except (ModbusError, OSError, ValueError) as error:
        return AccessResult(
            status_before=before,
            status_after=None,
            login_requested=True,
            login_written=True,
            error=_error_text(error),
        )

    error = None if after == 1 else "OVUM MIRA rejected the login code"
    return AccessResult(
        status_before=before,
        status_after=after,
        login_requested=True,
        login_written=True,
        error=error,
    )


def build_report(
    *,
    label: str | None,
    unit_id: int,
    access: AccessResult,
    results: Sequence[ProbeResult],
    captured_at: datetime | None = None,
    redactions: Sequence[str] = (),
) -> dict[str, Any]:
    """Build a shareable report without connection host or credentials."""
    timestamp = captured_at or datetime.now(UTC)
    report = {
        "schema_version": 1,
        "captured_at": timestamp.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        "label": label,
        "unit_id": unit_id,
        "access": asdict(access),
        "registers": [asdict(result) for result in results],
    }
    return _redact_report(report, redactions)


def _redact_report(value: Any, redactions: Sequence[str]) -> Any:
    """Remove explicitly sensitive strings from nested report values."""
    if isinstance(value, dict):
        return {key: _redact_report(item, redactions) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact_report(item, redactions) for item in value]
    if isinstance(value, str):
        for sensitive in redactions:
            if sensitive:
                value = value.replace(sensitive, "<redacted>")
    return value


def write_report(path: Path, report: Mapping[str, Any]) -> None:
    """Write one formatted JSON snapshot."""
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def print_access(access: AccessResult) -> None:
    """Print access information without exposing a login code."""
    before = "unknown" if access.status_before is None else str(access.status_before)
    after = "unknown" if access.status_after is None else str(access.status_after)
    print(f"Access status: before={before}, after={after}")
    if access.login_written:
        print("Login code was written once to registers 101/102 using FC16.")
    elif access.login_requested:
        print("Login was requested, but no write was needed.")
    else:
        print("No login write was requested.")
    if access.error:
        print(f"Access warning: {access.error}")


def print_results(results: Sequence[ProbeResult]) -> None:
    """Print readable probe output."""
    print("\nRegister results:")
    for result in results:
        prefix = "reference" if result.reference else "candidate"
        if result.error:
            raw = "" if result.raw_words is None else f" raw={result.raw_words}"
            print(
                f"- {result.address} {result.name} [{prefix}]: ERROR "
                f"{result.error}{raw}"
            )
            continue
        value = repr(result.value)
        if result.value_name is not None:
            value = f"{value} ({result.value_name})"
        print(
            f"- {result.address} {result.name} [{prefix}]: "
            f"raw={result.raw_words} value={value}"
        )


def parse_login_code(value: str) -> int:
    """Parse a signed 32-bit login code entered through a hidden prompt."""
    try:
        code = int(value.strip())
    except ValueError as error:
        raise ValueError("login code must be an integer") from error
    if not -(2**31) <= code < 2**31:
        raise ValueError("login code must fit into a signed 32-bit value")
    return code


def positive_port(value: str) -> int:
    """Validate a TCP port for argparse."""
    port = int(value)
    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError("port must be between 1 and 65535")
    return port


def unit_id(value: str) -> int:
    """Validate a Modbus Unit ID for argparse."""
    parsed = int(value)
    if not 1 <= parsed <= 247:
        raise argparse.ArgumentTypeError("unit ID must be between 1 and 247")
    return parsed


def create_parser() -> argparse.ArgumentParser:
    """Create the command-line parser."""
    parser = argparse.ArgumentParser(
        description=(
            "Read optional OVUM MIRA HSM registers individually. Candidate "
            "registers are never written."
        )
    )
    parser.add_argument("host", help="MIRA hostname or local IP address")
    parser.add_argument("--port", type=positive_port, default=DEFAULT_PORT)
    parser.add_argument(
        "--unit-id",
        type=unit_id,
        default=DEFAULT_UNIT_ID,
        help="HSM Modbus Unit ID (default: 110)",
    )
    parser.add_argument(
        "--prompt-login-code",
        action="store_true",
        help=(
            "securely prompt for a login code and, only if status 100 is not "
            "already granted, write it once to registers 101/102"
        ),
    )
    parser.add_argument(
        "--label",
        help="snapshot label such as normal, holiday, or after-holiday",
    )
    parser.add_argument(
        "--json",
        type=Path,
        metavar="PATH",
        help="write a shareable JSON snapshot without host or login code",
    )
    return parser


async def async_main(args: argparse.Namespace, login_code: int | None) -> int:
    """Connect, optionally authenticate, and run the read-only probes."""
    connection = ModbusConnection(ModbusTcpParams(host=args.host, port=args.port))
    try:
        unit = connection.for_unit(args.unit_id)
        access = await inspect_access(unit, login_code)
        results = await run_probes(unit)
    finally:
        await connection.close()

    print_access(access)
    print_results(results)

    if args.json is not None:
        report = build_report(
            label=args.label,
            unit_id=args.unit_id,
            access=access,
            results=results,
            redactions=(args.host,),
        )
        write_report(args.json, report)
        print(f"\nJSON snapshot written to {args.json}")
        print("Review operational values before sharing the file publicly.")

    successful = sum(result.error is None for result in results)
    print(f"\nCompleted: {successful}/{len(results)} registers decoded.")
    return 0 if successful else 1


def main() -> int:
    """Run the command-line interface."""
    args = create_parser().parse_args()
    login_code = None
    if args.prompt_login_code:
        try:
            login_code = parse_login_code(getpass("MIRA Modbus login code: "))
        except ValueError as error:
            print(f"Invalid login code: {error}", file=sys.stderr)
            return 2

    try:
        return asyncio.run(async_main(args, login_code))
    except (ModbusError, OSError, ValueError) as error:
        print(f"Probe failed: {_error_text(error)}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
