"""Tests for energy-ceiling boundary learning (spec 21).

Two levels, deliberately:

* The boundary *inference* (§2) is exercised against the classifier directly,
  by handing it episodes whose peak raw energies are stated outright. The rule
  is a statement about ceiling profiles, and reading a specific profile out of
  a synthetic radar stream would test the stream generator at least as much as
  the rule.
* The boundary's *effect* (§3) is exercised end to end through a real detector
  on a synthetic wall-attenuation profile, because "does a through-wall dwell
  still turn occupancy on?" is not a question the classifier can answer alone.
"""

from __future__ import annotations

import json

from custom_components.smart_ld2410.algo.gates import GateModel
from custom_components.smart_ld2410.algo.detector import Detector
from custom_components.smart_ld2410.algo.types import (
    CLASS_IN_ROOM,
    CLASS_OUT,
    GATE_COUNT,
    GATE_SPACING_M,
    MAX_GATE_ENERGY,
    SCOPE_GATE,
    DetectorConfig,
    Episode,
)

from . import FrameStream, feed, make_config, make_detector, make_gates

DAY_S = 86400.0
"""One evaluation interval: the classifier's "day" (spec 21 §2.3)."""

IN_ROOM_ENERGY = 90
"""Peak raw move energy an in-room gate reaches on a good pass."""

WALL_ENERGY = 22
"""Peak raw move energy the same traffic produces through a wall."""


def _episode(
    gate: int,
    ts: float,
    *,
    peak: int,
    duration_s: float = 3.0,
    still_frac: float = 0.0,
) -> Episode:
    """One closed per-gate episode with a stated peak raw move energy."""
    gate_peaks = [0] * GATE_COUNT
    gate_peaks[gate] = peak
    return Episode(
        scope=SCOPE_GATE,
        gate=gate,
        t0=ts - duration_s,
        t1=ts,
        peak_residual=10.0,
        gate_lo=gate,
        gate_hi=gate,
        centroid_mean=float(gate),
        centroid_vel=0.0,
        still_frac=still_frac,
        result="entered",
        gate_peaks=tuple(gate_peaks),
    )


def _feed_day(
    classifier: GateModel,
    day: int,
    profile: dict[int, int],
    *,
    count: int = 12,
) -> None:
    """Give every gate in ``profile`` ``count`` episodes at that peak energy.

    Episodes are spread over the day so their timestamps are distinct, then a
    single tick lands on the day boundary and runs one evaluation.
    """
    base = day * DAY_S
    for index in range(count):
        ts = base + (index + 1) * (DAY_S / (count + 2))
        for gate, peak in profile.items():
            classifier.observe(_episode(gate, ts, peak=peak))
    classifier.tick(base + DAY_S)


def _feed_day_open(
    classifier: GateModel,
    day: int,
    profile: dict[int, int],
    *,
    open_gates: tuple[int, ...],
    count: int = 12,
) -> tuple[object, ...]:
    """:func:`_feed_day` with gates reported as still having an episode open."""
    base = day * DAY_S
    for index in range(count):
        ts = base + (index + 1) * (DAY_S / (count + 2))
        for gate, peak in profile.items():
            classifier.observe(_episode(gate, ts, peak=peak))
    return classifier.tick(base + DAY_S, open_gates=open_gates)[1]


def _classifier(**overrides: object) -> GateModel:
    """A classifier whose evaluation interval is exactly one day."""
    config = DetectorConfig(class_eval_interval_s=DAY_S, **overrides)  # type: ignore[arg-type]
    return make_gates(config)


WALL_PROFILE = {
    **dict.fromkeys(range(5), IN_ROOM_ENERGY),
    **dict.fromkeys(range(5, GATE_COUNT), WALL_ENERGY),
}
"""Gates 0-4 in the room, 5-8 seen through a wall: the boundary is gate 4."""


def test_wall_profile_confirms_the_boundary_after_the_persistence_window() -> None:
    """Spec 21 §2: a sustained ceiling drop at gate 5 puts the boundary at 4.

    And it does not put it there on day one. The whole point of
    ``boundary_confirm_days`` is that a boundary is a claim about the house,
    not about yesterday.
    """
    classifier = _classifier()

    _feed_day(classifier, 0, WALL_PROFILE)
    assert classifier.boundary_gate is None
    assert classifier.confirmed_days == 1

    _feed_day(classifier, 1, WALL_PROFILE)
    assert classifier.boundary_gate is None
    assert classifier.confirmed_days == 2

    transitions = classifier.tick(3 * DAY_S)[1]
    assert classifier.confirmed_days == 3
    assert classifier.boundary_gate == 4
    assert [(t.previous, t.current, t.deferred) for t in transitions] == [
        (None, 4, False)
    ]

    profile = classifier.ceil_profile
    assert profile[4] is not None and profile[4] > 0.9
    assert profile[5] is not None and profile[5] < 0.45


def test_insufficient_episode_counts_produce_no_boundary() -> None:
    """Spec 21 §2: below ``n_ceil_min`` the question is not even asked.

    A gate nobody has walked past has no ceiling, and treating its silence as
    "low energy" is exactly how a sensor invents a wall across an empty room.
    """
    classifier = _classifier()

    for day in range(3):
        _feed_day(classifier, day, WALL_PROFILE, count=3)

    assert all(
        stat.n_epi(3 * DAY_S) < 10.0
        for stat in classifier.stats
    )
    assert classifier.boundary_gate is None
    assert classifier.confirmed_days == 0


def test_a_lone_low_ceiling_gate_mid_room_is_not_a_boundary() -> None:
    """Spec 21 §2 rationale: a wall attenuates *everything* past it.

    Gate 3 here is the strip of floor between the sofa and the window that
    nobody ever walks along - low ceiling, but the gates beyond it are as hot
    as ever, so it is a quiet gate and not a wall.
    """
    classifier = _classifier()
    profile = dict.fromkeys(range(GATE_COUNT), IN_ROOM_ENERGY)
    profile[3] = WALL_ENERGY

    for day in range(6):
        _feed_day(classifier, day, profile)

    assert classifier.boundary_gate is None
    assert classifier.ceil_profile[3] is not None
    assert classifier.ceil_profile[3] < 0.45


def test_a_wall_is_found_through_a_gate_that_has_no_evidence() -> None:
    """Spec 21 §2: a gate without episodes is skipped, not read as low.

    Gate 6 here is never walked past. It must neither block the wall at gate 5
    from being seen nor count as evidence for it.
    """
    profile = {gate: peak for gate, peak in WALL_PROFILE.items() if gate != 6}
    classifier = _classifier()
    for day in range(4):
        _feed_day(classifier, day, profile)

    assert classifier.boundary_gate == 4
    assert classifier.ceil_profile[6] is None


def test_a_never_occupied_nearest_gate_does_not_block_the_inference() -> None:
    """A wall-mounted sensor's gate 0 covers the volume nobody stands in.

    Months of traffic can leave it with a single episode, and the boundary
    still has to be inferable from the gates that do see people.
    """
    profile = {gate: peak for gate, peak in WALL_PROFILE.items() if gate != 0}
    classifier = _classifier()
    for day in range(4):
        _feed_day(classifier, day, profile)

    assert classifier.boundary_gate == 4
    assert classifier.ceil_profile[0] is None


def test_too_few_fittable_gates_produce_no_boundary() -> None:
    """Spec 21 §2.1: two points fit any line, so two points decide nothing."""
    classifier = _classifier()
    for day in range(4):
        _feed_day(classifier, day, {3: IN_ROOM_ENERGY, 4: WALL_ENERGY})

    assert classifier.boundary_gate is None
    assert classifier.confirmed_days == 0
    assert classifier.ceil_profile == (None,) * GATE_COUNT


def test_saturated_gates_are_left_out_of_the_falloff_fit() -> None:
    """Spec 21 §2.1: a clipped gate is a lower bound, not a ceiling.

    The near band here is pinned at the top of the sensor's scale, so what it
    would have reached is unknown and it cannot say anything about the slope.
    The wall at gate 6 is found from the gates that are not clipped, and moving
    the clipped values around changes nothing.
    """
    clipped = _classifier()
    for day in range(4):
        _feed_day(clipped, day, dict(enumerate([100, 100, 100, 80, 70, 62, 7, 6, 5])))

    other_clipping = _classifier()
    for day in range(4):
        _feed_day(
            other_clipping, day, dict(enumerate([96, 99, 100, 80, 70, 62, 7, 6, 5]))
        )

    assert clipped.boundary_gate == 5
    assert other_clipping.boundary_gate == 5
    assert clipped.ceil_profile[3:] == other_clipping.ceil_profile[3:]


def test_gates_zero_and_one_can_never_be_cut_off() -> None:
    """Spec 21 §2 fixes ``k >= 2``: the two nearest gates are never suppressed.

    A sensor that has decided the room ends 75 cm in front of itself has
    misread something, and the failure mode - never detecting anyone - is far
    worse than the through-wall dwell the ceiling exists to fix.
    """
    classifier = _classifier()
    profile = {0: IN_ROOM_ENERGY}
    profile.update(dict.fromkeys(range(1, GATE_COUNT), WALL_ENERGY))

    for day in range(6):
        _feed_day(classifier, day, profile)

    assert classifier.boundary_gate == 1


def _falloff_profile(exponent: float, *, saturated_to: int) -> dict[int, int]:
    """A pure free-space profile: energy falling as a power of range, no wall."""
    reference = (saturated_to + 0.5) * GATE_SPACING_M
    return {
        gate: min(
            MAX_GATE_ENERGY,
            round(
                MAX_GATE_ENERGY
                * (reference / ((gate + 0.5) * GATE_SPACING_M)) ** exponent
            ),
        )
        for gate in range(GATE_COUNT)
    }


def test_free_space_falloff_alone_is_not_a_boundary() -> None:
    """Spec 21 §5.0: an open room must not read as a walled one.

    Radar return energy falls with range whether or not there is a wall, so a
    threshold on the raw profile is a distance threshold wearing a wall's
    clothes: it would cut every sensor's room off at whatever range the slope
    happens to cross ``ceil_drop``. The profiles below are that slope and
    nothing else - one open room, near gates clipped at the sensor's 0-100
    ceiling - and each must leave the whole range in-room.
    """
    for exponent in (1.0, 2.0, 4.0):
        profile = _falloff_profile(exponent, saturated_to=5)
        assert profile[6] > profile[7] > profile[8]  # a smooth slope, not a step

        classifier = _classifier()
        for day in range(4):
            _feed_day(classifier, day, profile)

        assert classifier.boundary_gate is None
        assert classifier.confirmed_days == 4
        compensated = [value for value in classifier.ceil_profile[6:] if value is not None]
        assert compensated and all(value > 0.9 for value in compensated)


def test_a_wall_on_top_of_the_falloff_is_still_found() -> None:
    """Spec 21 §2: what marks the wall is attenuation the falloff cannot explain.

    The same slope as the free-space case, with a tenfold extra loss from gate
    5 outward - two-way transmission through plasterboard - and the boundary
    lands on the last gate in front of it.
    """
    wall_gate = 5
    profile = {
        gate: max(1, round(peak / 10)) if gate >= wall_gate else peak
        for gate, peak in _falloff_profile(1.0, saturated_to=1).items()
    }

    classifier = _classifier()
    for day in range(4):
        _feed_day(classifier, day, profile)

    assert classifier.boundary_gate == wall_gate - 1
    profile_e = classifier.ceil_profile
    assert profile_e[wall_gate - 1] is not None and profile_e[wall_gate - 1] > 0.9
    assert all(
        value is not None and value < 0.45 for value in profile_e[wall_gate:]
    )


def test_a_flapping_candidate_never_confirms() -> None:
    """Spec 21 §2.3: a boundary that disagrees with itself takes no effect.

    Gate 5 sits astride ``ceil_drop`` here. Its own ceiling creeps up as
    stronger traffic crosses it, and so does the falloff trend it is measured
    against as the room's near gates see stronger passes - so which side of the
    threshold gate 5 lands on alternates day by day. Nothing about the house has
    changed; only which ceiling moved most recently has. That is precisely the
    case the persistence window exists to refuse, and the assertion is that it
    refuses it rather than picking one at random.
    """
    classifier = _classifier()
    schedule = [(60, 24), (70, 24), (70, 28), (80, 28), (80, 32), (90, 32), (90, 36)]

    candidates: list[object] = []
    for day, (in_room, straddle) in enumerate(schedule):
        profile = dict.fromkeys(range(5), in_room)
        profile[5] = straddle
        profile.update(dict.fromkeys(range(6, GATE_COUNT), 12))
        _feed_day(classifier, day, profile)
        candidates.append(classifier.pending_boundary)
        assert classifier.confirmed_days < 3

    assert candidates == [5, 4, 5, 4, 5, 4, 5]
    assert classifier.boundary_gate is None


def test_max_gate_outranks_a_learned_boundary() -> None:
    """Spec 21 §3: manual cap first, then the learned boundary, then evidence."""
    classifier = _classifier(ceiling_enabled=True, max_gate=2)
    for day in range(4):
        _feed_day(classifier, day, WALL_PROFILE)

    assert classifier.boundary_gate == 4
    # The cap is stricter than the boundary, and wins.
    assert classifier.gate_class(3) == CLASS_OUT
    assert classifier.gate_class(4) == CLASS_OUT

    # Lift the cap and the learned boundary is what remains in force.
    classifier.reconfigure(
        DetectorConfig(class_eval_interval_s=DAY_S, ceiling_enabled=True)
    )
    assert classifier.gate_class(4) != CLASS_OUT
    assert classifier.gate_class(5) == CLASS_OUT


def test_a_boundary_retreat_waits_for_an_open_episode_to_close() -> None:
    """Spec 21 §3: never suppress a gate the sensor is watching right now.

    The retreat is driven here by tightening ``ceil_drop``, which is how a
    retreat realistically happens: a gate's *ceiling* is a decayed q99 and so
    is close to monotonic - a gate that has once been seen near-saturated goes
    on reading near-saturated for many half-lives - while the threshold it is
    compared against is one option away from moving at any time.
    """
    mid = {
        **dict.fromkeys(range(5), IN_ROOM_ENERGY),
        5: 50,
        6: 50,
        **dict.fromkeys(range(7, GATE_COUNT), WALL_ENERGY),
    }
    classifier = _classifier(ceiling_enabled=True)
    for day in range(4):
        _feed_day(classifier, day, mid)
    assert classifier.boundary_gate == 6

    # 50/90 is 0.55: inside a 0.45 drop, outside a 0.70 one.
    classifier.reconfigure(
        DetectorConfig(
            class_eval_interval_s=DAY_S, ceiling_enabled=True, ceil_drop=0.70
        )
    )

    # Somebody is sitting at gate 6 through every evaluation that follows.
    for day in range(4, 8):
        transitions = _feed_day_open(classifier, day, mid, open_gates=(6,))
        for transition in transitions:
            assert transition.deferred is True
            assert transition.current == 4
        assert classifier.boundary_gate == 6
        assert classifier.gate_class(6) != CLASS_OUT

    deferrals = classifier.tick(8 * DAY_S, open_gates=(6,))[1]
    assert deferrals == ()  # the deferral is reported once, not every frame

    # They get up; the retreat lands on the very next tick.
    transitions = classifier.tick(8 * DAY_S + 1.0, open_gates=())[1]
    assert [(t.previous, t.current, t.deferred) for t in transitions] == [(6, 4, False)]
    assert classifier.boundary_gate == 4
    assert classifier.gate_class(6) == CLASS_OUT


def test_disabled_ceiling_learns_everything_and_suppresses_nothing() -> None:
    """Spec 21 §5: the statistics and the boundary ship on; the effect does not."""
    disabled = _classifier()
    enabled = _classifier(ceiling_enabled=True)
    for day in range(4):
        for classifier in (disabled, enabled):
            _feed_day(classifier, day, WALL_PROFILE)
    # A through-wall dwell: gate 7 classifies IN_ROOM on the spec 20 evidence,
    # so what differs below is the ceiling's doing and nothing else.
    for classifier in (disabled, enabled):
        classifier.observe(
            _episode(7, 4 * DAY_S, peak=25, duration_s=180.0, still_frac=0.9)
        )

    # Same evidence, same learned boundary, same published profile.
    assert disabled.boundary_gate == enabled.boundary_gate == 4
    assert disabled.ceil_profile == enabled.ceil_profile
    assert disabled.confirmed_days == enabled.confirmed_days

    # Only the effect differs.
    assert disabled.stats[7].gate_class == enabled.stats[7].gate_class == CLASS_IN_ROOM
    assert enabled.gate_class(7) == CLASS_OUT
    assert disabled.gate_class(7) == CLASS_IN_ROOM
    assert enabled.excluded(7)
    assert not disabled.excluded(7)


def test_ceiling_state_survives_a_serialisation_round_trip() -> None:
    """Histograms, boundary and confirmation run all persist."""
    classifier = _classifier(ceiling_enabled=True)
    for day in range(4):
        _feed_day(classifier, day, WALL_PROFILE)
    classifier.observe(_episode(6, 4 * DAY_S, peak=70, duration_s=90.0, still_frac=0.9))

    restored = GateModel.from_dict(
        json.loads(json.dumps(classifier.to_dict())), classifier._config
    )

    assert restored.boundary_gate == classifier.boundary_gate == 4
    assert restored.confirmed_days == classifier.confirmed_days
    assert restored.ceil_profile == classifier.ceil_profile
    assert restored.classes == classifier.classes
    for gate in range(GATE_COUNT):
        assert restored.stats[gate].ceil_bins == classifier.stats[gate].ceil_bins
        assert restored.stats[gate].ceil_q() == classifier.stats[gate].ceil_q()

    # And it keeps confirming from where it left off rather than restarting.
    _feed_day(restored, 5, WALL_PROFILE)
    assert restored.boundary_gate == 4


def test_pre_ceiling_state_restores_with_the_dwell_statistics_intact() -> None:
    """A v1 payload keeps its month of dwell evidence and starts the ceiling empty.

    Rejecting it instead would make the upgrade cost every gate its learned
    class, which is a real regression in exchange for nothing.
    """
    classifier = _classifier()
    _feed_day(classifier, 0, WALL_PROFILE)
    classifier.observe(_episode(3, DAY_S, peak=88, duration_s=120.0, still_frac=0.9))

    legacy = classifier.to_dict()
    legacy["version"] = 1
    for gate in legacy["gates"]:
        gate.pop("ceil_bins")
    legacy.pop("boundary_gate")
    legacy.pop("pending_boundary")
    legacy.pop("pending_evaluated")
    legacy.pop("confirm_count")
    legacy.pop("last_boundary_eval_ts")

    restored = GateModel.from_dict(legacy, classifier._config)

    assert restored.stats[3].gate_class == CLASS_IN_ROOM
    assert restored.stats[3].n_sustained == 1.0
    assert restored.boundary_gate is None
    assert restored.ceil_profile == (None,) * GATE_COUNT


# -- End-to-end: a real detector on a synthetic wall ---------------------------

WALL_GATE = 5
"""First gate on the far side of the synthetic wall."""


def _wall_detector(**overrides: object) -> Detector:
    """A detector on the long baseline window the dwell tests use.

    ``hold_s`` also sets the episode close window, and these scenarios leave
    eight to twenty seconds of quiet between events, so it is short enough for
    each one to close on its own.
    """
    values: dict[str, object] = {
        "baseline_window_s": 3600.0,
        "class_eval_interval_s": 60.0,
        "hold_s": 2.0,
        "arrival_frac": 0.0,
    }
    values.update(overrides)
    return make_detector(make_config(**values), bucket_s=60.0)  # type: ignore[arg-type]


def _walk_the_room(stream: FrameStream, detector: Detector, *, passes: int) -> None:
    """Walk the whole range repeatedly, attenuated past the wall.

    Each gate gets its own brief episode per pass, so every gate accumulates
    the episode count the boundary inference needs, and the raw energies carry
    the attenuation profile the ceiling is supposed to read.
    """
    for _ in range(passes):
        for gate in range(GATE_COUNT):
            elevation = 80 if gate < WALL_GATE else 17
            feed(detector, stream.burst(2.0, move={gate: elevation}))
            feed(detector, stream.burst(8.0))


def test_wall_attenuation_learns_the_boundary_and_suppresses_beyond_it() -> None:
    """Spec 21 §3, end to end: the island dwell stops entering, the real one does not.

    This is the case spec 20 §7.3 documents as unfixable from dwell character
    alone - somebody sitting still behind a wall looks exactly like somebody
    sitting still in front of one. The ceiling is what tells them apart, and
    the test only means anything because the far gate does still classify
    IN_ROOM on the dwell evidence: the suppression has to be the boundary's
    doing, not the dwell rule's.
    """
    stream = FrameStream(sigma=2.0)
    detector = _wall_detector(ceiling_enabled=True)
    feed(detector, stream.burst(300.0))
    assert detector.baseline.ready

    _walk_the_room(stream, detector, passes=14)

    assert detector.gates.boundary_gate == WALL_GATE - 1
    profile = detector.gates.ceil_profile
    assert profile[WALL_GATE - 1] is not None and profile[WALL_GATE - 1] > 0.9
    assert all(value is not None and value < 0.45 for value in profile[WALL_GATE:])

    # The kitchen island on the far side of the wall: a full still dwell.
    feed(detector, stream.burst(120.0))
    island = feed(detector, stream.burst(180.0, still={6: 8, 7: 25}))
    feed(detector, stream.burst(20.0))
    assert not any(output.occupied for output in island)
    assert all(output.score == 0.0 for output in island)
    # It was suppressed by the boundary, not by the dwell statistics: the gate
    # itself learned exactly what spec 20 said it would.
    assert detector.gates.stats[7].gate_class == CLASS_IN_ROOM
    assert detector.gates.gate_class(7) == CLASS_OUT

    # And the armchair at gate 3, on this side of it, is untouched.
    feed(detector, stream.burst(120.0))
    in_room = feed(detector, stream.burst(180.0, still={2: 8, 3: 25}))
    feed(detector, stream.burst(20.0))
    assert any(output.occupied for output in in_room)
    assert detector.gates.gate_class(3) == CLASS_IN_ROOM


def test_the_same_wall_with_the_ceiling_disabled_still_admits_the_island() -> None:
    """Spec 21 §5: shipped disabled means shipped behaving exactly as before."""
    stream = FrameStream(sigma=2.0)
    detector = _wall_detector()
    feed(detector, stream.burst(300.0))
    _walk_the_room(stream, detector, passes=14)

    # Learned all the same things...
    assert detector.gates.boundary_gate == WALL_GATE - 1
    assert detector.gates.stats[7].n_epi(stream.ts) >= detector.config.n_ceil_min

    # ...and acts on none of them.
    feed(detector, stream.burst(120.0))
    island = feed(detector, stream.burst(180.0, still={6: 8, 7: 25}))
    feed(detector, stream.burst(20.0))
    assert any(output.occupied for output in island)
    assert detector.gates.gate_class(7) == CLASS_IN_ROOM


def test_episodes_carry_the_raw_move_peak_not_the_residual() -> None:
    """Spec 21 §1: the ceiling is absolute physics, so it reads the raw frame.

    A residual would drift with the noise floor the baseline learns, which is
    exactly the thing the ceiling must not depend on.
    """
    stream = FrameStream(sigma=2.0)
    detector = _wall_detector()
    feed(detector, stream.burst(300.0))

    outputs = feed(detector, stream.burst(3.0, move={4: 60}))
    outputs.extend(feed(detector, stream.burst(20.0)))

    gate_episodes = [
        episode
        for output in outputs
        for episode in output.episodes
        if episode.scope == SCOPE_GATE and episode.gate == 4
    ]
    assert len(gate_episodes) == 1
    episode = gate_episodes[0]
    # floor 5 + elevation 60, plus a little noise: nowhere near the residual,
    # which is a z-score in the tens.
    assert 58 <= episode.gate_peaks[4] <= 72
    # The residual is a z-score against the noise floor and is on a wholly
    # different scale; using it here would make the ceiling drift with the
    # baseline.
    assert episode.peak_residual > 20.0
    assert sum(episode.gate_peaks) == episode.gate_peaks[4]
