import json
import struct
from pathlib import Path

from custom_components.ovum_mira.const import INTEGRATION_VERSION

ROOT = Path(__file__).parents[1]


def _load_json(relative: str):
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def test_manifest_and_diagnostics_version_constant_match():
    manifest = _load_json("custom_components/ovum_mira/manifest.json")
    assert manifest["version"] == INTEGRATION_VERSION == "0.1.0"


def test_local_brand_images_have_expected_png_dimensions():
    expected_dimensions = {
        "icon.png": (256, 256),
        "icon@2x.png": (512, 512),
        "logo.png": (384, 256),
        "logo@2x.png": (768, 512),
    }

    for filename, dimensions in expected_dimensions.items():
        image = (ROOT / "custom_components/ovum_mira/brand" / filename).read_bytes()
        assert image.startswith(b"\x89PNG\r\n\x1a\n")
        assert image[12:16] == b"IHDR"
        assert struct.unpack(">II", image[16:24]) == dimensions
        assert image[25] == 6  # RGBA


def test_english_translation_is_canonical_strings_copy():
    strings = _load_json("custom_components/ovum_mira/strings.json")
    english = _load_json("custom_components/ovum_mira/translations/en.json")
    assert english == strings


def test_german_sensor_translation_covers_all_sensor_keys():
    strings = _load_json("custom_components/ovum_mira/strings.json")
    german = _load_json("custom_components/ovum_mira/translations/de.json")
    assert set(german["entity"]["sensor"]) == set(strings["entity"]["sensor"])


def test_holiday_options_have_english_and_german_help_text():
    keys = {"dhw_holiday_detection_enabled", "dhw_holiday_target_threshold"}
    for path in ["strings.json", "translations/en.json", "translations/de.json"]:
        step = _load_json(f"custom_components/ovum_mira/{path}")["options"]["step"]["init"]
        assert keys <= set(step["data"])
        assert keys <= set(step["data_description"])
