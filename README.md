# OVUM MIRA for Home Assistant

Community Home Assistant integration for OVUM heat pumps using the MIRA controller and Modbus TCP.

> **Release status:** `v0.1.0-beta.1` is a public beta intended for testing by additional OVUM users before the first public stable release.

## Disclaimer

This is an independent community project. It is **not affiliated with, maintained by, sponsored by, or endorsed by OVUM Heiztechnik GmbH**. OVUM and MIRA product names are used only to identify compatible equipment.

The integration can change heat-pump settings. Review your installation and controller documentation before enabling writable entities. Thermal-energy values derived from MIRA power data are intended for monitoring and are not metering-grade.

## Tested environment

- Home Assistant 2026.8.x
- MIRA 1.16
- Modbus TCP
- HSM Unit ID 110
- WPM Unit IDs 111–118 (WPM 1 starts at 111)

Other compatible MIRA 1.1.x systems may work, but should be treated as unverified until reported by users.

## Features

- Local Modbus TCP communication; no cloud service required
- Automatic detection of domestic hot water, heating buffer, and heating circuits
- Optional one-/two-sensor DHW and heating-buffer configuration
- Multiple WPM support
- Domestic-hot-water control and main switch
- Heating-circuit operating mode and room target controls
- Temperature, power, status, runtime, and diagnostic sensors
- Derived electrical and thermal energy statistics
- COP / work-factor monitoring
- DHW start detection from WPM status
- Transparent linear prediction of the next DHW heating start
- Home Assistant diagnostics with synchronized analysis history
- Safe change-only writes for persistent MIRA `P_*` parameters

## Installation

### HACS custom repository

Until the project is accepted into the HACS default list:

1. Open HACS.
2. Open **Custom repositories**.
3. Add `https://github.com/fhtagnn/ovum-mira-homeassistant` as an **Integration**.
4. Install **OVUM MIRA**.
5. Restart Home Assistant.
6. Add **OVUM MIRA** under **Settings → Devices & services**.

### Manual installation

Copy `custom_components/ovum_mira` into your Home Assistant configuration directory:

```text
/config/custom_components/ovum_mira/
```

Restart Home Assistant and add the integration from **Settings → Devices & services**.

## MIRA preparation

Enable Modbus TCP on the MIRA controller and note whether a Modbus login code is configured. The integration supports a login code, but it can also connect when login is disabled.

Do not expose Modbus TCP directly to the internet. Keep the controller on a trusted local network.

## Installation options

The setup flow asks for physical installation details that cannot always be inferred safely from register values, including:

- number of heating-buffer sensors;
- number of DHW sensors;
- presence of a room sensor for heating circuit 1;
- presence of the optional PV sensor module;
- number of WPM units.

## Persistent parameter writes

MIRA parameter types prefixed with `P_` are persistent controller parameters. The integration writes them only when the requested value differs from the current value and performs read-back verification. They are never intentionally rewritten on every polling cycle.

## Energy and COP

The integration integrates reported electrical and thermal power over time to produce kWh sensors. It also provides instantaneous COP and accumulated work-factor values. Communication gaps are not backfilled using stale power values.

Thermal power reported by MIRA is not a calibrated heat meter, so derived thermal energy and work-factor values are suitable for monitoring and optimization rather than billing.

## DHW analytics

A DHW heating start is detected when a WPM enters the MIRA `HOT_WATER` status. The integration stores recent observed start temperatures and estimates the typical trigger temperature.

While DHW heating is inactive, it calculates the current cooling slope from recent synchronized temperature samples and linearly extrapolates when the observed trigger temperature will be reached. This produces a transparent estimate of the next DHW heating start and can help evaluate circulation-pump behavior.

The prediction is informational only and is not used to control the heat pump.

## Diagnostics and privacy

Home Assistant's standard diagnostics export contains controller state and a compact synchronized analysis history. Credentials such as the Modbus login code are excluded. Review diagnostics before sharing them publicly because they may still reveal details about your home's operation.

## Documentation

Additional technical notes are included in:

- `ENERGY_STATISTICS.md`
- `DHW_ANALYTICS.md`
- `ANALYSIS_EXPORT.md`
- `CONTRIBUTING.md`
- `AI_POLICY.md`

Original OVUM protocol PDFs/XLS files are intentionally **not distributed** by this repository.

## AI-assisted development

Development of this project has been **AI-assisted using OpenAI ChatGPT**, including help with implementation, tests, documentation, and review. A human maintainer reviews changes and is responsible for release decisions and published code. See `AI_POLICY.md` for the project policy.

## License

Licensed under the Apache License 2.0. See `LICENSE` and `NOTICE`.
