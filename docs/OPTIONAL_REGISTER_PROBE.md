# Optional register probe

This repository includes a standalone development script for validating candidate
OVUM MIRA registers before they are added to the Home Assistant integration. It
runs independently of Home Assistant and does not import the integration.

The candidate registers are read one at a time. An unsupported register therefore
produces an individual error without preventing the remaining reads. The script
never writes any candidate register.

## Safety and scope

- Run the script only against your own controller on a trusted local network.
- The default target is the HSM at Modbus Unit ID `110` and TCP port `502`.
- Without `--prompt-login-code`, the complete run is read-only.
- With `--prompt-login-code`, the code is entered without terminal echo. The
  script writes it only to the documented login registers `101/102`, in one FC16
  transaction, and verifies status register `100`. It does not put the code on
  the command line or into the JSON report.
- The script does not change Home Assistant configuration or integration data.
- A short-lived second Modbus connection is normally sufficient. If a controller
  permits only one client, it may reject the probe while Home Assistant is
  connected; do not repeatedly retry it during controller operations.

## Registers currently probed

| Address | Protocol name | Decode | Purpose |
|---:|---|---|---|
| 55004 | `WW_DESIREDTEMP` | big-endian float32 | Known effective DHW target used as a reference |
| 55012 | `WW_ANFSTATUS` | signed 16-bit enum | DHW request status |
| 55016 | `WW_ZIRKPUMP` | boolean | Circulation-pump status |
| 55017 | `WW_ZIRKT` | big-endian float32 | Circulation-pump temperature |
| 55019 | `WW_URLAUB` | signed 16-bit enum | Candidate DHW vacation flag |
| 55030 | `HPUF_LADESTATUS` | signed 16-bit enum | Heating-buffer loading status |
| 56154 | `HK1_URLAUB` | signed 16-bit enum | Candidate heating-circuit 1 vacation flag |
| 56179 | `HK2_URLAUB` | signed 16-bit enum | Candidate heating-circuit 2 vacation flag |

Some of these registers are documented for a higher MIRA license level or an
optional subsystem. A Modbus exception can therefore be a valid and useful test
result rather than a script defect.

## Setup

Use a computer with Python 3.14 and network access to MIRA. From a clone of this
repository:

```bash
python3.14 -m venv .venv-register-probe
. .venv-register-probe/bin/activate
python -m pip install "modbus-connection[tmodbus]==4.8.1"
```

Set the local controller address and take a first snapshot:

```bash
MIRA_CONTROLLER=192.168.1.50
python scripts/probe_optional_registers.py "$MIRA_CONTROLLER" \
  --label normal \
  --json ovum-registers-normal.json
```

Replace the example address with the actual local address. If the read requires
an authenticated Modbus session, add the hidden interactive prompt:

```bash
python scripts/probe_optional_registers.py "$MIRA_CONTROLLER" \
  --prompt-login-code \
  --label normal \
  --json ovum-registers-normal.json
```

Do not pass the login code as a shell argument. The script intentionally has no
option that would expose it in shell history or the process list.

## Vacation-mode test sequence

The most useful result is a set of three snapshots from the same system:

1. With vacation mode inactive, create `ovum-registers-normal.json`.
2. Enable vacation mode at the MIRA controller. Wait until the effective DHW
   target (`WW_DESIREDTEMP`) reflects the setback, then create:

   ```bash
   python scripts/probe_optional_registers.py "$MIRA_CONTROLLER" \
     --label holiday \
     --json ovum-registers-holiday.json
   ```

3. Disable vacation mode again. Wait until the normal effective DHW target has
   returned, then create:

   ```bash
   python scripts/probe_optional_registers.py "$MIRA_CONTROLLER" \
     --label after-holiday \
     --json ovum-registers-after-holiday.json
   ```

Interpret `WW_URLAUB` and the heating-circuit flags only together with the known
effective target and the actual controller state:

- A repeatable `0 → 1 → 0` transition is evidence that a register reports the
  active vacation state.
- A constant value may instead mean whether that subsystem *participates* in
  vacation mode. It must not be exposed as an active-state sensor without
  additional evidence.
- An illegal-address or other per-register exception means that the register is
  unavailable on the tested controller/firmware/license combination.

For the other candidates, capture relevant operating states where practical:
DHW demand types, circulation pump off/on, and buffer below/above its target.
Never force a heat-pump operating condition solely for this probe.

## Sharing results

The optional JSON output contains the UTC timestamp, label, Unit ID, login status,
raw register words, decoded values, and per-register errors. It deliberately omits
the controller host and login code. It still contains operational data from the
installation, so review it before attaching it to a public issue or pull request.
