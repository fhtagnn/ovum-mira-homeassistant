from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.ovum_mira.ovum_mira_modbus.safe_write import write_if_changed


async def test_write_if_changed_skips_identical_value():
    component = SimpleNamespace(
        target=50.0,
        async_update=AsyncMock(),
        write=AsyncMock(),
        notify=MagicMock(),
    )

    changed = await write_if_changed(component, "target", 50.0)

    assert changed is False
    component.async_update.assert_awaited_once_with(notify=False)
    component.write.assert_not_awaited()
    component.notify.assert_not_called()


async def test_write_if_changed_normalizes_before_comparing():
    component = SimpleNamespace(
        target=51,
        async_update=AsyncMock(),
        write=AsyncMock(),
        notify=MagicMock(),
    )

    changed = await write_if_changed(component, "target", 50.6, normalize=round)

    assert changed is False
    component.write.assert_not_awaited()


async def test_write_if_changed_writes_verifies_and_notifies():
    component = SimpleNamespace(
        target=49.0,
        async_update=AsyncMock(),
        notify=MagicMock(),
    )

    async def write(field, value):
        setattr(component, field, value)

    component.write = AsyncMock(side_effect=write)

    changed = await write_if_changed(component, "target", 50.0)

    assert changed is True
    assert component.async_update.await_count == 2
    component.write.assert_awaited_once_with("target", 50.0)
    component.notify.assert_called_once_with()


async def test_write_if_changed_fails_when_readback_does_not_match():
    component = SimpleNamespace(
        target=49.0,
        async_update=AsyncMock(),
        write=AsyncMock(),
        notify=MagicMock(),
    )

    with pytest.raises(ValueError, match="write verification failed"):
        await write_if_changed(component, "target", 50.0)

    assert component.async_update.await_count == 2
    component.write.assert_awaited_once_with("target", 50.0)
    component.notify.assert_not_called()


async def test_write_if_changed_honors_float_tolerance():
    component = SimpleNamespace(
        target=20.00005,
        async_update=AsyncMock(),
        write=AsyncMock(),
        notify=MagicMock(),
    )

    changed = await write_if_changed(component, "target", 20.0, abs_tol=0.001)

    assert changed is False
    component.write.assert_not_awaited()
