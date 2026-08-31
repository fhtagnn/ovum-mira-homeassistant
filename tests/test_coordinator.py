from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.ovum_mira.coordinator import OvumMiraCoordinator


def _system(*, side_effect=None):
    return SimpleNamespace(
        wpms=[],
        async_update=AsyncMock(side_effect=side_effect),
    )


async def test_coordinator_update_refreshes_device_and_derived_data(hass):
    """Refresh the device once and update all derived state afterward."""
    system = _system()
    coordinator = OvumMiraCoordinator(hass, system, "entry-id")
    derived = MagicMock()
    coordinator._update_derived_data = derived

    assert await coordinator._async_update_data() is None

    system.async_update.assert_awaited_once_with()
    derived.assert_called_once_with()


async def test_coordinator_wraps_device_error_as_update_failed(hass):
    """Expose communication failures through DataUpdateCoordinator semantics."""
    system = _system(side_effect=OSError("offline"))
    coordinator = OvumMiraCoordinator(hass, system, "entry-id")
    derived = MagicMock()
    coordinator._update_derived_data = derived

    with pytest.raises(UpdateFailed, match="offline"):
        await coordinator._async_update_data()

    derived.assert_not_called()


async def test_coordinator_marks_failure_and_recovers_on_next_refresh(hass):
    """Become unavailable after a failed poll and recover after the next good poll."""
    system = _system(side_effect=[OSError("offline"), None])
    coordinator = OvumMiraCoordinator(hass, system, "entry-id")
    coordinator._update_derived_data = MagicMock()

    await coordinator.async_refresh()
    assert coordinator.last_update_success is False

    await coordinator.async_refresh()
    assert coordinator.last_update_success is True
    assert system.async_update.await_count == 2


async def test_coordinator_initialize_restores_all_persistent_state(hass):
    """Load history, analytics and energy state before deriving live values."""
    system = _system()
    coordinator = OvumMiraCoordinator(hass, system, "entry-id")

    history_load = AsyncMock()
    energy_initialize = AsyncMock()
    analytics_load = AsyncMock()
    maybe_sample = MagicMock()
    initialize_live_state = MagicMock()
    analytics_update = MagicMock()

    with (
        patch.object(coordinator.history, "async_load", new=history_load),
        patch.object(coordinator, "async_initialize_energy", new=energy_initialize),
        patch.object(coordinator.dhw_analytics, "async_load", new=analytics_load),
        patch.object(coordinator.history, "maybe_sample", new=maybe_sample),
        patch.object(
            coordinator.dhw_analytics,
            "initialize_live_state",
            new=initialize_live_state,
        ),
        patch.object(coordinator.dhw_analytics, "update", new=analytics_update),
    ):
        await coordinator.async_initialize()

    history_load.assert_awaited_once_with()
    analytics_load.assert_awaited_once_with()
    energy_initialize.assert_awaited_once_with()
    maybe_sample.assert_called_once_with(system)
    initialize_live_state.assert_called_once_with(system)
    analytics_update.assert_called_once_with(system, coordinator.history)


async def test_coordinator_save_persists_energy_history_and_analytics(hass):
    """Persist all derived state immediately during integration unload."""
    system = _system()
    coordinator = OvumMiraCoordinator(hass, system, "entry-id")

    save_energy = AsyncMock()
    save_history = AsyncMock()
    save_analytics = AsyncMock()

    with (
        patch.object(coordinator._store, "async_save", new=save_energy),
        patch.object(coordinator.history, "async_save", new=save_history),
        patch.object(coordinator.dhw_analytics, "async_save", new=save_analytics),
    ):
        await coordinator.async_save_persistent_state()

    save_energy.assert_awaited_once_with(coordinator.energy.as_storage_dict())
    save_history.assert_awaited_once_with()
    save_analytics.assert_awaited_once_with()
