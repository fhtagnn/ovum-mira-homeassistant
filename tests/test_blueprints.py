from pathlib import Path

import yaml
from homeassistant.components.automation.config import (
    AUTOMATION_BLUEPRINT_SCHEMA,
    async_validate_config_item,
)
from homeassistant.components.blueprint.models import Blueprint, BlueprintInputs
from homeassistant.helpers.template import Template
from homeassistant.util import yaml as yaml_util

from custom_components.ovum_mira.ovum_mira_modbus import WpmStatus

ROOT = Path(__file__).parents[1]
BLUEPRINT_DIR = ROOT / "blueprints" / "automation" / "ovum_mira"


class _BlueprintLoader(yaml.SafeLoader):
    pass


_BlueprintLoader.add_constructor(
    "!input",
    lambda loader, node: {"blueprint_input": loader.construct_scalar(node)},
)


def _load(name: str):
    return yaml.load(
        (BLUEPRINT_DIR / name).read_text(encoding="utf-8"),
        Loader=_BlueprintLoader,
    )


def _entity_filter(blueprint: dict, input_name: str):
    return blueprint["blueprint"]["input"][input_name]["selector"]["entity"]


def test_all_blueprints_parse_and_declare_stable_metadata():
    expected = {"system_health.yaml", "run_cycle.yaml", "status_observer.yaml"}
    assert {path.name for path in BLUEPRINT_DIR.glob("*.yaml")} == expected

    for filename in expected:
        blueprint = _load(filename)
        metadata = blueprint["blueprint"]
        assert metadata["domain"] == "automation"
        assert metadata["homeassistant"]["min_version"] == "2026.8.0"
        assert metadata["source_url"].endswith(
            f"/blueprints/automation/ovum_mira/{filename}"
        )
        assert blueprint["triggers"]
        assert blueprint["actions"]


def test_health_blueprint_only_selects_ovum_health_entities():
    blueprint = _load("system_health.yaml")

    communication = _entity_filter(blueprint, "communication_sensor")
    assert communication["filter"] == [
        {
            "integration": "ovum_mira",
            "domain": "binary_sensor",
            "device_class": "connectivity",
        }
    ]

    problems = _entity_filter(blueprint, "problem_sensors")
    assert problems["multiple"] is True
    assert problems["filter"] == [
        {
            "integration": "ovum_mira",
            "domain": "binary_sensor",
            "device_class": "problem",
        }
    ]


def test_run_blueprint_only_selects_ovum_running_entities():
    blueprint = _load("run_cycle.yaml")
    running = _entity_filter(blueprint, "running_sensor")
    assert running["filter"] == [
        {
            "integration": "ovum_mira",
            "domain": "binary_sensor",
            "device_class": "running",
        }
    ]


def test_status_blueprint_only_selects_ovum_enum_and_lists_every_status():
    blueprint = _load("status_observer.yaml")
    status = _entity_filter(blueprint, "status_sensor")
    assert status["filter"] == [
        {
            "integration": "ovum_mira",
            "domain": "sensor",
            "device_class": "enum",
        }
    ]

    options = blueprint["blueprint"]["input"]["reported_states"]["selector"][
        "select"
    ]["options"]
    assert {option["value"] for option in options} == {
        status.name.lower() for status in WpmStatus
    }


def test_notification_selectors_only_offer_notify_entities():
    for filename in ("system_health.yaml", "run_cycle.yaml", "status_observer.yaml"):
        blueprint = _load(filename)
        notifications = _entity_filter(blueprint, "notification_targets")
        assert notifications["multiple"] is True
        assert notifications["filter"] == [{"domain": "notify"}]


async def test_blueprints_substitute_and_validate_as_automations(hass):
    required_inputs = {
        "system_health.yaml": {
            "communication_sensor": "binary_sensor.ovum_modbus_communication",
            "problem_sensors": ["binary_sensor.ovum_wpm_1_problem"],
        },
        "run_cycle.yaml": {
            "running_sensor": "binary_sensor.ovum_wpm_1_running",
        },
        "status_observer.yaml": {
            "status_sensor": "sensor.ovum_wpm_1_status",
        },
    }

    for filename, inputs in required_inputs.items():
        path = BLUEPRINT_DIR / filename
        blueprint = Blueprint(
            yaml_util.load_yaml(path),
            path=str(path),
            expected_domain="automation",
            schema=AUTOMATION_BLUEPRINT_SCHEMA,
        )
        configured = BlueprintInputs(
            blueprint,
            {
                "use_blueprint": {
                    "path": str(path),
                    "input": inputs,
                }
            },
        )
        configured.validate()

        validated = await async_validate_config_item(
            hass,
            filename,
            configured.async_substitute(),
        )
        assert validated is not None


async def test_health_communication_template_tracks_selected_entity(hass):
    blueprint = _load("system_health.yaml")
    template_source = next(
        trigger["value_template"]
        for trigger in blueprint["triggers"]
        if trigger["id"] == "communication_lost"
    )
    template = Template(template_source, hass)
    variables = {
        "communication_sensor_for_trigger": "binary_sensor.ovum_communication",
        "communication_delay_for_trigger": {
            "hours": 0,
            "minutes": 0,
            "seconds": 0,
        },
    }

    hass.states.async_set("binary_sensor.ovum_communication", "off")
    assert template.async_render(variables, parse_result=True) is True

    hass.states.async_set("binary_sensor.ovum_communication", "on")
    assert template.async_render(variables, parse_result=True) is False
