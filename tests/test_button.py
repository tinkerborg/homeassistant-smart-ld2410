"""Tests for the Smart LD2410 button platform."""

from __future__ import annotations

from typing import Any

import pytest
from bleak.exc import BleakError
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import ATTR_ENTITY_ID, CONF_ADDRESS
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.smart_ld2410.algo.types import GATE_COUNT, Frame
from custom_components.smart_ld2410.const import DOMAIN, PERMISSIVE_SENSITIVITY
from custom_components.smart_ld2410.coordinator import detector_mode

from .conftest import TEST_ADDRESS, FakeLD2410Client


async def _setup_entry(hass: HomeAssistant) -> tuple[MockConfigEntry, FakeLD2410Client]:
    """Add and set up a config entry, returning it and its fake BLE client."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="PRP1-RD_6615",
        data={CONF_ADDRESS: TEST_ADDRESS},
        unique_id=TEST_ADDRESS,
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED

    client = entry.runtime_data.client
    assert isinstance(client, FakeLD2410Client)
    return entry, client


def _entity_id(hass: HomeAssistant) -> str | None:
    registry = er.async_get(hass)
    return registry.async_get_entity_id(
        "button", DOMAIN, f"{TEST_ADDRESS}_set_permissive_thresholds"
    )


def _reset_entity_id(hass: HomeAssistant) -> str | None:
    registry = er.async_get(hass)
    return registry.async_get_entity_id(
        "button", DOMAIN, f"{TEST_ADDRESS}_reset_learning"
    )


def _frame(
    ts: float,
    *,
    move: dict[int, int] | None = None,
    still: dict[int, int] | None = None,
) -> Frame:
    """Build a Frame with all-zero gates except the ones overridden."""
    move = move or {}
    still = still or {}
    return Frame(
        ts_utc=ts,
        ts_mono=ts,
        move_gates=tuple(move.get(gate, 0) for gate in range(GATE_COUNT)),
        still_gates=tuple(still.get(gate, 0) for gate in range(GATE_COUNT)),
        target_distance_cm=150,
        device_occupancy=False,
    )


def _warmup_frames(start: float = 0.0, count: int = 7) -> list[Frame]:
    """Idle frames spanning enough 60s buckets for the baseline to go ready."""
    return [_frame(start + i * 60.0) for i in range(count)]


async def test_press_writes_permissive_thresholds_to_every_gate(
    hass: HomeAssistant,
) -> None:
    """Pressing the button writes the permissive constant to all 9 gates."""
    _entry, client = await _setup_entry(hass)
    entity_id = _entity_id(hass)
    assert entity_id is not None

    await hass.services.async_call(
        "button",
        "press",
        {ATTR_ENTITY_ID: entity_id},
        blocking=True,
    )
    await hass.async_block_till_done()

    assert len(client.set_gate_sensitivity_calls) == GATE_COUNT
    assert client.set_gate_sensitivity_calls == [
        (gate, PERMISSIVE_SENSITIVITY, PERMISSIVE_SENSITIVITY)
        for gate in range(GATE_COUNT)
    ]


async def test_press_failure_raises_home_assistant_error(hass: HomeAssistant) -> None:
    """A BLE command failure surfaces as a HomeAssistantError, not a raw exception."""
    _entry, client = await _setup_entry(hass)
    entity_id = _entity_id(hass)
    assert entity_id is not None

    client.command_error = BleakError("write failed")

    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            "button",
            "press",
            {ATTR_ENTITY_ID: entity_id},
            blocking=True,
        )
    await hass.async_block_till_done()


async def test_reset_learning_replaces_detector_and_clears_store(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    """Pressing reset swaps in a fresh detector and wipes the baseline store."""
    entry, client = await _setup_entry(hass)
    coordinator = entry.runtime_data.coordinator
    baseline_store = entry.runtime_data.baseline_store
    old_detector = coordinator.detector
    entity_id = _reset_entity_id(hass)
    assert entity_id is not None

    for frame in _warmup_frames():
        client.on_frame(frame)
    await hass.async_block_till_done()
    assert coordinator.detector.baseline.ready

    # Simulate the periodic save that would normally have persisted this
    # learned state by now.
    await baseline_store.async_save(coordinator.detector.state_to_dict())
    assert baseline_store.key in hass_storage

    await hass.services.async_call(
        "button",
        "press",
        {ATTR_ENTITY_ID: entity_id},
        blocking=True,
    )
    await hass.async_block_till_done()

    assert coordinator.detector is not old_detector
    assert not coordinator.detector.baseline.ready
    assert baseline_store.key not in hass_storage


async def test_reset_learning_returns_to_passthrough(hass: HomeAssistant) -> None:
    """After a reset, occupancy mode reads passthrough until warmup completes again."""
    entry, client = await _setup_entry(hass)
    coordinator = entry.runtime_data.coordinator
    entity_id = _reset_entity_id(hass)
    assert entity_id is not None

    for frame in _warmup_frames():
        client.on_frame(frame)
    await hass.async_block_till_done()
    assert detector_mode(coordinator.data) == "learned"

    await hass.services.async_call(
        "button",
        "press",
        {ATTR_ENTITY_ID: entity_id},
        blocking=True,
    )
    await hass.async_block_till_done()

    client.on_frame(_frame(0.0))
    await hass.async_block_till_done()
    assert detector_mode(coordinator.data) == "passthrough"


async def test_reset_learning_frames_keep_flowing_and_rewarm(
    hass: HomeAssistant,
) -> None:
    """Frames after a reset are still processed and warmup completes again."""
    entry, client = await _setup_entry(hass)
    coordinator = entry.runtime_data.coordinator
    entity_id = _reset_entity_id(hass)
    assert entity_id is not None

    for frame in _warmup_frames():
        client.on_frame(frame)
    await hass.async_block_till_done()

    await hass.services.async_call(
        "button",
        "press",
        {ATTR_ENTITY_ID: entity_id},
        blocking=True,
    )
    await hass.async_block_till_done()

    for frame in _warmup_frames(start=100_000.0):
        client.on_frame(frame)
    await hass.async_block_till_done()

    assert coordinator.detector.baseline.ready
    assert detector_mode(coordinator.data) == "learned"
