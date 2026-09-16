"""Tests for the two-tier quantile noise baseline."""

from __future__ import annotations

import json
import math

import pytest

from custom_components.smart_ld2410.algo.baseline import (
    SCHEMA_VERSION,
    Baseline,
)
from custom_components.smart_ld2410.algo.types import (
    CHANNEL_MOVE,
    CHANNEL_STILL,
    GATE_COUNT,
    Frame,
)

from . import (
    TEST_BUCKET_S,
    TEST_MIN_BUCKETS,
    FrameStream,
    feed,
    make_baseline,
    make_config,
    make_detector,
    warmup_frames,
)


def test_learns_stationary_noise_floor() -> None:
    """Spec item 1: the threshold sits above every peak of stationary noise."""
    stream = FrameStream()
    config = make_config()
    model = make_baseline(config)
    frames = stream.burst(60.0)
    for frame in frames:
        model.add_frame(frame)

    assert model.ready
    total = 0
    exceedances = 0
    for gate in range(GATE_COUNT):
        for channel, samples in (
            (CHANNEL_MOVE, [frame.move_gates[gate] for frame in frames]),
            (CHANNEL_STILL, [frame.still_gates[gate] for frame in frames]),
        ):
            floor = model.floor(gate, channel)
            spread = model.spread(gate, channel)
            assert floor == pytest.approx(stream.floor, abs=1.0)
            assert spread >= config.min_mad
            threshold = floor + config.k * spread
            total += len(samples)
            exceedances += sum(1 for sample in samples if sample >= threshold)

    # The threshold sits above the noise: a bare handful of tail samples may
    # graze it, but it is not a level the noise floor lives at.
    assert exceedances / total < 0.001

    # And such a graze is spatially isolated, so it never scores.
    detector = make_detector(config)
    for output in feed(detector, stream.burst(10.0)):
        assert output.score == 0.0
        assert not output.occupied


def test_spread_tracks_the_upper_tail_not_the_bulk() -> None:
    """A spiky gate is scaled by how high it reaches, not by its bulk jitter.

    This is the estimator's whole point: the recorded hardware's idle gate 0
    sits at 15 with a MAD of 1 and excursions to 32. Scaled by a MAD, an
    ordinary excursion scores z=17; scaled by the q90-q50 tail spread it stays
    ordinary.
    """
    stream = FrameStream(floor=15, sigma=0.6)
    # 10s buckets: 100 samples each, enough for a q90 to see a 12% tail. The
    # production 60s bucket holds 600.
    model = make_baseline(make_config(baseline_window_s=120.0), bucket_s=10.0)
    spikes = {0: (0.15, 12)}
    frames = stream.burst(120.0, move_spikes=spikes)
    for frame in frames:
        model.add_frame(frame)

    quiet_floor = model.floor(0, CHANNEL_STILL)
    quiet_spread = model.spread(0, CHANNEL_STILL)
    spiky_floor = model.floor(0)
    spiky_spread = model.spread(0)
    assert spiky_floor == pytest.approx(quiet_floor, abs=1.0)
    # Same bulk, same centre - but the spiky channel is scaled far wider.
    assert spiky_spread > 3 * quiet_spread

    worst = max(frame.move_gates[0] for frame in frames)
    assert worst > 25  # the tail really is there
    assert (worst - spiky_floor) / spiky_spread < make_config().k


def test_empty_channel_reports_neutral_stats() -> None:
    """An unpopulated channel yields a zero floor and the spread floor."""
    config = make_config()
    model = make_baseline(config)

    assert model.bucket_s == TEST_BUCKET_S
    assert model.floor(0) == 0.0
    assert model.spread(0) == config.min_mad
    assert model.spread(8, CHANNEL_STILL) == config.min_mad


def test_not_ready_until_min_buckets_close() -> None:
    """The window reports unready until it holds the minimum bucket count."""
    stream = FrameStream()
    model = make_baseline()

    assert not model.ready
    assert model.age_s == 0.0

    for frame in stream.burst(TEST_MIN_BUCKETS * TEST_BUCKET_S):
        model.add_frame(frame)
    # Exactly min_buckets seconds of data leaves the last bucket still open.
    assert model.bucket_count == TEST_MIN_BUCKETS - 1
    assert not model.ready

    for frame in stream.burst(2 * TEST_BUCKET_S):
        model.add_frame(frame)
    assert model.ready
    assert model.age_s == model.bucket_count * TEST_BUCKET_S


def test_ingestion_is_unconditional() -> None:
    """``frozen`` is accepted for call-site compatibility and ignored.

    Gating learning on the detector's own output is what let a noise source
    that triggered detection freeze the learning that would have absorbed it.
    """
    stream = FrameStream()
    model = make_baseline()
    for frame in stream.burst(20.0):
        model.add_frame(frame, frozen=False)
    before = model.bucket_count

    for frame in stream.burst(30.0, move={4: 40}):
        model.add_frame(frame, frozen=True)

    assert model.bucket_count == before + 30
    # The elevated buckets are in the window, but they are the *upper* three
    # fifths of it, so the 25th-percentile floor still reads the empty room.
    assert model.floor(4) == pytest.approx(stream.floor, abs=1.0)


def test_floor_ignores_a_minority_of_occupied_buckets() -> None:
    """A person raising a gate for part of the window never lifts its floor."""
    stream = FrameStream()
    model = make_baseline()
    for frame in stream.burst(40.0):
        model.add_frame(frame)
    idle_floor = model.floor(4)

    for frame in stream.burst(15.0, move={4: 40}):
        model.add_frame(frame)

    assert model.floor(4) == pytest.approx(idle_floor, abs=0.5)


def test_floor_absorbs_an_overwhelmingly_occupied_window() -> None:
    """The documented tradeoff: >75% occupancy of the window is absorbed."""
    stream = FrameStream()
    model = make_baseline()
    for frame in stream.burst(10.0):
        model.add_frame(frame)
    for frame in stream.burst(50.0, move={4: 40}):
        model.add_frame(frame)

    assert model.floor(4) > stream.floor + 30


def test_window_evicts_buckets_beyond_the_configured_span() -> None:
    """The window never grows past baseline_window_s worth of buckets."""
    config = make_config(baseline_window_s=10.0)
    model = make_baseline(config)
    for frame in FrameStream().burst(40.0):
        model.add_frame(frame)

    assert model.bucket_count == int(config.baseline_window_s / TEST_BUCKET_S)
    assert model.age_s == config.baseline_window_s


def test_gaps_do_not_backfill_buckets() -> None:
    """A dropout skips ahead; empty buckets are never invented."""
    stream = FrameStream()
    model = make_baseline()
    for frame in stream.burst(10.0):
        model.add_frame(frame)
    before = model.bucket_count

    stream.skip(600.0)
    for frame in stream.burst(3.0):
        model.add_frame(frame)

    # Only buckets that actually carried samples were added, and the bucket
    # left open before the gap is discarded rather than closed (it only
    # partly covers real time, the rest is the 600s gap) - just the ~3
    # seconds fed after the gap count. The +/-1 allows for the resume landing
    # either side of a bucket boundary.
    assert before + 2 <= model.bucket_count <= before + 4
    assert model.floor(0) == pytest.approx(stream.floor, abs=1.0)


def test_restore_after_gap_discards_stale_open_bucket() -> None:
    """A restart gap discards the restored open bucket instead of closing it."""
    stream = FrameStream()
    model = make_baseline()
    for frame in stream.burst(10.0):
        model.add_frame(frame)
    before = model.bucket_count

    payload = json.loads(json.dumps(model.to_dict()))
    restored = Baseline.from_dict(payload)
    assert restored.bucket_count == before

    # Hours pass - an HA restart - before the next sample arrives.
    stream.skip(3600.0)
    restored.add_frame(stream.next_frame())

    # The stale open bucket restored from before the restart was discarded,
    # not folded into the window as if it covered the whole bucket.
    assert restored.bucket_count == before


def test_restore_immediate_continuation_still_closes_open_bucket() -> None:
    """Resuming right where persistence left off remains behaviour-preserving."""

    def make_frame(ts_utc: float) -> Frame:
        return Frame(
            ts_utc=ts_utc,
            ts_mono=0.0,
            move_gates=(5,) * GATE_COUNT,
            still_gates=(5,) * GATE_COUNT,
            target_distance_cm=0,
            device_occupancy=False,
        )

    model = make_baseline()
    for index in range(9):
        model.add_frame(make_frame(1_700_000_000.0 + index * 1.0))
    before = model.bucket_count
    assert before == 8

    payload = json.loads(json.dumps(model.to_dict()))
    restored = Baseline.from_dict(payload)

    # No gap: the very next sample lands in the following bucket, same as it
    # would have without any restart in between.
    restored.add_frame(make_frame(1_700_000_000.0 + 9.0))
    assert restored.bucket_count == before + 1


def test_min_mad_zero_does_not_divide_by_zero() -> None:
    """A pathological min_mad=0 config degrades instead of crashing."""
    config = make_config(min_mad=0.0)
    model = make_baseline(config)
    stream = FrameStream(sigma=0.0)  # perfectly flat noise: raw spread is 0
    for frame in stream.burst(20.0):
        model.add_frame(frame)

    assert model.ready
    assert model.spread(0) > 0.0
    assert model.spread(0, CHANNEL_STILL) > 0.0

    move, still = model.residuals(stream.next_frame())
    assert all(math.isfinite(value) for value in move)
    assert all(math.isfinite(value) for value in still)


def test_empty_channel_min_mad_zero_reports_epsilon_floor() -> None:
    """An unpopulated channel with min_mad=0 still reports a positive spread."""
    model = make_baseline(make_config(min_mad=0.0))
    assert model.spread(0) > 0.0
    assert model.spread(0, CHANNEL_STILL) > 0.0


def test_resize_window_shrinks_and_truncates_oldest_buckets() -> None:
    """Spec item: reconfiguring to a smaller window keeps the newest data."""
    config = make_config(baseline_window_s=30.0)
    model = make_baseline(config)
    stream = FrameStream()
    # 20 elevated buckets (oldest) followed by 4 floor-level ones (newest).
    # The idle minority is under the 25th percentile, so even the floor of the
    # unresized window reads elevated.
    for frame in stream.burst(20.0, move={0: 50}):
        model.add_frame(frame)
    for frame in stream.burst(5.0):
        model.add_frame(frame)
    assert model.ready
    mixed_floor = model.floor(0)
    assert mixed_floor > stream.floor + 10  # the elevated buckets dominate

    model.resize_window(5.0)

    assert model.ready
    assert model.bucket_count == 5
    assert model.age_s == 5.0
    # The oldest (elevated) buckets were truncated away; only the newest,
    # floor-level buckets remain.
    assert model.floor(0) == pytest.approx(stream.floor, abs=1.0)


def test_resize_window_grows_and_preserves_data() -> None:
    """Spec item: reconfiguring to a larger window keeps all learned data."""
    config = make_config(baseline_window_s=10.0)
    model = make_baseline(config)
    stream = FrameStream()
    for frame in stream.burst(10.0, move={0: 50}):
        model.add_frame(frame)
    assert model.ready
    before_count = model.bucket_count
    before_floor = model.floor(0)

    model.resize_window(60.0)

    assert model.bucket_count == before_count
    assert model.floor(0) == pytest.approx(before_floor)
    assert model.age_s == before_count * TEST_BUCKET_S

    # The larger cap now lets more data accumulate instead of evicting.
    for frame in stream.burst(55.0):
        model.add_frame(frame)
    assert model.bucket_count > before_count
    assert model.bucket_count <= 60


def test_add_frame_uses_ts_utc_for_bucketing() -> None:
    """Bucket boundaries follow ts_utc, independent of ts_mono."""
    model = make_baseline()
    for index in range(30):
        frame = Frame(
            ts_utc=1_700_000_000.0 + index * 0.5,
            ts_mono=0.0,
            move_gates=(5,) * GATE_COUNT,
            still_gates=(5,) * GATE_COUNT,
            target_distance_cm=0,
            device_occupancy=False,
        )
        model.add_frame(frame)

    # 30 frames at 0.5s spans 15s, so 14 buckets have closed.
    assert model.bucket_count == 14


def test_persistence_round_trip_preserves_behaviour() -> None:
    """Spec item 8: to_dict/from_dict yields an identically behaving model."""
    stream = FrameStream()
    model = make_baseline()
    for frame in stream.burst(25.0):
        model.add_frame(frame)

    payload = json.loads(json.dumps(model.to_dict()))
    assert payload["version"] == SCHEMA_VERSION
    restored = Baseline.from_dict(payload)

    assert restored.bucket_count == model.bucket_count
    assert restored.ready == model.ready
    assert restored.age_s == model.age_s
    for gate in range(GATE_COUNT):
        assert restored.floor(gate) == model.floor(gate)
        assert restored.spread(gate) == model.spread(gate)
        assert restored.floor(gate, CHANNEL_STILL) == model.floor(gate, CHANNEL_STILL)
        assert restored.spread(gate, CHANNEL_STILL) == model.spread(gate, CHANNEL_STILL)

    # Same subsequent frames, same decisions from detectors over each model.
    frames = [
        *stream.burst(5.0),
        *stream.burst(5.0, move={3: 40, 4: 40, 5: 40}),
        *stream.burst(5.0),
    ]
    original = feed(make_detector(baseline=model), frames)
    replayed = feed(make_detector(baseline=restored), frames)
    assert original == replayed
    assert any(output.occupied for output in original)


def test_from_dict_rejects_unknown_schema_version() -> None:
    """A future on-disk schema is refused rather than silently misread."""
    payload = make_baseline().to_dict()
    payload["version"] = SCHEMA_VERSION + 1
    with pytest.raises(ValueError, match="unsupported baseline schema version"):
        Baseline.from_dict(payload)


def test_from_dict_rejects_previous_schema_versions() -> None:
    """A stale persisted baseline is discarded, not misread.

    Version 2 recorded per-bucket MADs; this estimator divides by a per-bucket
    q90-q50 tail spread, which those summaries never carried. Relearning is
    the only honest option, and the wiring treats the ValueError as "no
    persisted baseline".
    """
    legacy = {
        "version": 2,
        "window_s": 60.0,
        "bucket_s": 1.0,
        "min_mad": 1.0,
        "min_buckets": 5,
        "move": [
            {"buckets": [5.0], "bucket_mads": [1.0], "open_index": None,
             "open_samples": []}
            for _ in range(GATE_COUNT)
        ],
        "still": [
            {"buckets": [5.0], "bucket_mads": [1.0], "open_index": None,
             "open_samples": []}
            for _ in range(GATE_COUNT)
        ],
    }
    with pytest.raises(ValueError, match="unsupported baseline schema version 2"):
        Baseline.from_dict(legacy)

    legacy["version"] = 1
    with pytest.raises(ValueError, match="unsupported baseline schema version 1"):
        Baseline.from_dict(legacy)


def test_from_dict_rejects_mismatched_bucket_series() -> None:
    """A truncated payload is refused rather than silently misaligned."""
    stream = FrameStream()
    model = make_baseline()
    for frame in stream.burst(10.0):
        model.add_frame(frame)

    payload = model.to_dict()
    payload["move"][0]["spreads"].pop()
    with pytest.raises(ValueError, match="mismatched bucket series"):
        Baseline.from_dict(payload)


def test_warmup_helper_makes_the_model_ready() -> None:
    """The shared warm-up helper leaves a detector's baseline usable."""
    stream = FrameStream()
    detector = make_detector()
    outputs = feed(detector, warmup_frames(stream))
    assert not outputs[0].baseline_ready
    assert outputs[-1].baseline_ready
    assert detector.baseline.ready
