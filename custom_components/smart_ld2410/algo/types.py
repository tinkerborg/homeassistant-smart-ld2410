"""Shared data types for the radar feature pipeline."""

from __future__ import annotations

from dataclasses import dataclass

GATE_COUNT = 9

CHANNEL_MOVE = "move"
CHANNEL_STILL = "still"
CHANNELS = (CHANNEL_MOVE, CHANNEL_STILL)
"""The two per-gate energy channels every baseline statistic is kept for."""

GATE_SPACING_M = 0.75
"""Range covered by one gate, fixed by the hardware across all known firmware."""

MAX_GATE_ENERGY = 100
"""Upper bound of the LD2410's per-gate energy scale (0..100, integer)."""

RESULT_ENTERED = "entered"
"""Episode outcome: the detector was occupied during the episode."""

RESULT_REJECTED_COHERENCE = "rejected_coherence"
"""Episode outcome: the exceedance never formed a credible spatial run."""

RESULT_REJECTED_HYSTERESIS = "rejected_hysteresis"
"""Episode outcome: it scored, but never crossed ``enter_score``."""

RESULT_REJECTED_ENERGY_FLOOR = "rejected_energy_floor"
"""Episode outcome: it scored, but never reached ``energy_floor``."""

RESULT_REJECTED_ARRIVAL = "rejected_arrival"
"""Episode outcome: it scored, but never showed arrival-scale motion."""

RESULT_REJECTED_LEADING_EDGE = "rejected_leading_edge"
"""Episode outcome: it scored, but never led at the room's entry gates."""

OWNERSHIP_DISARMED = "disarmed"
"""Ownership state: the occupant has not yet re-crossed the entry gates."""

OWNERSHIP_ARMED = "armed"
"""Ownership state: a departure crossing has been seen; release is permitted."""

SCOPE_GATE = "gate"
"""Episode scope: one gate's own activation interval (drives classification)."""

SCOPE_DETECTION = "detection"
"""Episode scope: the whole detection, spanning every gate that was active."""

CLASS_IN_ROOM = "in_room"
CLASS_PORTAL = "portal"
CLASS_BLEED = "bleed"
CLASS_UNKNOWN = "unknown"
CLASS_OUT = "out"

CLASS_LETTERS = {
    CLASS_IN_ROOM: "I",
    CLASS_PORTAL: "P",
    CLASS_BLEED: "B",
    CLASS_UNKNOWN: "U",
    CLASS_OUT: "O",
}
"""Single-character codes for the ``gate_classes`` diagnostic string.

Spec 20 §6 names I/P/B/U. ``O`` is added for gates the manual ``max_gate``
override has capped out; it is a distinct state from a learned ``B`` because
it is configuration, not evidence, and it must be visible as such.
"""


@dataclass(frozen=True, slots=True)
class Frame:
    """One engineering-mode radar frame, timestamped at ingestion."""

    ts_utc: float
    ts_mono: float
    move_gates: tuple[int, ...]
    still_gates: tuple[int, ...]
    target_distance_cm: int
    device_occupancy: bool


DEFAULT_BUCKET_S = 60.0
"""Width of one baseline accumulation bucket, in seconds of frame time."""

DEFAULT_MIN_BUCKETS = 5
"""Closed buckets needed before the baseline is usable (5 minutes by default)."""

ALL_STAGES = (
    "quantile_floor",
    "tail_spread",
    "histogram_floor",
    "mode_spread",
    "move_ceiling",
    "run_score",
    "lone_gate_suppression",
    "dwell_class",
    "portal_class",
    "energy_ceiling",
    "gate_exclusion",
    "energy_floor",
    "motion_anchor",
    "arrival",
    "leading_edge",
    "retention",
    "ownership",
    "crossing_arming",
    "score_hold",
    "attributed_hold",
    "retention_hold",
)
"""Every registered stage, in evaluation order.

Both floor estimators and both spread estimators are named, and the earlier of
each pair is the one residuals are taken against - a stage list holding every
mechanism is still one detector, not two.
"""

DEFAULT_STAGES = (
    "histogram_floor",
    "mode_spread",
    "run_score",
    "lone_gate_suppression",
    "energy_floor",
    "motion_anchor",
)
"""The stages the detector runs unless configured otherwise."""


@dataclass(frozen=True, slots=True)
class DetectorConfig:
    """Tuning knobs for the baseline model and detector."""

    # Names from the stage registry, in the order they are consulted within
    # their role. Entry filters short-circuit, so their order decides which
    # rejection an episode records.
    stages: tuple[str, ...] = DEFAULT_STAGES

    # support_tau_s smooths the neighbour-elevation test that rescues a lone
    # hot gate; see the coherence module.
    k: float = 4.5
    baseline_window_s: float = 12 * 3600.0
    enter_score: float = 3.0
    exit_score: float = 1.5
    hold_s: float = 30.0
    freeze_hold_s: float = 60.0
    min_mad: float = 1.0
    support_tau_s: float = 1.0

    # -- Phase 2.5: histogram baseline (spec 25) ------------------------------
    # Samples a gate must have observed before its histogram peak is trusted: a
    # freshly power-cycled channel reads saturated, and a mode estimator
    # follows it. ``mode_band`` is the half-width of the quiet population whose
    # median absolute deviation is the residual divisor.
    mode_min_s: float = 60.0
    mode_band: float = 6.0

    # -- Phase 2: dwell-character gate classification (spec 20) ---------------
    # Episode segmentation thresholds are expressed as fractions of ``k`` so
    # they track the detector's own notion of "hot" instead of being a second,
    # independently drifting scale. ``s_gate_on`` lands on k/2, which is
    # already the elevation the neighbour-support test treats as a credible
    # partial presence; ``s_gate_off`` at k/4 gives 2:1 hysteresis so a
    # wobbling smoothed residual does not shred one dwell into many episodes.
    s_gate_on_k: float = 0.5
    s_gate_off_k: float = 0.25
    # None follows hold_s: a dwell must tolerate the same low-signal gap that
    # occupancy already tolerates as continued presence.
    gap_close_s: float | None = None
    # Frames failing to arrive, not a gate going quiet, so this may sit below
    # the close window without competing with it.
    episode_stall_s: float = 10.0
    # Chained pass-by sweeps must not merge into a fake dwell now that gap
    # tolerance is as wide as hold_s.
    active_frac_min: float = 0.6
    t_dwell_s: float = 60.0
    t_brief_s: float = 10.0
    n_bleed_min: float = 20.0
    n_portal_min: float = 5.0
    portal_lead_frac: float = 0.3
    lead_window_s: float = 5.0
    stats_half_life_days: float = 30.0
    # Cadence of the periodic re-evaluation, shared by the dwell classes
    # (spec 20 §3, "daily") and the energy-ceiling boundary (spec 21 §2, also
    # "daily"). ``boundary_confirm_days`` counts *these* evaluations, so
    # compressing this knob in a test compresses the confirmation window with
    # it and the two can never drift apart.
    class_eval_interval_s: float = 24 * 3600.0
    max_gate: int | None = None

    # -- Phase 2: energy-ceiling boundary learning (spec 21) ------------------
    # SHIPS DISABLED (spec 21 §5): the statistics always accumulate and the
    # boundary is always inferred and published, but nothing is suppressed
    # until ``ceiling_enabled`` is turned on. That split is what lets a real
    # install be watched learning the boundary without the boundary being
    # allowed to lose a person in the meantime.
    ceiling_enabled: bool = False
    ceil_drop: float = 0.45
    n_ceil_min: float = 10.0
    # A gate clipped at the top of the energy scale states a lower bound, not
    # a ceiling, so it carries no slope information for the falloff fit.
    ceil_sat: float = 95.0
    boundary_confirm_days: int = 3

    # -- Phase 2: episode energy floor ----------------------------------------
    # Raw move+still energy a candidate must reach somewhere before it is
    # allowed to enter. Both channels count: a motionless in-room person shows
    # move peaks in the teens, indistinguishable from through-wall motion on
    # that channel alone, and only the still channel tells them apart. 0
    # disables the rule.
    energy_floor: float = 30.0

    # -- Phase 2: arrival-gated entry -----------------------------------------
    # Fraction of the learned move ceiling an admitted gate's raw moving energy
    # must reach, in at least ``arrival_min_frames`` frames of the candidate,
    # before entry is allowed. A person walking in pegs the moving channel near
    # whatever that sensor's ceiling is; activity attenuated by a wall cannot.
    # 0 disables the rule.
    arrival_frac: float = 0.55
    arrival_min_frames: int = 1

    # -- Phase 2.5: leading-edge entry and still-presence retention (spec 24) --
    # Nearest gate a candidate's suppressed moving residual may lead at and
    # still be admitted. A person walking in lights the near gates; activity
    # behind an intervening wall physically cannot. -1 disables the rule, and
    # with it ownership: entry then behaves per 22/23 alone.
    lead_gate_max: int = 1
    # Normalized signed retention that refreshes hold at the occupancy's gates
    # while ownership is disarmed, and the lower level it must fall under for
    # the whole hold window before an owned room releases. 0 for retention_off
    # disables retention release-gating.
    retention_on: float = 20.0
    retention_off: float = 10.0
    tau_fast: float = 2.0
    tau_slow: float = 60.0
    tau_peak: float = 90.0
    # Near-band quiet the entry walk-in must settle into before a fresh burst
    # of cross_n near-band frames can arm release, and how long after near-band
    # activity scored evidence still counts as the occupant's own.
    quiet_s: float = 10.0
    cross_n: int = 20
    grace_s: float = 60.0

    @property
    def s_gate_on(self) -> float:
        """Smoothed-residual level at which a gate episode opens."""
        return self.k * self.s_gate_on_k

    @property
    def s_gate_off(self) -> float:
        """Smoothed-residual level a gate episode must fall below to close."""
        return self.k * self.s_gate_off_k

    @property
    def episode_gap_close_s(self) -> float:
        """Seconds a gate must stay under ``s_gate_off`` before its episode ends."""
        return self.hold_s if self.gap_close_s is None else self.gap_close_s

    @property
    def stats_half_life_s(self) -> float:
        """Decay half-life of the per-gate episode counts, in seconds."""
        return self.stats_half_life_days * 86400.0


@dataclass(frozen=True, slots=True)
class Episode:
    """One closed activation episode, shaped for the ``episodes`` table.

    Two scopes share the row shape (see :data:`SCOPE_GATE` /
    :data:`SCOPE_DETECTION`). Per-gate episodes are what the dwell-character
    classifier learns from and carry ``gate_lo == gate_hi == gate``;
    the detection-scope episode spans every gate that was active at once and
    is the record whose ``centroid_mean`` / ``centroid_vel`` mean what the
    interfaces contract says they mean.
    """

    scope: str
    gate: int | None
    t0: float
    t1: float
    peak_residual: float
    gate_lo: int
    gate_hi: int
    centroid_mean: float
    centroid_vel: float
    still_frac: float
    """Fraction of the episode's active time the still channel dominated.

    Diagnostic only. Channel dominance does not separate dwells from blips: a
    body at rest breathes, which keeps the move channel alive.
    """
    result: str
    active_frac: float = 1.0
    """Fraction of ``duration_s`` the signal was above ``s_gate_off``.

    An episode spans quiet stretches up to ``gap_close_s`` without ending, so
    its span alone does not say the signal was there throughout.
    """
    gate_peaks: tuple[int, ...] = (0,) * GATE_COUNT
    """Peak *raw* move energy per gate over the episode (spec 21 §1).

    Raw, not residual, and move-channel only. The energy ceiling is a
    statement about absolute physics - a wall attenuates the return, full
    stop - so subtracting a learned baseline off it would make the ceiling
    move with the noise floor and stop meaning anything. Motion is what
    produces the strong returns; the still channel barely saturates even in
    the same room.

    Gates outside the episode's own span stay at 0: a per-gate episode fills
    only its own index, the detection-scope episode fills every gate that was
    elevated while it was open.
    """
    leading_gate: int | None = None
    """Nearest gate whose moving channel rose above its learned quiet level.

    Diagnostic. An in-room arrival leads at the near gates; activity behind a
    wall physically cannot, so the leading edge separates them even when the
    band they light up is the same.
    """

    @property
    def duration_s(self) -> float:
        """Length of the episode in frame-time seconds."""
        return self.t1 - self.t0


@dataclass(frozen=True, slots=True)
class GateTransition:
    """A change of a gate's learned class, for the caller to log or fire."""

    gate: int
    ts: float
    previous: str
    current: str


@dataclass(frozen=True, slots=True)
class BoundaryTransition:
    """A change of the learned energy-ceiling boundary (spec 21 §3).

    Reported for the caller to log exactly as it logs :class:`GateTransition`.
    ``deferred`` marks the retreat that was held back because a gate it would
    have suppressed still had an episode open; the same transition is
    reported again, undeferred, once that episode closes.
    """

    ts: float
    previous: int | None
    current: int | None
    deferred: bool = False


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
    # -- Learned classification and episode output; all defaulted. ------------
    gate_classes: str = ""
    boundary_gate: int | None = None
    """Learned energy-ceiling boundary: last in-room gate, or ``None`` (21 §2).

    Always published, even while ``ceiling_enabled`` is off - watching it
    learn is the whole point of shipping the feature disabled.
    """
    last_in_room_gate: int | None = None
    """Highest gate the *dwell* classifier has proven in-room (spec 20).

    A different question from :attr:`boundary_gate`, and answered from
    different evidence: this one only says how far in the room presence has
    been observed, which is what the feature stream's ``edge_band`` needs.
    """
    leading_gate: int | None = None
    """Nearest gate elevated above its learned quiet level in the open activity."""
    ownership: str | None = None
    """:data:`OWNERSHIP_ARMED` / :data:`OWNERSHIP_DISARMED`, or ``None`` if unowned."""
    retention_max: float = 0.0
    """Highest normalized still-presence retention at the occupancy's gates."""
    episodes: tuple[Episode, ...] = ()
    gate_transitions: tuple[GateTransition, ...] = ()
    boundary_transitions: tuple[BoundaryTransition, ...] = ()
