"""Tests for the residual-based occupancy state machine."""

from __future__ import annotations

from itertools import pairwise

import pytest

from custom_components.smart_ld2410.algo.types import (
    CHANNEL_STILL,
    DEFAULT_STAGES,
    DetectorOutput,
    Frame,
)

from . import (
    FrameStream,
    entry_index,
    feed,
    make_config,
    make_detector,
    warmup_frames,
)


HOLD_STAGES = (*DEFAULT_STAGES, "score_hold")
"""The default detector plus the score-driven hold the hysteresis rules need."""

def _transitions(outputs: list[DetectorOutput]) -> int:
    """Count occupancy edges in a run of outputs."""
    return sum(
        1
        for previous, current in pairwise(outputs)
        if previous.occupied != current.occupied
    )


def test_cold_start_passes_through_device_occupancy() -> None:
    """Spec item 9: the device's bit is used until the baseline is ready."""
    stream = FrameStream()
    detector = make_detector()

    cold = feed(detector, stream.burst(3.0, device_occupancy=True))
    assert all(not output.baseline_ready for output in cold)
    assert all(output.occupied for output in cold)
    assert all(output.confidence == 0.5 for output in cold)
    assert all(output.score == 0.0 for output in cold)
    assert all(output.active_gates == () for output in cold)
    assert all(not output.adaptation_frozen for output in cold)

    vacant_cold = feed(detector, stream.burst(1.0, device_occupancy=False))
    assert not any(output.occupied for output in vacant_cold)

    # Once ready the detector takes over: the device bit is ignored, and the
    # empty room releases after the normal hold rather than glitching off.
    ready = feed(detector, stream.burst(60.0, device_occupancy=True))
    assert ready[-1].baseline_ready
    assert not ready[-1].occupied
    assert all(output.score == 0.0 for output in ready)


def test_stuck_gate_zero_never_asserts_occupancy() -> None:
    """Spec item 2: an isolated hot gate 0 is spatial nonsense and is dropped."""
    stream = FrameStream()
    detector = make_detector()
    feed(detector, warmup_frames(stream))

    outputs = feed(detector, stream.burst(30.0, move={0: 55}))

    assert not any(output.occupied for output in outputs)
    assert all(output.score == 0.0 for output in outputs)
    assert all(output.active_gates == () for output in outputs)
    # The residual really is enormous - it is suppression, not a weak signal.
    assert outputs[0].residuals_move[0] > detector.config.k * 5


def test_grazing_noise_does_not_flap() -> None:
    """Spec item 3: threshold-grazing noise leaves the output rock steady."""
    stream = FrameStream()
    detector = make_detector()
    feed(detector, warmup_frames(stream))

    outputs: list[DetectorOutput] = []
    for index in range(600):
        # One isolated gate spikes well past the per-gate threshold every
        # second - exactly the pattern that flaps a device-style detector.
        spike = {4: 25} if index % 10 == 0 else None
        outputs.append(detector.process(stream.next_frame(move=spike)))

    assert not any(output.occupied for output in outputs)
    assert _transitions(outputs) == 0
    assert max(output.score for output in outputs) < detector.config.enter_score
    assert max(output.confidence for output in outputs) < 0.5


def test_multi_gate_entry_is_prompt_and_confident() -> None:
    """Spec item 4: a real body across several gates enters within a few frames."""
    stream = FrameStream()
    detector = make_detector()
    feed(detector, warmup_frames(stream))

    outputs = feed(detector, stream.burst(1.0, move={3: 40, 4: 40, 5: 40}))

    entry = outputs[entry_index(detector.config)]
    assert entry.occupied
    assert entry.active_gates == (3, 4, 5)
    assert entry.confidence > 0.5
    assert entry.score >= detector.config.enter_score
    assert entry.adaptation_frozen


def test_still_presence_is_retained_and_never_learned() -> None:
    """Spec item 5: hours of still presence hold, and stay out of the floor.

    Realistic proportions matter now that learning never stops: the baseline
    window is 12h, six of which were vacant before the person arrived and two
    of which they spend sitting still. At 25% of the window the occupied
    buckets sit above the 25th percentile, so the floor keeps reading the
    empty room.
    """
    stream = FrameStream()
    config = make_config(baseline_window_s=12 * 3600.0, stages=HOLD_STAGES)
    detector = make_detector(config, bucket_s=60.0)
    step = 10.0
    feed(detector, stream.burst(6 * 3600.0, interval_s=step))
    assert detector.baseline.ready
    idle_floor = detector.baseline.floor(4, CHANNEL_STILL)

    entry = feed(detector, stream.burst(3 * step, move={3: 40, 4: 40, 5: 40},
                                        interval_s=step))
    assert entry[-1].occupied

    # The person settles: energy collapses into one still gate with only weak
    # spill into its neighbours. Two hours of it.
    still_signature = {3: 4, 4: 12, 5: 4}
    outputs = feed(
        detector,
        stream.burst(2 * 3600.0, still=still_signature, interval_s=step),
    )

    assert all(output.occupied for output in outputs)
    assert all(output.adaptation_frozen for output in outputs)
    # Gate 4 carries the signature; noise occasionally lifts a neighbour over
    # the hot threshold too, which widens the run rather than breaking it.
    credited = sum(1 for output in outputs if 4 in output.active_gates)
    assert credited / len(outputs) > 0.99
    scored = sum(1 for output in outputs if output.score >= detector.config.exit_score)
    assert scored / len(outputs) > 0.99
    # Two hours of it went into the window - and left the floor where it was.
    assert detector.baseline.floor(4, CHANNEL_STILL) == pytest.approx(idle_floor, abs=0.5)

    # The person leaves: hold expires, then the reported freeze window.
    after = feed(detector, stream.burst(400.0, interval_s=step))
    assert not after[-1].occupied
    assert not after[-1].adaptation_frozen
    assert _transitions(after) == 1

    released = next(index for index, output in enumerate(after) if not output.occupied)
    unfrozen = next(
        index for index, output in enumerate(after) if not output.adaptation_frozen
    )
    assert (unfrozen - released) * step == pytest.approx(
        detector.config.freeze_hold_s, abs=step
    )

    # The still signature never reached the floor, so a repeat is detectable.
    feed(detector, stream.burst(600.0, interval_s=step))
    assert detector.baseline.floor(4, CHANNEL_STILL) == pytest.approx(stream.floor, abs=1.0)
    repeat = feed(detector, stream.burst(3 * step, move={3: 40, 4: 40, 5: 40},
                                         interval_s=step))
    assert repeat[entry_index(detector.config)].occupied


def test_real_hardware_idle_noise_never_enters() -> None:
    """Regression: the recorded empty-room noise must never assert occupancy.

    Modelled on the failure seen on hardware. Gates 0 and 1 idle at ~15 with a
    heavy right tail reaching into the high twenties several times a minute,
    while the rest of the array sits near zero. Under the old MAD-of-medians
    estimator those two adjacent gates scored z=10-20 apiece, entered
    occupancy on a blip, and every subsequent blip reset the exit hold.
    """
    stream = FrameStream(floor=2, sigma=1.5)
    detector = make_detector(make_config(baseline_window_s=600.0), bucket_s=10.0)
    idle = {0: 13, 1: 13}
    spikes = {0: (0.12, 10), 1: (0.12, 10)}

    warmup = feed(detector, stream.burst(120.0, move=idle, move_spikes=spikes))
    assert detector.baseline.ready
    assert not warmup[-1].occupied

    outputs = feed(detector, stream.burst(600.0, move=idle, move_spikes=spikes))

    assert not any(output.occupied for output in outputs)
    assert _transitions(outputs) == 0
    assert max(output.score for output in outputs) < detector.config.enter_score
    # The gates really are the noisy ones, and their residuals stay ordinary.
    assert detector.baseline.floor(0) > 10.0
    assert detector.baseline.spread(0) > 2 * detector.config.min_mad


def test_sustained_multi_gate_energy_enters_confidently() -> None:
    """A real body - several gates at ~4x the noise level - enters at once."""
    stream = FrameStream(floor=2, sigma=1.5)
    detector = make_detector(make_config(baseline_window_s=600.0), bucket_s=10.0)
    idle = {0: 13, 1: 13}
    spikes = {0: (0.12, 10), 1: (0.12, 10)}
    feed(detector, stream.burst(120.0, move=idle, move_spikes=spikes))

    person = {**idle, 3: 55, 4: 60, 5: 50}
    outputs = feed(detector, stream.burst(20.0, move=person, move_spikes=spikes))

    entered = entry_index(detector.config)
    assert outputs[entered].occupied
    assert outputs[entered].confidence > 0.5
    assert all(output.occupied for output in outputs[entered:])
    assert 4 in outputs[entered].active_gates


def test_warmup_contaminated_by_a_person_still_learns_the_noise() -> None:
    """A person present throughout warm-up does not get learned as background.

    Their energy is bursty - 30s of activity, 20s of quiet - so 40% of the
    buckets are clean, and the 25th-percentile floor reads those. That is the
    property that lets the baseline be learned in an occupied room.
    """
    stream = FrameStream()
    detector = make_detector(make_config(baseline_window_s=600.0), bucket_s=10.0)

    person = {3: 45, 4: 45}
    for _ in range(10):
        feed(detector, stream.burst(30.0, move=person))
        feed(detector, stream.burst(20.0))
    assert detector.baseline.ready

    # The person's gates were busy for 60% of warm-up, yet their floors were
    # learned from the quiet 40%.
    for gate in (3, 4):
        assert detector.baseline.floor(gate) == pytest.approx(
            stream.floor, abs=1.0
        )

    # The room, now genuinely empty, reads vacant.
    empty = feed(detector, stream.burst(120.0))
    assert not empty[-1].occupied
    assert not any(output.occupied for output in empty[-600:])

    # And a still-person signature at those same gates is still detected.
    repeat = feed(detector, stream.burst(5.0, still={3: 12, 4: 30, 5: 12}))
    assert repeat[-1].occupied
    assert 4 in repeat[-1].active_gates


def test_new_noise_source_is_absorbed_without_a_death_spiral() -> None:
    """A persistent new noise source is unlearned once the window turns over.

    Freezing adaptation while occupied used to make this unrecoverable: the
    source triggered detection, detection froze learning, and the sensor
    latched occupied forever. Learning unconditionally means the window simply
    absorbs it.
    """
    stream = FrameStream()
    config = make_config(baseline_window_s=300.0)
    detector = make_detector(config, bucket_s=10.0)
    feed(detector, stream.burst(120.0))
    assert detector.baseline.ready

    # Gates 0-1 start jittering at three times their old level, permanently.
    noisy = {0: 12, 1: 12}
    spikes = {0: (0.12, 8), 1: (0.12, 8)}
    onset = feed(detector, stream.burst(30.0, move=noisy, move_spikes=spikes))
    assert any(output.occupied for output in onset)  # a false positive, at first

    # One full window later the source is part of the noise model and the
    # detector has released - with adaptation never having been suspended.
    settled = feed(detector, stream.burst(600.0, move=noisy, move_spikes=spikes))
    assert not settled[-1].occupied
    tail = settled[-1200:]
    assert not any(output.occupied for output in tail)
    assert detector.baseline.floor(0) > stream.floor + 8

    # It has not gone blind: a real body elsewhere in the array still enters.
    person = {**noisy, 4: 50, 5: 50, 6: 50}
    assert feed(detector, stream.burst(2.0, move=person, move_spikes=spikes))[-1].occupied


def test_hysteresis_holds_through_short_dips() -> None:
    """Spec item 6: only a dip longer than hold_s releases occupancy."""
    stream = FrameStream()
    config = make_config(stages=HOLD_STAGES)
    detector = make_detector(config)
    feed(detector, warmup_frames(stream))

    present = {3: 40, 4: 40, 5: 40}
    assert feed(detector, stream.burst(1.0, move=present))[-1].occupied

    # A dip shorter than hold_s: still occupied throughout.
    dip = feed(detector, stream.burst(config.hold_s - 10.0))
    assert all(output.occupied for output in dip)
    assert all(output.score < config.exit_score for output in dip)

    # Recovery cancels the countdown, so the next dip gets the full hold again.
    recovered = feed(detector, stream.burst(1.0, move=present))
    assert all(output.occupied for output in recovered)

    partial = feed(detector, stream.burst(config.hold_s - 10.0))
    assert all(output.occupied for output in partial)

    long_dip = feed(detector, stream.burst(config.hold_s + 5.0))
    assert not long_dip[-1].occupied
    released_at = next(output for output in long_dip if not output.occupied)
    assert released_at.confidence < 0.5
    assert _transitions(long_dip) == 1


def test_gap_in_frames_is_tolerated() -> None:
    """Spec item 7: a ten-minute BLE dropout elapses timers, nothing else."""
    stream = FrameStream()
    detector = make_detector(make_config(stages=HOLD_STAGES))
    feed(detector, warmup_frames(stream))

    present = {3: 40, 4: 40, 5: 40}
    assert feed(detector, stream.burst(1.0, move=present))[-1].occupied
    buckets_before = detector.baseline.bucket_count

    stream.skip(600.0)

    # The first frame after the gap cannot know what happened during it, so the
    # hold countdown starts there rather than retroactively expiring.
    resumed = feed(detector, stream.burst(5.0))
    assert resumed[0].occupied
    assert resumed[0].score == 0.0

    released = feed(detector, stream.burst(detector.config.hold_s + 5.0))
    assert not released[-1].occupied

    # No phantom buckets were invented across the gap.
    assert detector.baseline.bucket_count <= buckets_before + 40
    assert detector.baseline.ready

    # Presence after the gap still works.
    assert feed(detector, stream.burst(120.0))[-1].occupied is False
    assert feed(detector, stream.burst(1.0, move=present))[-1].occupied


def test_partial_neighbour_elevation_rescues_a_single_gate() -> None:
    """One hot gate counts when a neighbour is at least partially elevated."""
    stream = FrameStream()
    detector = make_detector()
    feed(detector, warmup_frames(stream))

    isolated = feed(detector, stream.burst(5.0, still={4: 12}))
    assert all(output.score == 0.0 for output in isolated)
    assert all(output.active_gates == () for output in isolated)

    # Sustained spill into gate 3 - below the hot threshold but above k/2 -
    # makes the same lone gate credible once the support estimate settles.
    with_spill = feed(detector, stream.burst(5.0, still={3: 4, 4: 12}))
    # (Noise can occasionally lift the spill gate itself over the threshold,
    # which widens the run - the point is that gate 4 now counts at all.)
    assert 4 in with_spill[-1].active_gates
    assert with_spill[-1].score > 0.0


def test_repeated_timestamps_do_not_disturb_state() -> None:
    """Duplicate frame timestamps are consumed without corrupting smoothing."""
    stream = FrameStream()
    detector = make_detector()
    feed(detector, warmup_frames(stream))

    hot = {3: 40, 4: 40, 5: 40}
    feed(detector, stream.burst(1.0, move=hot))
    frame = stream.next_frame(move=hot)
    first = detector.process(frame)
    repeat = detector.process(frame)

    assert first.occupied
    assert detector.occupied
    assert repeat.score == pytest.approx(first.score)
    assert repeat.active_gates == first.active_gates


def test_confidence_is_monotonic_and_centred_on_enter_score() -> None:
    """Confidence is continuous, 0.5 at enter_score, saturating towards 1."""
    detector = make_detector()
    enter = detector.config.enter_score
    values = [detector._confidence(score / 10.0) for score in range(200)]

    assert all(later >= earlier for earlier, later in pairwise(values))
    assert detector._confidence(0.0) < 0.05
    assert detector._confidence(enter) == pytest.approx(0.5)
    assert detector._confidence(3 * enter) > 0.99


def test_backwards_ts_mono_rebases_hold_and_freeze() -> None:
    """A ts_mono jump backwards rebases hold/freeze instead of wedging forever.

    A recorded dataset spanning an HA restart replays a ``ts_mono`` (a
    per-process monotonic clock) that drops back near zero partway through.
    """
    stream = FrameStream()
    config = make_config()
    detector = make_detector(config)
    feed(detector, warmup_frames(stream))

    present = {3: 40, 4: 40, 5: 40}
    assert feed(detector, stream.burst(1.0, move=present))[-1].occupied

    # A calm frame arms the hold countdown in the current ("old") ts_mono
    # timebase.
    calm = stream.next_frame()
    output = detector.process(calm)
    assert output.occupied
    assert detector._hold_until_mono == pytest.approx(calm.ts_mono + config.hold_s)

    def retimed(ts_mono: float) -> Frame:
        return Frame(
            ts_utc=stream.ts,
            ts_mono=ts_mono,
            move_gates=calm.move_gates,
            still_gates=calm.still_gates,
            target_distance_cm=0,
            device_occupancy=False,
        )

    # Simulate a process restart: ts_mono jumps backwards to a small value
    # while everything else about the stream continues normally.
    jumped = detector.process(retimed(3.0))
    assert jumped.occupied  # not permanently wedged
    assert detector._hold_until_mono == pytest.approx(3.0 + config.hold_s)
    assert detector._freeze_until_mono is None

    # Calm frames advancing in the new timebase release occupancy after
    # hold_s counted from the jump...
    ts_mono = 3.0
    outputs: list[DetectorOutput] = []
    for _ in range(int((config.hold_s + 5.0) * 10)):
        ts_mono += 0.1
        outputs.append(detector.process(retimed(ts_mono)))
    assert not outputs[-1].occupied
    released_index = next(i for i, o in enumerate(outputs) if not o.occupied)
    released_ts = 3.0 + (released_index + 1) * 0.1
    assert released_ts == pytest.approx(3.0 + config.hold_s, abs=0.2)

    # ...and adaptation unfreezes freeze_hold_s after that release point.
    assert detector._freeze_until_mono == pytest.approx(
        released_ts + config.freeze_hold_s, abs=0.2
    )

    # A second process restart, this time while a freeze (not a hold) is
    # active, rebases the freeze deadline too.
    restart_ts = 4.0
    reoutput = detector.process(retimed(restart_ts))
    assert reoutput.adaptation_frozen
    assert detector._freeze_until_mono == pytest.approx(
        restart_ts + config.freeze_hold_s
    )
    assert detector._hold_until_mono is None

    ts_mono = restart_ts
    for _ in range(int((config.freeze_hold_s + 5.0) * 10)):
        ts_mono += 0.1
        outputs.append(detector.process(retimed(ts_mono)))
    assert not outputs[-1].adaptation_frozen


def test_reconfigure_resizes_the_live_baseline_window() -> None:
    """Spec item: reconfigure() resizes the live baseline, not just the config."""
    stream = FrameStream()
    config = make_config(baseline_window_s=30.0)
    detector = make_detector(config)
    for frame in stream.burst(20.0, move={0: 50}):
        detector.baseline.add_frame(frame)
    for frame in stream.burst(5.0):
        detector.baseline.add_frame(frame)
    assert detector.baseline.ready
    mixed_floor = detector.baseline.floor(0)

    smaller = make_config(baseline_window_s=5.0)
    detector.reconfigure(smaller)

    assert detector.config is smaller
    assert detector.baseline.ready
    assert detector.baseline.bucket_count == 5
    assert detector.baseline.floor(0) == pytest.approx(stream.floor, abs=1.0)
    assert detector.baseline.floor(0) != pytest.approx(mixed_floor, abs=1.0)

    larger = make_config(baseline_window_s=60.0)
    detector.reconfigure(larger)
    before_count = detector.baseline.bucket_count
    for frame in stream.burst(55.0):
        detector.baseline.add_frame(frame)
    assert detector.baseline.bucket_count > before_count
    assert detector.baseline.bucket_count <= 60


def test_negative_residuals_are_reported_but_not_scored() -> None:
    """Below-floor energy is diagnostic only; it can never add evidence."""
    stream = FrameStream()
    detector = make_detector()
    feed(detector, warmup_frames(stream))

    quiet = FrameStream(floor=0, sigma=0.0, start_ts=stream.ts)
    outputs = feed(detector, quiet.burst(1.0))

    assert all(min(output.residuals_move) < 0.0 for output in outputs)
    assert all(output.score == 0.0 for output in outputs)
    assert not any(output.occupied for output in outputs)
