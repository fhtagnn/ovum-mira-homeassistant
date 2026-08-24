# Analysis history and diagnostics export

The integration maintains a compact, synchronized analysis history for DHW-cycle and circulation-pump analysis.

The integration records one sample per minute and retains the most recent 14 days. The history is stored independently from Home Assistant Recorder so it remains available even if Recorder excludes one of the involved entities.

Each sample contains, when available:

- timestamp (UTC)
- MIRA outside temperature
- domestic-hot-water temperature
- effective DHW target temperature
- DHW main-switch state
- heating-buffer temperature
- per-WPM status, demand, electrical power, thermal power and condenser inlet/outlet temperatures

The data can be downloaded using Home Assistant's standard **Download diagnostics** action for the OVUM MIRA config entry. The Modbus login code is redacted from the export.

This history is intentionally compact rather than a complete copy of the Home Assistant Recorder database. Its purpose is reproducible analysis of DHW charging and circulation effects and local prediction of the next DHW cycle.

## Public-release privacy note

Diagnostics are intended for troubleshooting, but users should review exports before posting them publicly. The integration excludes the Modbus login code; operational time series can still reveal household usage patterns.
