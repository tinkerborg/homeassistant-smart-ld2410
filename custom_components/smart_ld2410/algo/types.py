"""Shared data types for the radar feature pipeline."""

from __future__ import annotations

from dataclasses import dataclass

GATE_COUNT = 9


@dataclass(frozen=True, slots=True)
class Frame:
    """One engineering-mode radar frame, timestamped at ingestion."""

    ts_utc: float
    ts_mono: float
    move_gates: tuple[int, ...]
    still_gates: tuple[int, ...]
    target_distance_cm: int
    device_occupancy: bool


@dataclass(frozen=True, slots=True)
class DetectorConfig:
    """Tuning knobs for the baseline model and detector."""

    # support_tau_s smooths the neighbour-elevation test that rescues a lone
    # hot gate; see Detector._score.
    k: float = 4.5
    baseline_window_s: float = 12 * 3600.0
    enter_score: float = 3.0
    exit_score: float = 1.5
    hold_s: float = 30.0
    freeze_hold_s: float = 60.0
    min_mad: float = 1.0
    support_tau_s: float = 1.0


@dataclass(frozen=True, slots=True)
class DetectorOutput:
    """Result of processing one frame."""

    occupied: bool
    confidence: float
    score: float
    active_gates: tuple[int, ...]
    residuals_move: tuple[float, ...]
    residuals_still: tuple[float, ...]
    adaptation_frozen: bool
    baseline_age_s: float
    baseline_ready: bool = True
