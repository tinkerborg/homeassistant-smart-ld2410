"""Tests for dwell-character gate classification (spec 20).

Spec 20 §7 lists the validation items; these are those items driven by
synthetic streams so they run in the unit suite. The replay-against-recordings
half of §7 lives outside pytest.
"""

from __future__ import annotations

import json
from math import log2

import pytest

from custom_components.smart_ld2410.algo.gates import GateModel
from custom_components.smart_ld2410.algo.detector import Detector
from custom_components.smart_ld2410.algo.types import (
    CLASS_BLEED,
    CLASS_IN_ROOM,
    CLASS_OUT,
    CLASS_PORTAL,
    CLASS_UNKNOWN,
    SCOPE_DETECTION,
    SCOPE_GATE,
    DetectorOutput,
    Episode,
)

from . import FrameStream, feed, make_config, make_detector, make_gates

SWEEP_GATES = (6, 7, 8)
"""Far gates used as the through-wall hallway in these tests."""

SWEEP = dict.fromkeys(SWEEP_GATES, 40)
"""A body's worth of move energy on the far gates."""

DWELL = {6: 8, 7: 25}
"""A person settling at gate 7: still-channel energy with a little spill."""


def _stream() -> FrameStream:
    """A synthetic sensor whose idle spread is not pinned to ``min_mad``.

    The default test stream is quiet enough that its measured ``q90 - q50``
    hits the configured minimum, which inflates idle residuals until they
    graze ``s_gate_off``. Episode boundaries would then be an artefact of the
    test rig rather than of the algorithm.
    """
    return FrameStream(sigma=2.0)


def _detector(**overrides: float | None) -> Detector:
    """A detector whose baseline window can outlast a minute-long dwell.

    The shared test default is a 60 s window, so a 60 s dwell is a quarter of
    it and the quantile floor starts absorbing the person mid-episode. An
    hour-long window of minute buckets is the smallest thing that behaves
    like the real 12 h default here.

    ``hold_s`` also sets the episode close window, and these scenarios space
    their pass-bys eight seconds apart, so it is short enough for each one to
    close on its own.
    """
    values: dict[str, float | None] = {"baseline_window_s": 3600.0, "hold_s": 2.0}
    values.update(overrides)
    return make_detector(make_config(**values), bucket_s=60.0)


def _warm(stream: FrameStream, detector: Detector) -> None:
    """Feed enough idle frames for the baseline to become usable."""
    feed(detector, stream.burst(300.0))
    assert detector.baseline.ready


def _sweep(
    stream: FrameStream,
    detector: Detector,
    *,
    passes: int,
    duration_s: float = 2.0,
    quiet_s: float = 8.0,
    move: dict[int, int] | None = None,
) -> list[DetectorOutput]:
    """Walk past the far gates ``passes`` times, with quiet gaps between."""
    outputs: list[DetectorOutput] = []
    for _ in range(passes):
        outputs.extend(feed(detector, stream.burst(duration_s, move=move or SWEEP)))
        outputs.extend(feed(detector, stream.burst(quiet_s)))
    return outputs


def _gate_episodes(outputs: list[DetectorOutput], gate: int) -> list[Episode]:
    """Every closed per-gate episode for ``gate`` in a run of outputs."""
    return [
        episode
        for output in outputs
        for episode in output.episodes
        if episode.scope == SCOPE_GATE and episode.gate == gate
    ]


def test_repeated_pass_bys_reach_bleed_and_are_then_rejected_at_entry() -> None:
    """Spec 20 §7.1: brief sweeps make a gate bleed, and bleed rejects entry.

    The rejection has to happen in the scoring, not merely in hysteresis: the
    score itself must be zero, because a pass-by that scores and is then held
    off by a threshold is one noisy frame away from a false entry.
    """
    stream = _stream()
    detector = _detector()
    _warm(stream, detector)

    # Early sweeps look exactly like a person and do enter - nothing has been
    # learned yet, and the permissive default is the point.
    first = _sweep(stream, detector, passes=1)
    assert any(output.occupied for output in first)
    assert detector.gates.classes == "U" * 9

    outputs = _sweep(stream, detector, passes=30)

    for gate in SWEEP_GATES:
        episodes = _gate_episodes(outputs, gate)
        assert len(episodes) >= 20
        assert all(
            episode.duration_s <= detector.config.t_brief_s for episode in episodes
        )
        assert all(episode.still_frac < 0.5 for episode in episodes)
        assert detector.gates.gate_class(gate) == CLASS_BLEED
    assert detector.gates.classes == "UUUUUUBBB"
    assert detector.gates.last_in_room_gate is None
    # The demotions were reported for the caller to log.
    demotions = [
        transition
        for output in outputs
        for transition in output.gate_transitions
        if transition.current == CLASS_BLEED
    ]
    assert {transition.gate for transition in demotions} == set(SWEEP_GATES)

    # Let the hold expire so entry scoring is what is being tested.
    released = feed(detector, stream.burst(60.0))
    assert not released[-1].occupied

    rejected = _sweep(stream, detector, passes=3)
    assert not any(output.occupied for output in rejected)
    assert all(output.score == 0.0 for output in rejected)
    assert all(output.active_gates == () for output in rejected)
    # Bleed gates still stream residuals and still record episodes, so a
    # reclassification later has the data it needs.
    assert max(output.residuals_move[7] for output in rejected) > detector.config.k
    assert _gate_episodes(rejected, 7)


def test_a_single_sustained_dwell_classifies_a_rare_zone_in_room() -> None:
    """Spec 20 §7.2: one dwell at an unused far gate is enough, immediately."""
    stream = _stream()
    detector = _detector()
    _warm(stream, detector)
    assert detector.gates.gate_class(7) == CLASS_UNKNOWN

    # Somebody sits down in the rarely-used corner: still-channel energy on
    # gate 7 with a little spill, for two minutes.
    dwell = feed(detector, stream.burst(120.0, still=DWELL))
    assert any(output.occupied for output in dwell)
    closing = feed(detector, stream.burst(20.0))

    episodes = _gate_episodes(dwell + closing, 7)
    assert len(episodes) == 1
    assert episodes[0].duration_s >= detector.config.t_dwell_s
    assert episodes[0].still_frac > 0.5
    assert detector.gates.gate_class(7) == CLASS_IN_ROOM
    assert detector.gates.last_in_room_gate == 7
    assert detector.gates.stats[7].n_sustained == 1.0

    # And from then on brief events there count toward occupancy, which is the
    # half of the rare-zone requirement that bleed classification would break.
    feed(detector, stream.burst(60.0))
    brief = feed(detector, stream.burst(2.0, move={6: 40, 7: 40}))
    assert brief[-1].occupied


def test_a_move_dominated_dwell_still_promotes_at_the_dwell_time() -> None:
    """A dwell is a minute of elevation, whichever channel carries it.

    A body at rest breathes, so the move channel keeps firing and the still
    channel does not dominate. This is the shape real dwells have.
    """
    stream = _stream()
    detector = _detector()
    _warm(stream, detector)

    dwell = feed(detector, stream.burst(70.0, move={6: 8, 7: 25}))
    closing = feed(detector, stream.burst(20.0))

    episodes = _gate_episodes(dwell + closing, 7)
    assert len(episodes) == 1
    assert episodes[0].still_frac < 0.1
    assert episodes[0].duration_s >= detector.config.t_dwell_s
    assert episodes[0].active_frac == pytest.approx(1.0, abs=0.05)
    assert detector.gates.gate_class(7) == CLASS_IN_ROOM
    assert detector.gates.stats[7].n_sustained == 1.0


def test_an_entered_detection_episode_closes_when_occupancy_releases() -> None:
    """The band's episode ends with the occupancy, not with the last hot gate.

    A gate left hovering above ``s_gate_off`` after everyone has gone is
    ordinary in a real room, and waiting for it is what leaves an episode open
    for days.
    """
    stream = _stream()
    detector = _detector(hold_s=5.0)
    _warm(stream, detector)

    entered = feed(detector, stream.burst(30.0, still={6: 8, 7: 25}))
    assert any(output.occupied for output in entered)

    # Weak enough to score nothing, strong enough to hold gate 7's episode
    # open: occupancy releases while that episode is still running.
    tail = feed(detector, stream.burst(40.0, still={7: 6}))
    assert tail[0].occupied
    assert not tail[-1].occupied
    assert all(output.score == 0.0 for output in tail)
    assert detector._episodes.open_gates == (7,)  # noqa: SLF001

    detection = [
        episode
        for output in tail
        for episode in output.episodes
        if episode.scope == SCOPE_DETECTION
    ]
    assert len(detection) == 1
    assert detection[0].result == "entered"
    assert detection[0].duration_s < 40.0


def test_a_stalled_stream_closes_episodes_at_the_last_frame_before_the_gap() -> None:
    """A dead link must not be recorded as an hours-long dwell."""
    stream = _stream()
    detector = _detector()
    _warm(stream, detector)

    feed(detector, stream.burst(70.0, still={6: 8, 7: 25}))
    stream.skip(6 * 3600.0)
    resumed = feed(detector, stream.burst(1.0))

    episodes = _gate_episodes(resumed, 7)
    assert len(episodes) == 1
    assert (
        detector.config.t_dwell_s
        <= episodes[0].duration_s
        < detector.config.t_dwell_s + 20.0
    )
    # The classifier sees the bounded episode, and it is enough to promote.
    assert detector.gates.gate_class(7) == CLASS_IN_ROOM


def test_a_dip_inside_a_dwell_does_not_split_it() -> None:
    """The dwell clock tolerates the same low-signal gap occupancy does."""
    stream = _stream()
    detector = _detector(hold_s=10.0)
    _warm(stream, detector)

    dwell = feed(detector, stream.burst(30.0, still={6: 8, 7: 25}))
    dwell.extend(feed(detector, stream.burst(8.0)))
    dwell.extend(feed(detector, stream.burst(30.0, still={6: 8, 7: 25})))
    dwell.extend(feed(detector, stream.burst(30.0)))

    episodes = _gate_episodes(dwell, 7)
    assert len(episodes) == 1
    assert episodes[0].duration_s >= detector.config.t_dwell_s
    assert episodes[0].active_frac >= detector.config.active_frac_min
    assert detector.gates.gate_class(7) == CLASS_IN_ROOM


def test_chained_pass_bys_inside_the_gap_do_not_stack_into_a_dwell() -> None:
    """Sweeps bridged by sub-``gap_close_s`` quiet are not a body sitting down."""
    stream = _stream()
    detector = _detector(hold_s=10.0)
    _warm(stream, detector)

    outputs: list[DetectorOutput] = []
    for _ in range(8):
        outputs.extend(feed(detector, stream.burst(2.0, move=SWEEP)))
        outputs.extend(feed(detector, stream.burst(7.0)))
    outputs.extend(feed(detector, stream.burst(30.0)))

    episodes = _gate_episodes(outputs, 7)
    assert len(episodes) == 1
    assert episodes[0].duration_s >= detector.config.t_dwell_s
    assert episodes[0].active_frac < detector.config.active_frac_min
    assert detector.gates.stats[7].n_sustained == 0.0
    assert detector.gates.gate_class(7) == CLASS_UNKNOWN


def test_through_wall_sustained_dwell_classifies_in_room() -> None:
    """Spec 20 §7.3: the kitchen-island case is NOT fixed by dwell statistics.

    This asserts the documented limit rather than a fix: somebody sitting
    still on the far side of a wall produces exactly the episode character of
    somebody sitting still inside the room, and nothing in spec 20 can tell
    them apart. Spec 21 (energy ceiling) or ``max_gate`` is the answer; if
    this test ever starts failing, one of those landed and the limit moved.
    """
    stream = _stream()
    detector = _detector()
    _warm(stream, detector)

    feed(detector, stream.burst(120.0, still={7: 8, 8: 25}))
    feed(detector, stream.burst(20.0))

    assert detector.gates.gate_class(8) == CLASS_IN_ROOM


def test_max_gate_override_forces_out_and_excludes_from_scoring() -> None:
    """Spec 20 §4: the manual cap outranks the evidence, at the entry stage."""
    stream = _stream()
    detector = _detector(max_gate=5)
    _warm(stream, detector)
    assert detector.gates.classes == "UUUUUUOOO"

    # The same sustained dwell that classified in-room above.
    dwell = feed(detector, stream.burst(120.0, still={7: 8, 8: 25}))
    feed(detector, stream.burst(20.0))

    assert not any(output.occupied for output in dwell)
    assert all(output.score == 0.0 for output in dwell)
    assert detector.gates.gate_class(8) == CLASS_OUT
    assert detector.gates.last_in_room_gate is None
    # The evidence was still collected - dropping the cap must re-enable the
    # gate without relearning it from scratch.
    assert detector.gates.stats[8].n_sustained == 1.0

    detector.reconfigure(make_config(baseline_window_s=3600.0, max_gate=None))
    detector.gates.evaluate(stream.ts)
    assert detector.gates.gate_class(8) == CLASS_IN_ROOM


def test_bleed_demotion_follows_the_statistics_half_life() -> None:
    """A gate stops being bleed as its decayed brief count falls away.

    Bleed is a statement about *current* traffic, so the count that supports
    it has to be the decayed one: a hallway that gets walled off must stop
    being suppressed. The half-life is compressed to five minutes here so the
    decay can be measured directly rather than asserted about in the
    abstract; the mechanism is identical at the 30-day default, and it runs
    entirely on frame time.
    """
    half_life_s = 300.0
    stream = _stream()
    detector = _detector(
        stats_half_life_days=half_life_s / 86400.0, class_eval_interval_s=30.0
    )
    _warm(stream, detector)
    _sweep(stream, detector, passes=45, duration_s=1.5, quiet_s=5.0)

    stats = detector.gates.stats[7]
    at_peak = stats.decayed(stream.ts)[1]
    assert at_peak >= detector.config.n_bleed_min
    assert detector.gates.gate_class(7) == CLASS_BLEED

    def idle(seconds: float) -> float:
        feed(detector, stream.burst(seconds))
        return stats.decayed(stream.ts)[1]

    # Time for the decayed count to fall to the bleed threshold, from the
    # half-life alone. Nothing else may move it: no new episodes, no clock.
    expiry_s = half_life_s * log2(at_peak / detector.config.n_bleed_min)
    assert expiry_s > detector.config.class_eval_interval_s

    early = idle(expiry_s * 0.6)
    assert early == pytest.approx(
        at_peak * 0.5 ** (expiry_s * 0.6 / half_life_s), rel=1e-3
    )
    assert early > detector.config.n_bleed_min
    assert detector.gates.gate_class(7) == CLASS_BLEED

    late = idle(expiry_s * 0.6)
    assert late == pytest.approx(
        at_peak * 0.5 ** (expiry_s * 1.2 / half_life_s), rel=1e-3
    )
    assert late < detector.config.n_bleed_min

    # Decay alone demotes, so the demotion lands on the periodic
    # re-evaluation rather than on an episode close.
    idle(detector.config.class_eval_interval_s)
    assert detector.gates.gate_class(7) == CLASS_UNKNOWN

    # Demotion is a return to permissive: the gate can enter the room again.
    assert any(output.occupied for output in _sweep(stream, detector, passes=1))


def test_classifier_state_survives_a_serialisation_round_trip() -> None:
    """to_dict/from_dict preserves counts, classes and decay bookkeeping."""
    stream = _stream()
    detector = _detector()
    _warm(stream, detector)
    _sweep(stream, detector, passes=25)
    feed(detector, stream.burst(120.0, still={2: 8, 3: 25}))
    feed(detector, stream.burst(20.0))

    state = json.loads(json.dumps(detector.state_to_dict()))
    restored = Detector.gates_from_state(state, detector.config)

    assert restored is not None
    assert restored.classes == detector.gates.classes
    assert restored.last_in_room_gate == detector.gates.last_in_room_gate
    assert restored.boundary_gate == detector.gates.boundary_gate
    for gate in range(9):
        before = detector.gates.stats[gate]
        after = restored.stats[gate]
        assert after.n_brief == before.n_brief
        assert after.n_sustained == before.n_sustained
        assert after.last_sustained_ts == before.last_sustained_ts
        assert after.updated_ts == before.updated_ts

    # And a detector rebuilt on it keeps rejecting what it had learned to.
    revived = Detector(
        detector.config,
        baseline=detector.baseline,
        gates=restored,
        bucket_s=60.0,
        min_buckets=5,
    )
    feed(revived, stream.burst(60.0))
    assert not any(output.occupied for output in _sweep(stream, revived, passes=2))


def test_state_without_gate_stats_restores_as_permissive() -> None:
    """Baseline state written before this phase loads with every gate unknown."""
    detector = make_detector()
    legacy = detector.baseline.to_dict()

    assert Detector.gates_from_state(legacy, detector.config) is None
    assert make_gates(detector.config).classes == "U" * 9


def test_detection_scope_episode_carries_the_band_and_centroid() -> None:
    """The contract row needs a band that moves; a single gate cannot give one."""
    stream = _stream()
    detector = _detector()
    _warm(stream, detector)

    outputs = feed(detector, stream.burst(2.0, move={2: 40, 3: 40}))
    outputs.extend(feed(detector, stream.burst(2.0, move={5: 40, 6: 40})))
    outputs.extend(feed(detector, stream.burst(20.0)))

    detection = [
        episode
        for output in outputs
        for episode in output.episodes
        if episode.scope == SCOPE_DETECTION
    ]
    assert len(detection) == 1
    episode = detection[0]
    assert (episode.gate_lo, episode.gate_hi) == (2, 6)
    assert 2.0 < episode.centroid_mean < 6.0
    assert episode.centroid_vel > 0.0  # the band moved outward
    assert episode.result == "entered"
    assert episode.still_frac < 0.5


DOOR_GATES = (2, 3)
"""Near gates standing in for a doorway in the portal tests."""

DOOR = dict.fromkeys(DOOR_GATES, 40)
"""A body's worth of move energy on the doorway gates."""


def _classifier(**overrides: float | None) -> GateModel:
    """A classifier whose bleed threshold is out of reach unless asked for."""
    values: dict[str, float | None] = {"n_bleed_min": 100.0}
    values.update(overrides)
    return make_gates(make_config(**values))


def _episode(gate: int, t0: float, t1: float) -> Episode:
    """A closed per-gate episode spanning ``t0`` to ``t1``."""
    return Episode(
        scope=SCOPE_GATE,
        gate=gate,
        t0=t0,
        t1=t1,
        peak_residual=10.0,
        gate_lo=gate,
        gate_hi=gate,
        centroid_mean=float(gate),
        centroid_vel=0.0,
        still_frac=0.0,
        result="entered",
    )


def _outcomes(classifier: GateModel, gate: int, ts: float) -> tuple[float, float]:
    """Decayed ``(n_lead, n_dead)`` for ``gate`` as of ``ts``."""
    return classifier.stats[gate].decayed_outcomes(ts)


def test_a_brief_episode_stays_unresolved_until_its_lead_window_expires() -> None:
    """Spec 20 §3a: a sweep with nothing after it is dead-end, one window later."""
    classifier = _classifier()
    classifier.observe(_episode(2, 100.0, 102.0))

    classifier.tick(106.0)
    assert _outcomes(classifier, 2, 106.0) == (0.0, 0.0)

    classifier.tick(107.0)
    lead, dead = _outcomes(classifier, 2, 107.0)
    assert (lead, dead) == pytest.approx((0.0, 1.0))


def test_a_brief_episode_followed_by_a_dwell_resolves_leading() -> None:
    """A sweep the sensor then watches somebody settle after is a transit."""
    classifier = _classifier()
    classifier.observe(_episode(2, 100.0, 102.0))

    # The dwell is still running when the window expires, so the verdict waits.
    classifier.tick(110.0, open_gates=(7,), open_starts=(104.0,))
    assert _outcomes(classifier, 2, 110.0) == (0.0, 0.0)

    classifier.observe(_episode(7, 104.0, 200.0))
    classifier.tick(201.0)
    lead, dead = _outcomes(classifier, 2, 201.0)
    assert (lead, dead) == pytest.approx((1.0, 0.0))


def test_portal_outranks_bleed_and_in_room_outranks_portal() -> None:
    """Spec 20 §3: IN_ROOM > PORTAL > BLEED, on the same brief-episode counts."""
    classifier = _classifier(n_bleed_min=5.0, n_portal_min=5.0)
    ts = 1000.0
    for _ in range(6):
        classifier.observe(_episode(2, ts, ts + 2.0))
        classifier.observe(_episode(4, ts, ts + 2.0))
        classifier.observe(_episode(7, ts + 4.0, ts + 100.0))
        ts += 200.0
        classifier.tick(ts)

    assert classifier.gate_class(2) == CLASS_PORTAL
    assert classifier.gate_class(7) == CLASS_IN_ROOM

    # Gate 4 saw the same sweeps but its own dwell as well, so it is in-room.
    classifier.observe(_episode(4, ts, ts + 100.0))
    classifier.tick(ts + 200.0)
    assert classifier.gate_class(4) == CLASS_IN_ROOM

    # And a gate whose sweeps lead nowhere reaches bleed on the same counts.
    ts += 400.0
    for _ in range(6):
        classifier.observe(_episode(8, ts, ts + 2.0))
        ts += 200.0
        classifier.tick(ts)
    assert classifier.gate_class(8) == CLASS_BLEED


def test_a_doorway_classifies_portal_and_still_enters_the_room() -> None:
    """Every entry crosses the door and nobody dwells there: portal, not bleed.

    The bleed threshold is low enough that the door would demote without the
    outcome-conditioned counts.
    """
    stream = _stream()
    detector = _detector(n_bleed_min=5.0, n_portal_min=5.0, t_dwell_s=20.0)
    _warm(stream, detector)

    for _ in range(6):
        feed(detector, stream.burst(2.0, move=DOOR))
        feed(detector, stream.burst(30.0, still=DWELL))
        feed(detector, stream.burst(20.0))

    assert detector.gates.gate_class(2) == CLASS_PORTAL
    assert detector.gates.stats[2].n_brief >= 5.0
    assert detector.gates.stats[2].n_dead == 0.0
    assert "P" in detector.gates.classes

    entering = feed(detector, stream.burst(2.0, move=DOOR))
    assert any(output.occupied for output in entering)
    assert max(output.score for output in entering) > 0.0


def test_pass_by_sweeps_with_no_follow_up_stay_bleed() -> None:
    """Spec 20 §3a: a hallway seen through a wall leads nowhere, so it is bleed."""
    stream = _stream()
    detector = _detector(n_bleed_min=5.0, n_portal_min=5.0)
    _warm(stream, detector)

    _sweep(stream, detector, passes=12)
    feed(detector, stream.burst(30.0))

    stats = detector.gates.stats[7]
    assert stats.n_lead == 0.0
    assert stats.n_dead >= 5.0
    assert detector.gates.gate_class(7) == CLASS_BLEED
    assert "P" not in detector.gates.classes


def test_outcome_counts_survive_a_round_trip_and_older_payloads_load() -> None:
    """Lead/dead counts persist, and state written before them restores empty."""
    classifier = _classifier(n_bleed_min=5.0, n_portal_min=5.0)
    ts = 1000.0
    for _ in range(6):
        classifier.observe(_episode(2, ts, ts + 2.0))
        classifier.observe(_episode(7, ts + 4.0, ts + 100.0))
        ts += 200.0
        classifier.tick(ts)
    assert classifier.gate_class(2) == CLASS_PORTAL

    state = json.loads(json.dumps(classifier.to_dict()))
    restored = GateModel.from_dict(state, classifier._config)  # noqa: SLF001
    assert restored.classes == classifier.classes
    for gate in range(9):
        assert restored.stats[gate].n_lead == classifier.stats[gate].n_lead
        assert restored.stats[gate].n_dead == classifier.stats[gate].n_dead

    older = json.loads(json.dumps(classifier.to_dict()))
    older["version"] = 2
    for gate_state in older["gates"]:
        del gate_state["n_lead"]
        del gate_state["n_dead"]
    legacy = GateModel.from_dict(older, classifier._config)  # noqa: SLF001
    assert legacy.stats[2].n_lead == 0.0
    assert legacy.stats[2].n_dead == 0.0
    assert legacy.stats[2].n_brief == classifier.stats[2].n_brief
