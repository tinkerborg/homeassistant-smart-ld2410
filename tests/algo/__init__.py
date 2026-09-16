"""Tests for the pure-Python radar feature pipeline.

This module also holds the synthetic frame generator the algo tests share.
Everything here is seeded and frame-time driven, so a test run is reproducible.
"""

from __future__ import annotations

import random
from collections.abc import Mapping

from custom_components.smart_ld2410.algo.baseline import Baseline
from custom_components.smart_ld2410.algo.context import DetectorContext
from custom_components.smart_ld2410.algo.detector import Detector
from custom_components.smart_ld2410.algo.episodes import EpisodeTracker
from custom_components.smart_ld2410.algo.gates import GateModel
from custom_components.smart_ld2410.algo.pipeline import build_pipeline
from custom_components.smart_ld2410.algo.presence import Presence
from custom_components.smart_ld2410.algo.roles import StageEnv
from custom_components.smart_ld2410.algo.types import (
    GATE_COUNT,
    DetectorConfig,
    DetectorOutput,
    Frame,
)

BASE_TS = 1_700_000_000.0
"""Arbitrary fixed epoch start so bucketing is reproducible."""

NOISE_FLOOR = 5
"""Per-gate idle energy the synthetic sensor sits at."""

TEST_BUCKET_S = 1.0
"""One-second baseline buckets keep the tests fast."""

TEST_MIN_BUCKETS = 5


def make_config(**overrides: object) -> DetectorConfig:
    """Return a detector config with a short baseline window for tests.

    The leading-edge rule is off unless a test asks for it: the synthetic
    bands the other rules are exercised with sit wherever those rules need
    them, which is rarely at the entry gates.
    """
    values: dict[str, object] = {
        "k": 4.5,
        "baseline_window_s": 60.0,
        "enter_score": 3.0,
        "exit_score": 1.5,
        "hold_s": 30.0,
        "freeze_hold_s": 60.0,
        "min_mad": 1.0,
        "lead_gate_max": -1,
    }
    values.update(overrides)
    return DetectorConfig(**values)


def make_detector(
    config: DetectorConfig | None = None,
    *,
    baseline: Baseline | None = None,
    bucket_s: float = TEST_BUCKET_S,
) -> Detector:
    """Build a detector wired to the fast test bucketing."""
    return Detector(
        config or make_config(),
        baseline=baseline,
        bucket_s=bucket_s,
        min_buckets=TEST_MIN_BUCKETS,
    )


def make_baseline(
    config: DetectorConfig | None = None, *, bucket_s: float = TEST_BUCKET_S
) -> Baseline:
    """Build a standalone baseline with the fast test bucketing."""
    resolved = config or make_config()
    return Baseline.build(
        StageEnv(resolved, bucket_s=bucket_s, min_buckets=TEST_MIN_BUCKETS),
        resolved.stages,
    )


class FrameStream:
    """Deterministic synthetic frame source.

    Every gate idles at ``floor`` plus seeded Gaussian noise; callers raise
    individual gates by passing per-gate elevations.
    """

    def __init__(
        self,
        *,
        seed: int = 20260829,
        interval_s: float = 0.1,
        floor: int = NOISE_FLOOR,
        sigma: float = 1.0,
        start_ts: float = BASE_TS,
    ) -> None:
        """Initialise the stream at ``start_ts``."""
        self._rng = random.Random(seed)
        self._interval_s = interval_s
        self._floor = floor
        self._sigma = sigma
        self._ts = start_ts

    @property
    def ts(self) -> float:
        """Timestamp the next frame will carry."""
        return self._ts

    @property
    def floor(self) -> int:
        """The idle energy level."""
        return self._floor

    def skip(self, seconds: float) -> None:
        """Advance frame time without emitting frames (a BLE dropout)."""
        self._ts += seconds

    def _sample(self, elevation: int, spike: tuple[float, int] | None) -> int:
        """Draw one noisy gate energy, clamped to the device's 0..100 range.

        ``spike`` is an optional ``(probability, extra)`` pair that models the
        heavy right tail real idle gates show: most samples sit at the floor
        while a few per second jump ``extra`` above it.
        """
        value = self._floor + elevation + self._rng.gauss(0.0, self._sigma)
        if spike is not None and self._rng.random() < spike[0]:
            value += spike[1]
        return max(0, min(100, round(value)))

    def next_frame(
        self,
        *,
        move: Mapping[int, int] | None = None,
        still: Mapping[int, int] | None = None,
        move_spikes: Mapping[int, tuple[float, int]] | None = None,
        device_occupancy: bool = False,
        interval_s: float | None = None,
    ) -> Frame:
        """Emit one frame with the given per-gate elevations."""
        ts = self._ts
        self._ts += self._interval_s if interval_s is None else interval_s
        move_levels = move or {}
        still_levels = still or {}
        spikes = move_spikes or {}
        return Frame(
            ts_utc=ts,
            ts_mono=ts,
            move_gates=tuple(
                self._sample(move_levels.get(gate, 0), spikes.get(gate))
                for gate in range(GATE_COUNT)
            ),
            still_gates=tuple(
                self._sample(still_levels.get(gate, 0), None)
                for gate in range(GATE_COUNT)
            ),
            target_distance_cm=0,
            device_occupancy=device_occupancy,
        )

    def burst(
        self,
        duration_s: float,
        *,
        move: Mapping[int, int] | None = None,
        still: Mapping[int, int] | None = None,
        move_spikes: Mapping[int, tuple[float, int]] | None = None,
        device_occupancy: bool = False,
        interval_s: float | None = None,
    ) -> list[Frame]:
        """Emit frames covering ``duration_s`` of frame time."""
        step = self._interval_s if interval_s is None else interval_s
        count = max(1, round(duration_s / step))
        return [
            self.next_frame(
                move=move,
                still=still,
                move_spikes=move_spikes,
                device_occupancy=device_occupancy,
                interval_s=interval_s,
            )
            for _ in range(count)
        ]


def entry_index(config: DetectorConfig) -> int:
    """Index of the earliest frame of a strong candidate that may be admitted.

    Arrival gating asks for the threshold to be reached in several frames, so
    even an unambiguous walk-in is admitted a couple of frames in.
    """
    return config.arrival_min_frames - 1


def feed(detector: Detector, frames: list[Frame]) -> list[DetectorOutput]:
    """Push frames through a detector and collect every output."""
    return [detector.process(frame) for frame in frames]


def warmup_frames(stream: FrameStream, duration_s: float = 10.0) -> list[Frame]:
    """Produce enough idle frames for the baseline to become ready."""
    return stream.burst(duration_s)


def make_gates(config: DetectorConfig) -> GateModel:
    """Build the gate stages on their own, as a detector would."""
    return GateModel.build(StageEnv(config), config.stages)


def make_presence(config: DetectorConfig) -> Presence:
    """Build the presence stages on their own, as a detector would."""
    return Presence.build(StageEnv(config), config.stages)


def hold_refreshes(
    config: DetectorConfig, presence: Presence, ts: float, *, scored: bool
) -> bool:
    """Whether the config's hold refreshers keep an occupancy alive at ``ts``.

    Drives the shipped stages the way :meth:`Detector._advance` drives them for
    an owned room, without folding a frame into the retention statistic.
    """
    env = StageEnv(config, bucket_s=TEST_BUCKET_S, min_buckets=TEST_MIN_BUCKETS)
    pipeline = build_pipeline(env, presence=presence)
    context = DetectorContext(
        config, pipeline=pipeline, episodes=EpisodeTracker(config)
    )
    context.frame = Frame(
        ts_utc=ts,
        ts_mono=ts,
        move_gates=(0,) * GATE_COUNT,
        still_gates=(0,) * GATE_COUNT,
        target_distance_cm=0,
        device_occupancy=False,
    )
    context.score = config.exit_score if scored else 0.0
    if presence.owned:
        presence.step_arming(ts)
    return pipeline.refreshes_hold(context)
