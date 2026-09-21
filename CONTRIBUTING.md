# Contributing

Thanks for helping improve OVUM MIRA support for Home Assistant.

## Ground rules

1. Keep protocol behavior explicit and testable.
2. Do not add periodic writes to persistent OVUM `P_*` parameters.
3. Prefer Home Assistant native entity semantics over exposing raw registers.
4. New optional hardware must be capability-detected or explicitly configured.
5. Never include proprietary OVUM PDFs/XLS files in commits unless redistribution
   permission is documented.
6. Add or update tests for behavior changes.

## Development

Use Python 3.14, create a virtual environment, and install the same pinned test
dependencies used by CI:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-test.txt
python -m compileall -q custom_components/ovum_mira
python -m pytest -q --cov=custom_components.ovum_mira --cov-report=term-missing
ruff check .
python scripts_release_check.py
```

The repository tests use `pytest-homeassistant-custom-component`. For additional
interactive testing, install the custom component in a separate Home Assistant
test instance; do not develop against a production heat-pump installation.

## Pull requests

Describe:

- the affected MIRA/controller version;
- relevant register addresses and data types;
- whether the change reads or writes the controller;
- how the behavior was tested;
- whether real-device testing was performed.

AI-assisted contributions are welcome. See `AI_POLICY.md`.
