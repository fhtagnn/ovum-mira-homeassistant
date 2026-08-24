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

Create a virtual environment and install the lightweight local test tools:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install pytest ruff
python -m pytest
ruff check .
```

For full Home Assistant integration tests, use a Home Assistant Core development
environment and install the custom component into the test configuration.

## Pull requests

Describe:

- the affected MIRA/controller version;
- relevant register addresses and data types;
- whether the change reads or writes the controller;
- how the behavior was tested;
- whether real-device testing was performed.

AI-assisted contributions are welcome. See `AI_POLICY.md`.
