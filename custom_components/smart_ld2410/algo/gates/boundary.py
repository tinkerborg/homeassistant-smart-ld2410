"""Energy-ceiling boundary learning (spec 21).

Dwell character cannot say where the room ends - somebody sitting still behind
a wall produces exactly the episodes of somebody sitting still in front of one
- so the boundary asks physics instead. A wall attenuates every return past it,
but return energy also falls with range in empty air, so the comparison is
against the sensor's own measured falloff rather than against the strongest
gate. The learned boundary is the range past which every gate with evidence
sits well below that trend.

It ships disabled (``ceiling_enabled``): the statistics accumulate and the
boundary publishes regardless, but only the flag lets it suppress anything.
That split is what lets a real install be watched learning the boundary
without the boundary being allowed to lose a person in the meantime.
"""

from __future__ import annotations

from math import exp, log
from statistics import median
from typing import Any

from ..roles import ROLE_GATE_BOUNDARY, Stage, StageEnv
from ..types import (
    CLASS_OUT,
    GATE_COUNT,
    GATE_SPACING_M,
    MAX_GATE_ENERGY,
    BoundaryTransition,
    Episode,
)
from .decay import decay_factor

CEIL_QUANTILE = 0.99
"""Upper quantile of episode peak raw energy taken as a gate's ceiling."""

_CEIL_BIN_EPSILON = 1e-9
"""Decayed bin weight below which a histogram bin is dropped entirely."""

_MIN_BOUNDARY_K = 2
"""Smallest ``k`` spec 21 §2 will consider, so gates 0-1 are never suppressed."""

_MIN_FIT_GATES = 3
"""Unsaturated gates with evidence a falloff fit needs before it means anything."""


def _gate_range_m(gate: int) -> float:
    """Range of the centre of ``gate``, in metres."""
    return (gate + 0.5) * GATE_SPACING_M


def _falloff_fit(points: list[tuple[float, float]]) -> tuple[float, float]:
    """Robust log-linear fit of the sensor's own range falloff.

    ``points`` are ``(log range, log ceiling)`` pairs; the return is
    ``(slope, intercept)``.
    """
    slopes = [
        (far_y - near_y) / (far_x - near_x)
        for index, (near_x, near_y) in enumerate(points)
        for far_x, far_y in points[index + 1 :]
        if far_x != near_x
    ]
    slope = median(slopes)
    # The intercept rides the top of the cloud rather than its middle. What the
    # fit has to predict is the energy an *unobstructed* gate at that range
    # would reach, so gates dragged below the trend must move the line's
    # position not at all - that deficit is the entire signal.
    return slope, max(y - slope * x for x, y in points)


class _Unevaluated:
    """Sentinel for "the boundary has never been evaluated"."""

    __slots__ = ()

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        """Render readably in tracebacks."""
        return "<unevaluated>"


_UNEVALUATED = _Unevaluated()


class _GateCeiling:
    """One gate's decayed histogram of episode peak raw move energy."""

    __slots__ = ("bins", "updated_ts")

    def __init__(self) -> None:
        # The LD2410's scale is a bounded 0..100, so a histogram is not an
        # approximation of the quantile - it *is* the quantile, exactly, for a
        # hundredth of the memory a sample buffer would need and with a decay
        # that is one multiply per bin.
        self.bins: dict[int, float] = {}
        self.updated_ts: float | None = None


class EnergyCeilingBoundary(Stage):
    """Learns how far the room reaches from where returns stop saturating."""

    __slots__ = (
        "_boundary_gate",
        "_confirm_count",
        "_deferred_boundary",
        "_gates",
        "_last_eval_ts",
        "_pending_boundary",
    )

    role = ROLE_GATE_BOUNDARY

    def __init__(self, env: StageEnv) -> None:
        """Start with no evidence and no boundary."""
        super().__init__(env)
        self._gates = [_GateCeiling() for _ in range(GATE_COUNT)]
        self._boundary_gate: int | None = None
        self._pending_boundary: int | None | _Unevaluated = _UNEVALUATED
        self._confirm_count = 0
        self._deferred_boundary: int | None | _Unevaluated = _UNEVALUATED
        self._last_eval_ts: float | None = None

    @property
    def boundary_gate(self) -> int | None:
        """Confirmed boundary: last in-room gate, or ``None``.

        Published whether or not ``ceiling_enabled`` lets it act.
        """
        return self._boundary_gate

    @property
    def pending_boundary(self) -> int | None:
        """The candidate boundary the confirmation run is counting, if any."""
        pending = self._pending_boundary
        return None if pending is _UNEVALUATED else pending

    @property
    def confirmed_days(self) -> int:
        """Consecutive daily evaluations the pending candidate has survived."""
        return self._confirm_count

    @property
    def ceil_profile(self) -> tuple[float | None, ...]:
        """Each gate's ceiling over what the sensor's falloff predicts for it.

        ``None`` for a gate without enough episodes to testify; that is a
        different thing from a gate whose ceiling is genuinely low, and
        collapsing the two into 0.0 would let an unvisited gate manufacture a
        boundary.
        """
        latest = [stat.updated_ts for stat in self._gates if stat.updated_ts is not None]
        if not latest:
            return (None,) * GATE_COUNT
        return self._compensated_profile(max(latest))

    def advance(self, gate: int, ts: float) -> None:
        """Decay one gate's histogram forward to ``ts``."""
        stat = self._gates[gate]
        factor = decay_factor(stat.updated_ts, ts, self._config.stats_half_life_s)
        if factor != 1.0:
            stat.bins = {
                value: weight * factor
                for value, weight in stat.bins.items()
                if weight * factor > _CEIL_BIN_EPSILON
            }
        stat.updated_ts = ts

    def observe(self, episode: Episode) -> None:
        """Fold one episode's peak raw move energy into its gate's ceiling.

        Every episode contributes whatever its duration class: the question is
        "how strong can a return from this gate get?", and a two-second
        walk-through is a perfectly good sample of that - in fact the best one,
        since motion is what saturates.
        """
        gate = episode.gate
        if gate is None:
            return
        value = max(0, min(MAX_GATE_ENERGY, int(episode.gate_peaks[gate])))
        bins = self._gates[gate].bins
        bins[value] = bins.get(value, 0.0) + 1.0

    def ceil_q(self, gate: int, quantile: float = CEIL_QUANTILE) -> float | None:
        """Decayed upper quantile of episode peak raw energy, or ``None``.

        No ``ts`` argument, and none is missing: decay multiplies every bin by
        the same factor, which cancels out of a quantile exactly.
        """
        bins = self._gates[gate].bins
        total = sum(bins.values())
        if total <= 0.0:
            return None
        target = quantile * total
        cumulative = 0.0
        for value in sorted(bins):
            cumulative += bins[value]
            if cumulative >= target:
                return float(value)
        # Only reachable through floating-point summation slack.
        return float(max(bins))  # pragma: no cover

    def n_epi(self, gate: int, ts: float) -> float:
        """Decayed count of episodes folded into one gate's ceiling."""
        stat = self._gates[gate]
        total = sum(stat.bins.values())
        return total * decay_factor(
            stat.updated_ts, ts, self._config.stats_half_life_s
        )

    def class_override(self, gate: int) -> str | None:
        """``CLASS_OUT`` when the learned boundary is allowed to suppress ``gate``."""
        boundary = self._boundary_gate
        if self._config.ceiling_enabled and boundary is not None and gate > boundary:
            return CLASS_OUT
        return None

    def tick(
        self, ts: float, open_gates: tuple[int, ...] = ()
    ) -> tuple[BoundaryTransition, ...]:
        """Run the inference if a day has elapsed, and apply what it confirmed.

        Returns whatever boundary transitions this produced - including a
        deferred retreat finally landing, which can happen on a tick that ran
        no new inference at all. The schedule is its own: spec 21 §2 counts
        consecutive daily evaluations, so it must not be driven by episode
        closes or a busy sensor would confirm a three-day-stable boundary in an
        afternoon.
        """
        transitions: list[BoundaryTransition] = []
        last = self._last_eval_ts
        due = last is None or not 0.0 <= ts - last < self._config.class_eval_interval_s
        if due:
            self._last_eval_ts = ts
            self._step_candidate(ts)
        transitions.extend(self._apply_boundary(ts, open_gates))
        return tuple(transitions)

    def gate_state(self, gate: int) -> dict[str, Any]:
        """Return one gate's histogram, JSON-safe."""
        # Sparse: only occupied bins are written, and JSON object keys are
        # strings, so this round-trips through HA's Store unchanged.
        return {
            "ceil_bins": {
                str(value): weight for value, weight in self._gates[gate].bins.items()
            }
        }

    def restore_gate(self, gate: int, data: dict[str, Any]) -> None:
        """Restore one gate from :meth:`gate_state` output."""
        stat = self._gates[gate]
        stat.bins = {
            int(value): float(weight)
            for value, weight in data.get("ceil_bins", {}).items()
        }
        updated = data.get("updated_ts")
        stat.updated_ts = None if updated is None else float(updated)

    def to_dict(self) -> dict[str, Any]:
        """Return the boundary state, JSON-safe."""
        pending = self._pending_boundary
        return {
            "boundary_gate": self._boundary_gate,
            # A confirmation run that survived a restart is a confirmation run
            # that happened; throwing it away would make every restart cost
            # three more days before the boundary could take effect.
            "pending_boundary": None if pending is _UNEVALUATED else pending,
            "pending_evaluated": pending is not _UNEVALUATED,
            "confirm_count": self._confirm_count,
            "last_boundary_eval_ts": self._last_eval_ts,
        }

    def restore(self, data: dict[str, Any]) -> None:
        """Restore the boundary state from :meth:`to_dict` output."""
        boundary = data.get("boundary_gate")
        self._boundary_gate = None if boundary is None else int(boundary)
        if data.get("pending_evaluated"):
            pending = data.get("pending_boundary")
            self._pending_boundary = None if pending is None else int(pending)
            self._confirm_count = int(data.get("confirm_count", 0))
        last = data.get("last_boundary_eval_ts")
        self._last_eval_ts = None if last is None else float(last)

    def _compensated_profile(self, ts: float) -> tuple[float | None, ...]:
        n_ceil_min = self._config.n_ceil_min
        ceil_sat = self._config.ceil_sat
        ceilings: list[float | None] = []
        for gate in range(GATE_COUNT):
            ceiling = self.ceil_q(gate)
            enough = self.n_epi(gate, ts) >= n_ceil_min
            ceilings.append(ceiling if enough else None)

        points = [
            (log(_gate_range_m(gate)), log(ceiling))
            for gate, ceiling in enumerate(ceilings)
            if ceiling is not None and 0.0 < ceiling < ceil_sat
        ]
        if len(points) < _MIN_FIT_GATES:
            return (None,) * GATE_COUNT

        slope, intercept = _falloff_fit(points)
        return tuple(
            None
            if ceiling is None
            else ceiling / exp(intercept + slope * log(_gate_range_m(gate)))
            for gate, ceiling in enumerate(ceilings)
        )

    def _step_candidate(self, ts: float) -> None:
        """Score today's candidate boundary and advance the confirmation run."""
        candidate = self._infer_boundary(ts)
        if candidate is _UNEVALUATED:
            # Too few gates carry usable evidence to fit the sensor's falloff.
            # That is a reason not to run at all, not a reason to decide "no
            # boundary": silence is not evidence either way.
            return
        if candidate == self._pending_boundary:
            self._confirm_count += 1
        else:
            self._pending_boundary = candidate
            self._confirm_count = 1

    def _infer_boundary(self, ts: float) -> int | None | _Unevaluated:
        """The first range past which every gate with evidence is low."""
        profile = self._compensated_profile(ts)
        if all(value is None for value in profile):
            return _UNEVALUATED

        drop = self._config.ceil_drop
        for k in range(_MIN_BOUNDARY_K, GATE_COUNT):
            # A gate without episodes cannot testify either way, so it is
            # skipped rather than read as low - and a k with nothing but such
            # gates beyond it rests on no evidence at all.
            beyond = [value for value in profile[k:] if value is not None]
            if beyond and all(value < drop for value in beyond):
                return k - 1
        return None

    def _apply_boundary(
        self, ts: float, open_gates: tuple[int, ...]
    ) -> tuple[BoundaryTransition, ...]:
        """Promote a confirmed candidate to the live boundary, or defer it.

        Runs on every tick rather than only on the daily one, which is what
        makes the deferral self-clearing: the confirmed candidate simply keeps
        failing to apply until the episode blocking it closes, and then applies
        on the very next frame.
        """
        if self._confirm_count < self._config.boundary_confirm_days:
            return ()
        target = self._pending_boundary
        if target is _UNEVALUATED or target == self._boundary_gate:
            return ()

        current = self._boundary_gate
        retreat = target is not None and (current is None or target < current)
        if retreat and any(gate > target for gate in open_gates):
            # Never yank a gate out from under a person the sensor is watching
            # right now.
            if self._deferred_boundary == target:
                return ()
            self._deferred_boundary = target
            return (
                BoundaryTransition(
                    ts=ts, previous=current, current=target, deferred=True
                ),
            )

        self._deferred_boundary = _UNEVALUATED
        self._boundary_gate = target
        return (BoundaryTransition(ts=ts, previous=current, current=target),)
