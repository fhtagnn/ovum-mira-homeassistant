"""Compatibility imports for supported Home Assistant test packages."""

try:
    from pytest_homeassistant.common import MockConfigEntry
except ModuleNotFoundError:
    from pytest_homeassistant_custom_component.common import MockConfigEntry

__all__ = ["MockConfigEntry"]
