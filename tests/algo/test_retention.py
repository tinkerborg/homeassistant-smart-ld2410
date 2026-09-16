"""Tests for still-presence retention and ownership (spec 24 §1a, §2)."""

from __future__ import annotations

import json

from custom_components.smart_ld2410.algo.detector import Detector
from custom_components.smart_ld2410.algo.presence import Presence
from custom_components.smart_ld2410.algo.types import (
    GATE_COUNT,
    OWNERSHIP_ARMED,
    OWNERSHIP_DISARMED,
    DetectorConfig,
)

from . import (
    FrameStream,
    feed,
    hold_refreshes,
    make_config,
    make_detector,
    make_presence,
    warmup_frames,
)

SEAT_GATE = 3
"""Where the synthetic occupant settles."""

AMBIENT_STILL = 10
"""Still energy the empty room reports at every gate."""

OCCUPANT_STILL = 40
"""Still energy a body at rest adds on top of it."""

FRAME_S = 0.1
NEAR_GATE = 0
FAR_GATE = 5


def _still(level: int) -> tuple[int, ...]:
    """A still-channel reading with ``level`` at the seat and ambient elsewhere."""
    return tuple(
        level if gate == SEAT_GATE else AMBIENT_STILL for gate in range(GATE_COUNT)
    )


def _config(**overrides: float | None) -> DetectorConfig:
    """A config with the leading-edge rule live, as ownership needs."""
    values: dict[str, float | None] = {"lead_gate_max": 1, "arrival_frac": 0.0}
    values.update(overrides)
    return make_config(**values)


def _settle(tracker: Presence, ts: float, seconds: float) -> float:
    """Hold the room at ambient for ``seconds``, returning the new frame time."""
    end = ts + seconds
    while ts < end:
        tracker.update(ts, _still(AMBIENT_STILL))
        ts += FRAME_S
    return ts


def _sit_down(tracker: Presence, ts: float, seconds: float) -> float:
    """Raise the seat gate for ``seconds``, returning the new frame time."""
    end = ts + seconds
    while ts < end:
        tracker.update(ts, _still(OCCUPANT_STILL))
        ts += FRAME_S
    return ts


def test_a_rise_in_the_still_channel_reads_positive() -> None:
    """Somebody settling into the room separates the fast EMA from the slow one."""
    tracker = make_presence(_config())

    ts = _settle(tracker, 0.0, 30.0)
    assert tracker.values[SEAT_GATE] == 0.0

    _sit_down(tracker, ts, 10.0)

    assert tracker.values[SEAT_GATE] >= _config().retention_on


def test_a_departure_never_reads_as_presence() -> None:
    """The signed statistic is what keeps a departure transient out of the hold."""
    tracker = make_presence(_config(tau_peak=0.0))

    ts = _settle(tracker, 0.0, 30.0)
    ts = _sit_down(tracker, ts, 60.0)
    _settle(tracker, ts, 10.0)

    assert tracker.values[SEAT_GATE] == 0.0


def test_the_peak_is_held_across_a_quiet_stretch() -> None:
    """A sit is not over because one minute of it went sub-threshold."""
    tracker = make_presence(_config(tau_peak=90.0))

    ts = _settle(tracker, 0.0, 30.0)
    ts = _sit_down(tracker, ts, 10.0)
    peak = tracker.values[SEAT_GATE]

    _sit_down(tracker, ts, 30.0)

    assert tracker.values[SEAT_GATE] > peak * 0.5


def test_retention_only_answers_for_the_occupancys_own_gates() -> None:
    """Elevation somewhere the visit never reached is somebody else's business."""
    config = _config()
    tracker = make_presence(config)

    ts = _settle(tracker, 0.0, 30.0)
    tracker.enter((NEAR_GATE, 1))
    ts = _sit_down(tracker, ts, 10.0)

    assert tracker.values[SEAT_GATE] >= config.retention_on
    assert not hold_refreshes(config, tracker, ts, scored=False)


def test_retention_holds_a_disarmed_room_until_it_decays() -> None:
    """Stillness cannot release a room nobody has been seen leaving."""
    config = _config(tau_peak=1.0)
    tracker = make_presence(config)

    ts = _settle(tracker, 0.0, 30.0)
    tracker.enter((SEAT_GATE,))
    ts = _sit_down(tracker, ts, 10.0)
    assert hold_refreshes(config, tracker, ts, scored=False)

    ts = _settle(tracker, ts, 30.0)

    assert tracker.level < config.retention_off
    assert not hold_refreshes(config, tracker, ts, scored=False)


def test_zero_retention_off_leaves_release_to_the_score() -> None:
    """Turning retention release-gating off takes retention out of the hold."""
    config = _config(retention_off=0.0)
    tracker = make_presence(config)

    ts = _settle(tracker, 0.0, 30.0)
    tracker.enter((SEAT_GATE,))
    ts = _sit_down(tracker, ts, 10.0)

    assert tracker.level >= config.retention_on
    assert not hold_refreshes(config, tracker, ts, scored=False)


def _walk(
    config: DetectorConfig,
    tracker: Presence,
    ts: float,
    frames: int,
    gate: int | None,
) -> float:
    """Feed ``frames`` frames of activity leading at ``gate``."""
    for _ in range(frames):
        tracker.observe_lead(ts, gate)
        hold_refreshes(config, tracker, ts, scored=True)
        ts += FRAME_S
    return ts


def test_the_entry_walk_in_cannot_arm_release() -> None:
    """Arriving at the entry gates is not the same event as leaving by them."""
    config = _config()
    tracker = make_presence(config)
    tracker.enter((NEAR_GATE,))

    _walk(config, tracker, 0.0, config.cross_n * 3, NEAR_GATE)

    assert tracker.state == OWNERSHIP_DISARMED


def test_re_crossing_the_entry_band_arms_release() -> None:
    """A fresh burst at the entry gates, after quiet, is the occupant heading out."""
    config = _config()
    tracker = make_presence(config)
    tracker.enter((NEAR_GATE,))

    ts = _walk(config, tracker, 0.0, config.cross_n * 3, NEAR_GATE)
    ts = _walk(config, tracker, ts + config.quiet_s, 1, None)
    _walk(config, tracker, ts, config.cross_n, NEAR_GATE)

    assert tracker.state == OWNERSHIP_ARMED


def _arm(tracker: Presence, config: DetectorConfig) -> float:
    """Drive a fresh ownership through to armed, returning the frame time."""
    tracker.enter((NEAR_GATE,))
    ts = _walk(config, tracker, 0.0, config.cross_n, NEAR_GATE)
    ts = _walk(config, tracker, ts + config.quiet_s, 1, None)
    ts = _walk(config, tracker, ts, config.cross_n, NEAR_GATE)
    assert tracker.armed
    return ts


def test_an_armed_room_is_held_only_by_attributed_evidence() -> None:
    """Evidence leading beyond the entry band belongs to the neighbour."""
    config = _config()
    tracker = make_presence(config)
    ts = _arm(tracker, config)

    assert hold_refreshes(config, tracker, ts, scored=True)

    ts += config.grace_s + 1.0
    tracker.observe_lead(ts, FAR_GATE)

    assert not hold_refreshes(config, tracker, ts, scored=True)


def test_an_armed_room_ignores_retention() -> None:
    """Once the occupant has been seen leaving, stillness stops holding the door."""
    config = _config()
    tracker = make_presence(config)
    ts = _arm(tracker, config)
    tracker.include((SEAT_GATE,))

    ts = _settle(tracker, ts, 30.0)
    ts = _sit_down(tracker, ts, 10.0)
    ts += config.grace_s + 1.0

    assert tracker.level >= config.retention_on
    assert not hold_refreshes(config, tracker, ts, scored=True)


def test_state_round_trip_preserves_retention_and_ownership() -> None:
    """A restored sensor carries on from the statistic it had already built."""
    stream = FrameStream(sigma=0.5)
    config = _config()
    detector = make_detector(config)
    feed(detector, warmup_frames(stream))
    feed(
        detector,
        stream.burst(5.0, move=dict.fromkeys((0, 1, 2), 50), still={SEAT_GATE: 40}),
    )
    assert detector.occupied

    payload = json.loads(json.dumps(detector.state_to_dict()))
    restored = Detector.presence_from_state(payload, config)
    assert restored is not None

    assert restored.values == detector.presence.values
    assert restored.state == detector.presence.state == OWNERSHIP_DISARMED

    for frame in stream.burst(5.0, still={SEAT_GATE: 40}):
        detector.presence.update(frame.ts_mono, frame.still_gates)
        restored.update(frame.ts_mono, frame.still_gates)

    assert restored.values == detector.presence.values


def test_state_from_before_this_phase_starts_the_statistic_fresh() -> None:
    """An older payload simply has no retention in it, and must still load."""
    detector = make_detector(_config())

    payload = detector.state_to_dict()
    del payload["retention"]

    assert Detector.presence_from_state(payload, detector.config) is None
