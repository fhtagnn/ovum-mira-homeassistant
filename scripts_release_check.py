import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
errors: list[str] = []
manifest = json.loads((ROOT / "custom_components/ovum_mira/manifest.json").read_text())
required = {"domain", "name", "codeowners", "config_flow", "documentation", "issue_tracker", "integration_type", "iot_class", "requirements", "version"}
missing = required - manifest.keys()
if missing:
    errors.append(f"manifest missing keys: {sorted(missing)}")
for path in ["README.md", "LICENSE", "NOTICE", "hacs.json", "custom_components/ovum_mira/translations/en.json", "custom_components/ovum_mira/brand/icon.png"]:
    if not (ROOT / path).exists():
        errors.append(f"missing: {path}")
for p in ROOT.rglob("*"):
    if p.is_file() and p.suffix in {".py", ".md", ".json", ".yml", ".yaml"}:
        try:
            text = p.read_text(errors="ignore")
        except OSError:
            continue
        if p.name != "scripts_release_check.py" and "YOUR_GITHUB_USERNAME" in text:
            errors.append(f"maintainer placeholder remains: {p.relative_to(ROOT)}")
if errors:
    print("Release check FAILED")
    for e in errors:
        print(f"- {e}")
    sys.exit(1)
print("Release check passed")
