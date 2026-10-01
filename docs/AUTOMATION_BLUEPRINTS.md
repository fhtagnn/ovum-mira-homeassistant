# Automation blueprints

The repository provides three optional Home Assistant automation blueprints.
Installing the integration does not create notifications or automations by
itself. Import a blueprint and create an automation from it only when the
corresponding behavior is wanted.

The blueprint entity selectors are intentionally restricted to entities
provided by the `ovum_mira` integration and to the semantic device class needed
by each input. Renaming an entity ID or reorganizing devices therefore does not
change the blueprint contract.

## System health notifications

[![Import the system-health blueprint into Home Assistant](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Ffhtagnn%2Fovum-mira-homeassistant%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fovum_mira%2Fsystem_health.yaml)

Monitors one installation-wide **Modbus communication** binary sensor and one
or more WPM **Problem** binary sensors.

- `fault` and `inverter_offline` are explicit problems and are reported.
- Normal operating states such as lockout, stopping, and defrost are not
  problems.
- Communication loss is reported only after the configured delay, which is
  five minutes by default.
- Optional recovery messages report when the fault or outage ends.
- A failed write while polling still succeeds is not classified as a
  communication outage. Home Assistant reports that failure on the initiating
  write action instead.
- The blueprint can create a persistent Home Assistant notification, send to
  selected `notify` entities, and execute optional additional actions.

The communication sensor intentionally remains available when polling fails:
its `off` state means that the last Modbus refresh failed. Its
`last_successful_update` attribute records the last successful refresh.

## Run start and end notifications

[![Import the run-cycle blueprint into Home Assistant](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Ffhtagnn%2Fovum-mira-homeassistant%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fovum_mira%2Frun_cycle.yaml)

Monitors the **Running** binary sensor of one WPM. The running state uses the
same cycle semantics as the integration's compressor-start statistics:

- start, domestic hot water, heating, cooling, automatic defrost, manual
  defrost, and stopping form one continuous observed run;
- internal transitions do not create additional start messages;
- a run shorter than the configurable minimum duration creates neither a start
  nor an end message;
- a WPM already running when Home Assistant starts does not create a false
  start message;
- an unavailable entity is not interpreted as a stopped heat pump.

The default minimum runtime is 30 seconds. Start and end messages can be enabled
independently.

## WPM status observer

[![Import the WPM-status blueprint into Home Assistant](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Ffhtagnn%2Fovum-mira-homeassistant%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fovum_mira%2Fstatus_observer.yaml)

Reports selected transitions of one WPM enum status sensor. It is intended for
commissioning, diagnostics, and users who deliberately want detailed operating
messages. It can be disabled after the observation period without affecting the
integration.

Unknown, unavailable, and initial startup states are ignored. Fault states can
be selected, but they are disabled in the default selection because the system
health blueprint handles them without duplicate messages.

## Notification outputs

Each blueprint supports English and German message text. It can send to one or
more modern Home Assistant `notify` entities. Optional additional actions cover
legacy notification actions, text-to-speech, lights, or any other action users
want to run.

Additional actions can reference the variables documented in the blueprint's
input description. All three provide `ovum_event`, `ovum_title`,
`ovum_message`, `ovum_source_entity`, and `ovum_status`; specialized blueprints
also expose their previous status or observed run duration.

## Manual import

If the buttons above are not available, open **Settings → Automations & scenes
→ Blueprints → Import blueprint** in Home Assistant and paste the corresponding
GitHub `source_url` from the YAML file.
