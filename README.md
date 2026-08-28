# OVUM MIRA for Home Assistant

Community Home Assistant integration for OVUM heat pumps using the MIRA controller and Modbus TCP.

> **Release status:** The `0.1.0` beta series is intended for testing by additional OVUM users before the first public stable release.

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
- Operating-mode energy and work factors for domestic hot water and heating
- Compressor cycling metrics and average completed-cycle runtime
- DHW start detection, average heating interval, and diagnostic median interval
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

## Connection parameters

The initial setup asks for the values needed to reach the existing MIRA installation:

- **Host / IP address** — hostname or local IP address of the MIRA controller.
- **Port** — Modbus TCP port. MIRA normally uses port `502`.
- **Number of WPM units** — number of installed WPM units from `1` to `8`. WPM 1 uses Unit ID 111 and additional WPMs use the following Unit IDs up to 118.
- **Modbus login code** — optional numeric login configured on MIRA. Leave the field empty when Modbus login is disabled on the controller.

The connection is tested before the config entry is created. Later changes to host, port, or WPM count should be made with Home Assistant's **Reconfigure** flow. When authentication fails, use the **Reauthenticate** flow to replace the login code. Both flows keep the existing config entry and therefore preserve the integration's data association.

## Installation options

Physical installation details that cannot be inferred safely from register values are stored as Home Assistant config-entry options and can be changed later from the integration options flow:

- **Heating-buffer sensor count** — choose `1` or `2` according to the temperature sensors physically installed. The upper-buffer-temperature entity is exposed only for a two-sensor setup.
- **Domestic-hot-water sensor count** — choose `1` or `2`. With one sensor, the MIRA `WW_ACTUALTEMPO` input is used as the primary DHW temperature; with two sensors, the additional lower-temperature value is exposed separately.
- **Heating circuit 1 room sensor** — enable only when a real MIRA room-temperature sensor is installed. When enabled, Home Assistant can expose a room climate entity; without it, the circuit water temperature is not presented as room temperature.
- **PV sensor module installed** — enable when the optional MIRA PV sensor module is physically present. PV parameter entities are still disabled by default and can be enabled individually when needed.

Changing these installation options reloads the config entry but does not create a new one.

## Persistent parameter writes

MIRA parameter types prefixed with `P_` are persistent controller parameters. The integration writes them only when the requested value differs from the current value and performs read-back verification. They are never intentionally rewritten on every polling cycle.

Write failures from Home Assistant entity actions are reported to the user rather than silently ignored.

## Energy, efficiency, and cycling

The integration integrates reported electrical and thermal power over time to produce kWh sensors. It also provides instantaneous COP and accumulated work-factor values. Communication gaps longer than two minutes are not backfilled using stale power values.

Energy is additionally classified into domestic-hot-water, heating, cooling, and unclassified/other buckets from WPM operating-state transitions. Domestic-hot-water and heating mode-energy/work-factor sensors are enabled by default. Cooling metrics are initially disabled by default; ambiguous or unreconstructable energy stays explicitly unclassified rather than being guessed.

Compressor starts are derived conservatively from observed inactive-to-active state transitions. Internal active-state changes, including normal defrost within one run, do not count as new starts. A Home Assistant restart while the compressor is already active establishes a baseline and does not invent a start.

Thermal power reported by MIRA is not a calibrated heat meter, so derived thermal energy and work-factor values are suitable for monitoring and optimization rather than billing.

## DHW analytics

A DHW heating start is detected when a WPM enters the MIRA `HOT_WATER` status. The integration stores recent observed start temperatures and estimates the typical trigger temperature.

It also derives the average interval between recent valid DHW starts. Intervals below 2 hours, above 72 hours, or crossing an analysis-history gap longer than 2 minutes are excluded. The normal sensor uses the arithmetic mean of up to 10 valid intervals; a median interval is available as a diagnostic entity.

While DHW heating is inactive, the integration calculates the current cooling slope from recent synchronized temperature samples and linearly extrapolates when the observed trigger temperature will be reached. This produces a transparent estimate of the next DHW heating start and can help evaluate circulation-pump behavior.

The analytics are informational only and are not used to control the heat pump.

## Diagnostics and privacy

Home Assistant's standard diagnostics export contains controller state and a compact synchronized analysis history. Credentials such as the Modbus login code are excluded. Review diagnostics before sharing them publicly because they may still reveal details about your home's operation.

## Updating and removing the integration

For updates, keep the existing OVUM MIRA config entry and update the custom integration in place. Do **not** delete and recreate the config entry merely to install a new version. The integration's energy, analysis-history, and DHW-analytics stores are associated with Home Assistant's config-entry ID; a newly created entry receives a different ID and will not automatically attach itself to the previous stores. See [Upgrade and data compatibility](docs/UPGRADES.md) for the supported migration path.

To permanently remove the integration, open **Settings → Devices & services**, select **OVUM MIRA**, and remove its config entry. Then uninstall the custom integration from HACS, or remove `/config/custom_components/ovum_mira/` for a manual installation, and restart Home Assistant if required. Take a Home Assistant backup first if historical data or the integration-managed stores may be needed later. Reinstalling as a new config entry is not a supported method for reconnecting old integration-managed storage.

## Documentation

Additional technical notes are included in:

- [Energy and efficiency statistics](docs/ENERGY_STATISTICS.md)
- [DHW analytics](docs/DHW_ANALYTICS.md)
- [Analysis history and diagnostics export](docs/ANALYSIS_EXPORT.md)
- [Upgrade and data compatibility](docs/UPGRADES.md)
- [Release setup notes](docs/RELEASE_SETUP.md)
- [Contributing](CONTRIBUTING.md)
- [AI-assisted development policy](AI_POLICY.md)

Original OVUM protocol PDFs/XLS files are intentionally **not distributed** by this repository.

## AI-assisted development

Development of this project has been **AI-assisted using OpenAI ChatGPT**, including help with implementation, tests, documentation, and review. A human maintainer reviews changes and is responsible for release decisions and published code. See `AI_POLICY.md` for the project policy.

## License

Licensed under the Apache License 2.0. See `LICENSE` and `NOTICE`.
