"""Tests for the Phase 2 HA-layer wiring: episodes, gate classes, features, options."""

from __future__ import annotations

import sqlite3
from typing import Any

from homeassistant.const import CONF_ADDRESS
from homeassistant.core import Event, HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.smart_ld2410.algo.types import (
    GATE_COUNT,
    DetectorConfig,
    Frame,
)
from custom_components.smart_ld2410.const import (
    CONF_ARRIVAL_FRAC,
    CONF_ARRIVAL_MIN_FRAMES,
    CONF_BOUNDARY_CONFIRM_DAYS,
    CONF_CEIL_DROP,
    CONF_CEILING_ENABLED,
    CONF_CEIL_SAT,
    CONF_MAX_GATE,
    CONF_N_CEIL_MIN,
    CONF_RAW_RETENTION_DAYS,
    CONF_SUMMARY_RETENTION_DAYS,
    CONF_T_DWELL_S,
    DOMAIN,
    EVENT_EPISODE,
    SIGNAL_FEATURES_V1,
)

from .conftest import TEST_ADDRESS, FakeLD2410Client


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
    hass: HomeAssistant, *, options: dict[str, Any] | None = None
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

    client = entry.runtime_data.client
    assert isinstance(client, FakeLD2410Client)
    return entry, client


def _entity_id(hass: HomeAssistant, platform: str, key: str) -> str | None:
    registry = er.async_get(hass)
    return registry.async_get_entity_id(platform, DOMAIN, f"{TEST_ADDRESS}_{key}")


async def test_episode_lands_in_store_and_fires_bus_event(hass: HomeAssistant) -> None:
    """An entry+exit stream closes a detection-scope episode: DB row + bus event."""
    entry, client = await _setup_entry(hass)

    events: list[dict[str, Any]] = []

    def _capture(event: Event) -> None:
        events.append(event.data)

    hass.bus.async_listen(EVENT_EPISODE, _capture)

    for frame in _warmup_frames():
        client.on_frame(frame)
    await hass.async_block_till_done()

    # Same shape as the occupancy-flip scenario: one strong two-gate frame
    # enters occupancy and opens gate/detection episodes; the sustained idle
    # gap that follows exits occupancy and closes both.
    warm_ts = 7 * 60.0
    for step in range(_ARRIVAL_FRAMES):
        client.on_frame(_frame(warm_ts + step * 0.1, move={3: 50, 4: 50}))
    calm_ts = warm_ts + _ARRIVAL_FRAMES * 0.1
    client.on_frame(_frame(calm_ts))
    client.on_frame(_frame(calm_ts + 31.0))
    await hass.async_block_till_done()

    assert len(events) == 1
    payload = events[0]
    assert payload["sensor_id"] == TEST_ADDRESS
    assert payload["result"] == "entered"
    assert payload["gate_lo"] <= 3
    assert payload["gate_hi"] >= 4
    assert payload["t1"] > payload["t0"]

    db_path = hass.data[DOMAIN]["shared_store"].store.db_path
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT sensor_id, result, gate_lo, gate_hi FROM episodes WHERE sensor_id = ?",
            (TEST_ADDRESS,),
        ).fetchall()
    finally:
        conn.close()
    assert len(rows) == 1
    assert rows[0] == (TEST_ADDRESS, "entered", payload["gate_lo"], payload["gate_hi"])


async def test_gate_classes_entity_reflects_detector_output(hass: HomeAssistant) -> None:
    """A sustained still dwell on gate 3 promotes it to IN_ROOM ('I')."""
    entry, client = await _setup_entry(hass)
    entity_id = _entity_id(hass, "sensor", "gate_classes")
    assert entity_id is not None

    for frame in _warmup_frames():
        client.on_frame(frame)
    await hass.async_block_till_done()

    # Default t_dwell_s is 60s, so the dwell runs a full minute of frames.
    # They are spaced under episode_stall_s (10s) apart, or the stream would
    # read as stalled; the gap that follows exceeds it, which is what closes
    # the episode and hands it to the classifier.
    warm_ts = 7 * 60.0
    for step in range(13):
        client.on_frame(_frame(warm_ts + step * 5.0, still={3: 50}))
    client.on_frame(_frame(warm_ts + 75.0))
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state is not None
    assert len(state.state) == GATE_COUNT
    assert state.state[3] == "I"
    assert state.attributes["gate_3_class"] == "in_room"
    assert state.attributes["gate_3_n_sustained"] >= 1.0


async def test_occupancy_attributes_track_mode_passthrough_to_learned(
    hass: HomeAssistant,
) -> None:
    """Occupancy attributes exist in both cold-start and learned modes."""
    entry, client = await _setup_entry(hass)
    entity_id = _entity_id(hass, "binary_sensor", "occupancy")
    assert entity_id is not None

    client.on_frame(_frame(0.0, device_occupancy=True))
    await hass.async_block_till_done()
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.attributes["mode"] == "passthrough"
    assert state.attributes["boundary_gate"] is None
    assert "confidence" in state.attributes
    assert "active_gate_min" in state.attributes
    assert "active_gate_max" in state.attributes

    for frame in _warmup_frames():
        client.on_frame(frame)
    await hass.async_block_till_done()

    warm_ts = 7 * 60.0
    client.on_frame(_frame(warm_ts, move={3: 50, 4: 50}))
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state is not None
    assert state.attributes["mode"] == "learned"
    assert state.attributes["active_gate_min"] == 3
    assert state.attributes["active_gate_max"] == 4
    assert 0.0 <= state.attributes["confidence"] <= 1.0


async def test_feature_signal_emitted_with_contract_keys_and_throttled(
    hass: HomeAssistant,
) -> None:
    """smart_ld2410_features_v1 fires with the contract's keys, at <=2 Hz."""
    entry, client = await _setup_entry(hass)

    payloads: list[dict[str, Any]] = []
    async_dispatcher_connect(hass, SIGNAL_FEATURES_V1, payloads.append)

    for frame in _warmup_frames():
        client.on_frame(frame)
    await hass.async_block_till_done()
    warmup_count = len(payloads)
    assert warmup_count >= 1

    payloads.clear()
    # 20 frames crammed into under half a second of ts_mono: throttled to a
    # single dispatch instead of 20.
    base_ts = 7 * 60.0
    for i in range(20):
        client.on_frame(_frame(base_ts + i * 0.01, move={3: 40}))
    await hass.async_block_till_done()

    assert len(payloads) == 1
    payload = payloads[0]
    assert payload["schema"] == 1
    assert payload["sensor_id"] == TEST_ADDRESS
    assert set(payload) == {
        "schema",
        "sensor_id",
        "ts",
        "occ",
        "confidence",
        "centroid_gate",
        "gate_span",
        "residual_mass_move",
        "residual_mass_still",
        "edge_band",
        "mode",
    }
    assert payload["mode"] == "learned"
    assert payload["edge_band"] in ("near", "far", "none")


async def test_options_round_trip_for_phase2_knobs(hass: HomeAssistant) -> None:
    """Phase 2 detector knobs set via options reach the DetectorConfig."""
    entry, _client = await _setup_entry(
        hass,
        options={
            CONF_T_DWELL_S: 45.0,
            CONF_MAX_GATE: 5,
        },
    )
    detector = entry.runtime_data.coordinator.detector
    assert detector.config.t_dwell_s == 45.0
    assert detector.config.max_gate == 5

    new_options = {**entry.options, CONF_T_DWELL_S: 90.0}
    new_options.pop(CONF_MAX_GATE, None)
    hass.config_entries.async_update_entry(entry, options=new_options)
    await hass.async_block_till_done()

    assert detector.config.t_dwell_s == 90.0
    assert detector.config.max_gate is None


async def test_boundary_gate_entity_publishes_while_the_ceiling_is_disabled(
    hass: HomeAssistant,
) -> None:
    """Spec 21 §4-5: the diagnostic ships on even though the effect ships off.

    Watching a real install learn a boundary, without letting the boundary
    act, is the entire ship path - so this entity existing and carrying its
    profile at default options is the feature, not an extra.
    """
    _entry, client = await _setup_entry(hass)
    entity_id = _entity_id(hass, "sensor", "boundary_gate")
    assert entity_id is not None

    for frame in _warmup_frames():
        client.on_frame(frame)
    await hass.async_block_till_done()

    warm_ts = 7 * 60.0
    client.on_frame(_frame(warm_ts, move={3: 50, 4: 50}))
    client.on_frame(_frame(warm_ts + 0.1))
    client.on_frame(_frame(warm_ts + 31.1))
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == "unknown"  # nothing confirmed on one episode
    assert state.attributes["ceiling_enabled"] is False
    assert state.attributes["confirmed_days"] == 0
    profile = state.attributes["ceil_profile"]
    assert len(profile) == GATE_COUNT
    # One episode is evidence of a ceiling but not of a falloff, so the
    # compensated profile stays empty while the episode counts already climb.
    assert profile == [None] * GATE_COUNT
    assert state.attributes["n_epi"][3] >= 1.0
    assert state.attributes["n_epi"][8] == 0.0


async def test_ceiling_options_round_trip(hass: HomeAssistant) -> None:
    """The spec 21 §4 knobs reach the DetectorConfig, and default to disabled."""
    entry, _client = await _setup_entry(hass)
    assert entry.runtime_data.coordinator.detector.config.ceiling_enabled is False

    hass.config_entries.async_update_entry(
        entry,
        options={
            CONF_CEILING_ENABLED: True,
            CONF_CEIL_DROP: 0.6,
            CONF_N_CEIL_MIN: 25,
            CONF_CEIL_SAT: 88,
            CONF_BOUNDARY_CONFIRM_DAYS: 5,
        },
    )
    await hass.async_block_till_done()

    config = entry.runtime_data.coordinator.detector.config
    assert config.ceiling_enabled is True
    assert config.ceil_drop == 0.6
    assert config.n_ceil_min == 25
    assert config.ceil_sat == 88
    assert config.boundary_confirm_days == 5


async def test_arrival_options_round_trip(hass: HomeAssistant) -> None:
    """The arrival-gating knobs reach the DetectorConfig."""
    entry, _client = await _setup_entry(hass)

    hass.config_entries.async_update_entry(
        entry,
        options={CONF_ARRIVAL_FRAC: 0.75, CONF_ARRIVAL_MIN_FRAMES: 7},
    )
    await hass.async_block_till_done()

    config = entry.runtime_data.coordinator.detector.config
    assert config.arrival_frac == 0.75
    assert config.arrival_min_frames == 7


async def test_retention_options_reach_the_store(hass: HomeAssistant) -> None:
    """raw_retention_days/summary_retention_days from options land on the FrameStore."""
    entry, _client = await _setup_entry(
        hass,
        options={CONF_RAW_RETENTION_DAYS: 3, CONF_SUMMARY_RETENTION_DAYS: 40},
    )
    store = hass.data[DOMAIN]["shared_store"].store
    assert store.raw_retention_days == 3
    assert store.summary_retention_days == 40

    new_options = {**entry.options, CONF_RAW_RETENTION_DAYS: 10}
    hass.config_entries.async_update_entry(entry, options=new_options)
    await hass.async_block_till_done()

    assert store.raw_retention_days == 10
    assert store.summary_retention_days == 40
