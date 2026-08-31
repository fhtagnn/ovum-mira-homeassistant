import json
from pathlib import Path

from custom_components.ovum_mira.const import INTEGRATION_VERSION

ROOT = Path(__file__).parents[1]


def _load_json(relative: str):
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def test_manifest_and_diagnostics_version_constant_match():
    manifest = _load_json("custom_components/ovum_mira/manifest.json")
    assert manifest["version"] == INTEGRATION_VERSION == "0.1.0-beta.2"


def test_english_translation_is_canonical_strings_copy():
    strings = _load_json("custom_components/ovum_mira/strings.json")
    english = _load_json("custom_components/ovum_mira/translations/en.json")
    assert english == strings


def test_german_sensor_translation_covers_all_sensor_keys():
    strings = _load_json("custom_components/ovum_mira/strings.json")
    german = _load_json("custom_components/ovum_mira/translations/de.json")
    assert set(german["entity"]["sensor"]) == set(strings["entity"]["sensor"])
