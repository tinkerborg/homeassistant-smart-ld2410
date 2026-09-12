"""Tests for Smart LD2410 setup, wiring, entities, and options updates."""

from __future__ import annotations

import asyncio
import sqlite3
import threading
from unittest.mock import patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.smart_ld2410.algo.types import (
    GATE_COUNT,
    DetectorConfig,
    Frame,
)
from custom_components.smart_ld2410.const import DOMAIN

from .conftest import TEST_ADDRESS, FakeLD2410Client

ENTITY_KEYS = (
    ("binary_sensor", "occupancy"),
    ("binary_sensor", "adaptation_frozen"),
    ("sensor", "confidence"),
    ("sensor", "active_gate_range"),
    ("sensor", "target_distance"),
    ("sensor", "baseline_age"),
    ("sensor", "gate_classes"),
    *(("sensor", f"residual_move_{gate}") for gate in range(GATE_COUNT)),
    *(("sensor", f"residual_still_{gate}") for gate in range(GATE_COUNT)),
)


_ARRIVAL_FRAMES = DetectorConfig().arrival_min_frames
"""Frames of arrival-scale motion an entry needs before it is admitted."""


def _frame(
    ts: float,
    *,
    move: dict[int, int] | None = None,
    still: dict[int, int] | None = None,
    device_occupancy: bool = False,
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
        device_occupancy=device_occupancy,
    )


def _warmup_frames(count: int = 7) -> list[Frame]:
    """Idle frames spanning enough 60s buckets for the baseline to go ready."""
    return [_frame(i * 60.0) for i in range(count)]


async def _setup_entry(
    hass: HomeAssistant, *, options: dict[str, float] | None = None
) -> tuple[MockConfigEntry, FakeLD2410Client]:
    """Add and set up a config entry, returning it and its fake BLE client."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="PRP1-RD_6615",
        data={CONF_ADDRESS: TEST_ADDRESS},
        unique_id=TEST_ADDRESS,
        options=options or {},
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED

    client = entry.runtime_data.client
    assert isinstance(client, FakeLD2410Client)
    return entry, client


def _entity_id(hass: HomeAssistant, platform: str, key: str) -> str | None:
    registry = er.async_get(hass)
    return registry.async_get_entity_id(platform, DOMAIN, f"{TEST_ADDRESS}_{key}")


async def test_setup_and_unload(hass: HomeAssistant) -> None:
    """A config entry sets up, registers a device, creates entities, and unloads cleanly."""
    entry, client = await _setup_entry(hass)

    device_registry_entry = dr.async_get(hass).async_get_device(
        identifiers={(DOMAIN, TEST_ADDRESS)}
    )
    assert device_registry_entry is not None

    for platform, key in ENTITY_KEYS:
        assert _entity_id(hass, platform, key) is not None, f"missing {platform}.{key}"

    assert client.started

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED
    assert client.stopped

    assert not any(
        thread.name == "smart_ld2410-writer" for thread in threading.enumerate()
    )
    assert DOMAIN not in hass.data or "shared_store" not in hass.data[DOMAIN]


async def test_cold_start_passes_through_device_occupancy(hass: HomeAssistant) -> None:
    """Before the baseline is ready, occupancy mirrors the device's own bit."""
    entry, client = await _setup_entry(hass)
    coordinator = entry.runtime_data.coordinator

    client.on_frame(_frame(0.0, device_occupancy=True))
    await hass.async_block_till_done()

    assert not coordinator.data.baseline_ready
    occupancy_entity_id = _entity_id(hass, "binary_sensor", "occupancy")
    assert occupancy_entity_id is not None
    assert hass.states.get(occupancy_entity_id).state == "on"

    client.on_frame(_frame(0.1, device_occupancy=False))
    await hass.async_block_till_done()
    assert hass.states.get(occupancy_entity_id).state == "off"


async def test_occupancy_flip(hass: HomeAssistant) -> None:
    """A strong walk-in band enters occupancy; a sustained calm period exits it."""
    entry, client = await _setup_entry(hass)
    occupancy_entity_id = _entity_id(hass, "binary_sensor", "occupancy")
    assert occupancy_entity_id is not None

    for frame in _warmup_frames():
        client.on_frame(frame)
    await hass.async_block_till_done()
    assert entry.runtime_data.coordinator.data.baseline_ready

    warm_ts = 7 * 60.0
    for step in range(_ARRIVAL_FRAMES):
        client.on_frame(_frame(warm_ts + step * 0.1, move={1: 50, 2: 50, 3: 50, 4: 50}))
    await hass.async_block_till_done()
    assert hass.states.get(occupancy_entity_id).state == "on"

    # First calm frame starts the hold countdown; a second one, timestamped
    # past hold_s later, lets it expire in a single step.
    calm_ts = warm_ts + _ARRIVAL_FRAMES * 0.1
    client.on_frame(_frame(calm_ts))
    client.on_frame(_frame(calm_ts + 31.0))
    await hass.async_block_till_done()
    assert hass.states.get(occupancy_entity_id).state == "off"


async def test_availability(hass: HomeAssistant) -> None:
    """A disconnect makes entities unavailable; a reconnect restores them."""
    entry, client = await _setup_entry(hass)
    occupancy_entity_id = _entity_id(hass, "binary_sensor", "occupancy")
    assert occupancy_entity_id is not None

    client.on_availability(False)
    await hass.async_block_till_done()
    assert hass.states.get(occupancy_entity_id).state == "unavailable"

    client.on_availability(True)
    await hass.async_block_till_done()
    assert hass.states.get(occupancy_entity_id).state != "unavailable"


async def test_options_update_preserves_baseline(hass: HomeAssistant) -> None:
    """Changing an option reconfigures the detector without discarding the baseline."""
    entry, client = await _setup_entry(hass)
    coordinator = entry.runtime_data.coordinator
    detector = coordinator.detector
    baseline_before = detector.baseline

    for frame in _warmup_frames():
        client.on_frame(frame)
    await hass.async_block_till_done()
    assert detector.baseline.ready

    old_k = detector.config.k
    new_options = {**entry.options, "k": old_k + 1.0}
    hass.config_entries.async_update_entry(entry, options=new_options)
    await hass.async_block_till_done()

    assert detector.baseline is baseline_before
    assert detector.baseline.ready
    assert detector.config.k == pytest.approx(old_k + 1.0)
    # A reload was not triggered; the same client/coordinator are still wired.
    assert entry.runtime_data.client is client
    assert entry.runtime_data.coordinator is coordinator


async def test_residual_sensors_disabled_by_default(hass: HomeAssistant) -> None:
    """Per-gate residual sensors start disabled; enabling one exposes state."""
    config_entry, _ = await _setup_entry(hass)
    registry = er.async_get(hass)

    entity_id = _entity_id(hass, "sensor", "residual_move_0")
    assert entity_id is not None
    registry_entry = registry.async_get(entity_id)
    assert registry_entry is not None
    assert registry_entry.disabled_by is not None
    assert hass.states.get(entity_id) is None

    registry.async_update_entity(entity_id, disabled_by=None)
    await hass.async_block_till_done()
    assert registry.async_get(entity_id).disabled_by is None

    # HA reloads the entry (after a delay) to bring the entity to life; do it
    # explicitly so the assertion doesn't depend on that timer.
    assert await hass.config_entries.async_reload(config_entry.entry_id)
    await hass.async_block_till_done()

    client = config_entry.runtime_data.client
    assert isinstance(client, FakeLD2410Client)
    client.on_frame(_frame(0.0, move={0: 40}))
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state not in (None, "unavailable")
    assert float(state.state) == pytest.approx(
        config_entry.runtime_data.coordinator.data.residuals_move[0], rel=1e-3
    )


async def test_concurrent_entry_setup_shares_one_store(hass: HomeAssistant) -> None:
    """Two entries set up concurrently share a single FrameStore."""
    entries = []
    for suffix in ("11", "22"):
        address = f"AA:BB:CC:DD:EE:{suffix}"
        entry = MockConfigEntry(
            domain=DOMAIN,
            title=f"PRP1-RD_{suffix}",
            data={CONF_ADDRESS: address},
            unique_id=address,
        )
        entry.add_to_hass(hass)
        entries.append(entry)

    results = await asyncio.gather(
        *(hass.config_entries.async_setup(entry.entry_id) for entry in entries)
    )
    await hass.async_block_till_done()

    assert all(results)
    assert all(entry.state is ConfigEntryState.LOADED for entry in entries)

    shared = hass.data[DOMAIN]["shared_store"]
    assert shared.refcount == 2
    assert {
        id(entry.runtime_data.coordinator._store)  # noqa: SLF001
        for entry in entries
    } == {id(shared.store)}
    assert (
        sum(
            1 for thread in threading.enumerate()
            if thread.name == "smart_ld2410-writer"
        )
        == 1
    )

    # Unloading one entry must leave the store the other one is using alone.
    assert await hass.config_entries.async_unload(entries[0].entry_id)
    await hass.async_block_till_done()
    assert entries[0].state is ConfigEntryState.NOT_LOADED
    assert entries[1].state is ConfigEntryState.LOADED
    assert hass.data[DOMAIN]["shared_store"] is shared
    assert shared.refcount == 1
    assert any(
        thread.name == "smart_ld2410-writer" for thread in threading.enumerate()
    )

    assert await hass.config_entries.async_unload(entries[1].entry_id)
    await hass.async_block_till_done()
    assert "shared_store" not in hass.data[DOMAIN]
    assert not any(
        thread.name == "smart_ld2410-writer" for thread in threading.enumerate()
    )


async def test_setup_failure_releases_shared_store(hass: HomeAssistant) -> None:
    """A failure after acquiring the store releases the reference again."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="PRP1-RD_6615",
        data={CONF_ADDRESS: TEST_ADDRESS},
        unique_id=TEST_ADDRESS,
    )
    entry.add_to_hass(hass)

    with patch.object(
        hass.config_entries,
        "async_forward_entry_setups",
        side_effect=ConfigEntryNotReady("platforms not ready"),
    ):
        assert not await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.SETUP_RETRY
    assert "shared_store" not in hass.data.get(DOMAIN, {})
    assert not any(
        thread.name == "smart_ld2410-writer" for thread in threading.enumerate()
    )

    # The retry succeeds and takes exactly one fresh reference.
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    assert hass.data[DOMAIN]["shared_store"].refcount == 1

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert "shared_store" not in hass.data[DOMAIN]


async def test_frames_land_in_store(hass: HomeAssistant) -> None:
    """Injected frames are queued to and persisted in the SQLite store."""
    entry, client = await _setup_entry(hass)

    client.on_frame(_frame(0.0, move={2: 10}))
    client.on_frame(_frame(0.1, move={2: 12}))
    await hass.async_block_till_done()

    db_path = hass.data[DOMAIN]["shared_store"].store.db_path

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    conn = sqlite3.connect(db_path)
    try:
        count = conn.execute(
            "SELECT COUNT(*) FROM frames WHERE sensor_id = ?", (TEST_ADDRESS,)
        ).fetchone()[0]
    finally:
        conn.close()
    assert count == 2


async def test_ble_device_not_found_raises_not_ready(hass: HomeAssistant) -> None:
    """Setup defers with ConfigEntryNotReady when the device can't be resolved."""
    with patch(
        "homeassistant.components.bluetooth.async_ble_device_from_address",
        return_value=None,
    ):
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="PRP1-RD_6615",
            data={CONF_ADDRESS: TEST_ADDRESS},
            unique_id=TEST_ADDRESS,
        )
        entry.add_to_hass(hass)
        assert not await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert entry.state is ConfigEntryState.SETUP_RETRY
