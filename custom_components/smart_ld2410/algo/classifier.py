"""Dwell-character gate classification (spec 20 §2-3).

The question this answers is "which gates are inside the room?", and the
answer comes from the *character* of each gate's activation episodes rather
than from any geometry the user had to type in:

* A gate where people regularly settle - one unbroken minute of elevation, a
  thing no sweep can produce - is in the room. One such episode is enough: a guest
  bedroom used twice a year must work the first time it is used, so there is
  no "enough evidence yet" waiting period.
* A gate that has only ever seen dozens of three-second sweeps and never a
  dwell is bleed: a hallway behind a wall, seen through it.
* A gate whose brief sweeps keep being followed, seconds later, by somebody
  settling in deeper is a doorway: a portal, and portals count toward entry
  exactly as in-room gates do. Only what happens next tells a doorway from a
  hallway, so each brief episode is resolved a lead window after it closes.
* Everything else is unknown, and unknown is treated as in-room. Being
  permissive by default means a fresh install behaves exactly as it did
  before classification existed, and only ever gets stricter about a gate
  once that gate has earned it.

Counts are exponentially decayed with a 30-day half-life so the model tracks
a home that changes: move a sofa and the old dwell gate demotes itself over a
month, without ever needing a reset button. Decay is computed from frame
time, never from a clock, so a replay of a recording produces exactly the
classes the live run produced.

Demotion is deliberately asymmetric. Promotion to IN_ROOM is instant;
IN_ROOM -> BLEED can only happen through decay. A wrongly-permissive gate
costs a false positive; a wrongly-strict gate loses a real person.

Spec 21 layers a second, independent question on top: *where does the room
end?* Dwell character cannot answer it - somebody sitting still behind a wall
produces exactly the episodes of somebody sitting still in front of one - so
the ceiling asks physics instead. A wall attenuates every return past it, and
attenuation is what the boundary looks for - but return energy also falls with
range in empty air, so the comparison is against the sensor's own measured
falloff rather than against the strongest gate. The learned boundary is the
range past which every gate with evidence sits well below that trend. It ships
disabled (``ceiling_enabled``): the statistics accumulate and the boundary
publishes regardless, but only the flag lets it suppress anything.
"""

from __future__ import annotations

from math import exp, log
from statistics import median
from typing import Any

from .types import (
    CLASS_BLEED,
    CLASS_IN_ROOM,
    CLASS_LETTERS,
    CLASS_OUT,
    CLASS_PORTAL,
    CLASS_UNKNOWN,
    GATE_COUNT,
    GATE_SPACING_M,
    MAX_GATE_ENERGY,
    SCOPE_GATE,
    BoundaryTransition,
    DetectorConfig,
    Episode,
    GateTransition,
)

SCHEMA_VERSION = 3
"""Serialisation version of the classifier state.

v2 adds the spec 21 energy-ceiling histograms and the confirmed boundary;
v3 adds the outcome-conditioned brief-episode counts behind PORTAL.
"""

_SUPPORTED_VERSIONS = (1, 2, 3)
"""Versions :meth:`GateClassifier.from_dict` accepts.

An older payload restores with the fields it predates empty, keeping a month
of hard-won dwell statistics a version rejection would have thrown away.
"""

_IN_ROOM_SUSTAINED = 1.0
"""Decayed sustained count at which a gate is in-room."""

_BLEED_SUSTAINED_MAX = 0.5
"""Decayed sustained count a gate must be under to be demotable to bleed."""

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


class GateStats:
    """Decayed episode counts, energy ceiling, and current class for one gate."""

    __slots__ = (
        "ceil_bins",
        "gate",
        "gate_class",
        "last_sustained_ts",
        "n_brief",
        "n_dead",
        "n_lead",
        "n_sustained",
        "updated_ts",
    )

    def __init__(self, gate: int) -> None:
        """Create empty statistics for ``gate``."""
        self.gate = gate
        self.n_sustained = 0.0
        self.n_brief = 0.0
        self.n_lead = 0.0
        self.n_dead = 0.0
        # Decayed histogram of episode peak raw move energy, keyed by the
        # integer energy value. The LD2410's scale is a bounded 0..100, so a
        # histogram is not an approximation of the quantile - it *is* the
        # quantile, exactly, for a hundredth of the memory a sample buffer
        # would need and with a decay that is one multiply per bin. Streaming
        # estimators (P-square, Frugal, SA) exist for unbounded domains; there
        # is no reason to accept their convergence error here.
        self.ceil_bins: dict[int, float] = {}
        self.last_sustained_ts: float | None = None
        self.updated_ts: float | None = None
        self.gate_class = CLASS_UNKNOWN

    def decayed(self, ts: float, half_life_s: float) -> tuple[float, float]:
        """Return ``(n_sustained, n_brief)`` as of frame time ``ts``.

        Pure: reading the counts at a later time never mutates them, so a
        classification pass and a persistence snapshot cannot disagree.
        """
        return (
            self.n_sustained * _decay(self.updated_ts, ts, half_life_s),
            self.n_brief * _decay(self.updated_ts, ts, half_life_s),
        )

    def decayed_outcomes(self, ts: float, half_life_s: float) -> tuple[float, float]:
        """Return ``(n_lead, n_dead)`` as of frame time ``ts``, without mutating."""
        factor = _decay(self.updated_ts, ts, half_life_s)
        return (self.n_lead * factor, self.n_dead * factor)

    def n_epi(self, ts: float, half_life_s: float) -> float:
        """Decayed count of episodes folded into the ceiling, as of ``ts``."""
        total = sum(self.ceil_bins.values())
        return total * _decay(self.updated_ts, ts, half_life_s)

    def ceil_q(self, quantile: float = CEIL_QUANTILE) -> float | None:
        """Decayed upper quantile of episode peak raw energy, or ``None``.

        No ``ts`` argument, and none is missing: decay multiplies every bin by
        the same factor, which cancels out of a quantile exactly. The relative
        weighting that matters - old episodes counting for less than new ones -
        is already baked into the stored bins by :meth:`advance`, which runs
        before each new sample lands at full weight.
        """
        total = sum(self.ceil_bins.values())
        if total <= 0.0:
            return None
        target = quantile * total
        cumulative = 0.0
        for value in sorted(self.ceil_bins):
            cumulative += self.ceil_bins[value]
            if cumulative >= target:
                return float(value)
        # Only reachable through floating-point summation slack.
        return float(max(self.ceil_bins))  # pragma: no cover

    def advance(self, ts: float, half_life_s: float) -> None:
        """Decay the stored counts and the ceiling histogram forward to ``ts``."""
        factor = _decay(self.updated_ts, ts, half_life_s)
        self.n_sustained, self.n_brief = self.decayed(ts, half_life_s)
        self.n_lead, self.n_dead = self.decayed_outcomes(ts, half_life_s)
        if factor != 1.0:
            self.ceil_bins = {
                value: weight * factor
                for value, weight in self.ceil_bins.items()
                if weight * factor > _CEIL_BIN_EPSILON
            }
        self.updated_ts = ts

    def observe_peak(self, energy: int) -> None:
        """Fold one episode's peak raw move energy into the ceiling histogram."""
        value = max(0, min(MAX_GATE_ENERGY, int(energy)))
        self.ceil_bins[value] = self.ceil_bins.get(value, 0.0) + 1.0

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe snapshot of this gate."""
        return {
            "gate": self.gate,
            "n_sustained": self.n_sustained,
            "n_brief": self.n_brief,
            "n_lead": self.n_lead,
            "n_dead": self.n_dead,
            "last_sustained_ts": self.last_sustained_ts,
            "updated_ts": self.updated_ts,
            "class": self.gate_class,
            # Sparse: only occupied bins are written, and JSON object keys are
            # strings, so this round-trips through HA's Store unchanged.
            "ceil_bins": {str(value): weight for value, weight in self.ceil_bins.items()},
        }

    def restore(self, data: dict[str, Any]) -> None:
        """Restore this gate from :meth:`to_dict` output."""
        self.n_sustained = float(data["n_sustained"])
        self.n_brief = float(data["n_brief"])
        self.n_lead = float(data.get("n_lead", 0.0))
        self.n_dead = float(data.get("n_dead", 0.0))
        last = data.get("last_sustained_ts")
        self.last_sustained_ts = None if last is None else float(last)
        updated = data.get("updated_ts")
        self.updated_ts = None if updated is None else float(updated)
        gate_class = str(data["class"])
        if gate_class not in CLASS_LETTERS:
            raise ValueError(f"unknown gate class {gate_class!r}")
        self.gate_class = gate_class
        self.ceil_bins = {
            int(value): float(weight)
            for value, weight in data.get("ceil_bins", {}).items()
        }


def _decay(updated_ts: float | None, ts: float, half_life_s: float) -> float:
    """Return the decay multiplier between ``updated_ts`` and ``ts``."""
    if updated_ts is None or half_life_s <= 0.0:
        return 1.0
    elapsed = ts - updated_ts
    if elapsed <= 0.0:
        # Frame time can repeat, and a recording can be replayed out of order
        # by a caller; neither may resurrect decayed evidence.
        return 1.0
    return 0.5 ** (elapsed / half_life_s)


def _within(starts: list[float] | tuple[float, ...], ts: float, window: float) -> bool:
    """Whether any of ``starts`` falls within ``window`` seconds of ``ts``.

    Symmetric: a doorway transit lights the gate it is heading for before the
    doorway gate falls quiet.
    """
    return any(abs(start - ts) <= window for start in starts)


class _PendingBrief:
    """A closed brief episode still waiting to be called leading or dead-end."""

    __slots__ = ("close_ts", "gate")

    def __init__(self, gate: int, close_ts: float) -> None:
        """Record that ``gate``'s brief episode ended at ``close_ts``."""
        self.gate = gate
        self.close_ts = close_ts


class GateClassifier:
    """Per-gate dwell statistics and the classification they imply."""

    __slots__ = (
        "_boundary_gate",
        "_config",
        "_confirm_count",
        "_deferred_boundary",
        "_last_boundary_eval_ts",
        "_last_eval_ts",
        "_pending_boundary",
        "_pending_briefs",
        "_stats",
        "_sustained_starts",
    )

    def __init__(self, config: DetectorConfig) -> None:
        """Create a classifier with every gate unknown."""
        self._config = config
        self._stats = [GateStats(gate) for gate in range(GATE_COUNT)]
        self._pending_briefs: list[_PendingBrief] = []
        self._sustained_starts: list[float] = []
        self._last_eval_ts: float | None = None
        self._boundary_gate: int | None = None
        self._pending_boundary: int | None | _Unevaluated = _UNEVALUATED
        self._confirm_count = 0
        self._deferred_boundary: int | None | _Unevaluated = _UNEVALUATED
        self._last_boundary_eval_ts: float | None = None

    def reconfigure(self, config: DetectorConfig) -> None:
        """Adopt new thresholds; the learned statistics are untouched."""
        self._config = config

    @property
    def stats(self) -> list[GateStats]:
        """Per-gate statistics, indexed by gate."""
        return self._stats

    def gate_class(self, gate: int) -> str:
        """Effective class of ``gate``: overrides, then boundary, then evidence.

        Precedence is spec 21 §3: manual ``max_gate`` > learned energy-ceiling
        boundary > dwell class. Both of the first two produce ``OUT``, so the
        order is only visible in the reasoning, but it is the reasoning that
        has to stay right: the manual cap is configuration and must never be
        second-guessed by something the sensor learned.
        """
        max_gate = self._config.max_gate
        if max_gate is not None and gate > max_gate:
            # The override is applied on read rather than stored, so dropping
            # the cap later restores whatever the gate had actually learned
            # instead of making it start over.
            return CLASS_OUT
        boundary = self._boundary_gate
        if self._config.ceiling_enabled and boundary is not None and gate > boundary:
            return CLASS_OUT
        return self._stats[gate].gate_class

    def excluded(self, gate: int) -> bool:
        """Whether ``gate`` is barred from entry scoring and neighbour support.

        Exclusion is an entry-side rule only. Once the room is occupied every
        gate contributes to holding it occupied, because a person who walked
        into a corner the sensor sees through a wall is still a person who is
        in the room.
        """
        return self.gate_class(gate) in (CLASS_BLEED, CLASS_OUT)

    @property
    def classes(self) -> str:
        """Diagnostic string like ``IIIPUBB...``, one letter per gate."""
        return "".join(
            CLASS_LETTERS[self.gate_class(gate)] for gate in range(GATE_COUNT)
        )

    @property
    def last_in_room_gate(self) -> int | None:
        """Highest gate proven to be in-room, or ``None`` if none is yet.

        Unknown gates are treated as in-room for *detection*, but they are
        not evidence of where the room ends, so they do not move this. Note
        this answers "how far has presence been seen?", not spec 21's "where
        does the room end?" - see :attr:`boundary_gate`.
        """
        for stat in reversed(self._stats):
            if self.gate_class(stat.gate) == CLASS_IN_ROOM:
                return stat.gate
        return None

    @property
    def boundary_gate(self) -> int | None:
        """Confirmed energy-ceiling boundary: last in-room gate, or ``None``.

        Published whether or not ``ceiling_enabled`` lets it act.
        """
        return self._boundary_gate

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
        latest = [stat.updated_ts for stat in self._stats if stat.updated_ts is not None]
        if not latest:
            return (None,) * GATE_COUNT
        return self._compensated_profile(max(latest))

    def _compensated_profile(self, ts: float) -> tuple[float | None, ...]:
        n_ceil_min = self._config.n_ceil_min
        ceil_sat = self._config.ceil_sat
        half_life_s = self._config.stats_half_life_s
        ceilings: list[float | None] = []
        for stat in self._stats:
            ceiling = stat.ceil_q()
            enough = stat.n_epi(ts, half_life_s) >= n_ceil_min
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

    def observe(self, episode: Episode) -> tuple[GateTransition, ...]:
        """Fold one closed per-gate episode in and reclassify.

        Detection-scope episodes are ignored: they describe a band, and the
        classification question is per gate.
        """
        if episode.scope != SCOPE_GATE or episode.gate is None:
            return ()
        config = self._config
        stat = self._stats[episode.gate]
        ts = episode.t1
        stat.advance(ts, config.stats_half_life_s)

        # Every episode contributes to the ceiling, whatever its duration
        # class: the question the ceiling asks is "how strong can a return
        # from this gate get?", and a two-second walk-through is a perfectly
        # good sample of that - in fact the best one, since motion is what
        # saturates. n_epi is the total weight of this histogram.
        stat.observe_peak(episode.gate_peaks[episode.gate])

        duration = episode.duration_s
        if duration >= config.t_dwell_s and episode.active_frac >= config.active_frac_min:
            stat.n_sustained += 1.0
            stat.last_sustained_ts = ts
            self._sustained_starts.append(episode.t0)
        elif duration <= config.t_brief_s:
            stat.n_brief += 1.0
            self._pending_briefs.append(_PendingBrief(episode.gate, episode.t1))
        # Episodes between the two lengths, and long ones too gappy to be a
        # dwell, count toward neither class.
        return self.evaluate(ts)

    def tick(
        self,
        ts: float,
        *,
        open_gates: tuple[int, ...] = (),
        open_starts: tuple[float, ...] = (),
    ) -> tuple[tuple[GateTransition, ...], tuple[BoundaryTransition, ...]]:
        """Re-evaluate on a schedule so decay alone can demote a gate.

        Classification is otherwise only recomputed when an episode closes,
        which would leave a gate that has simply gone quiet for months stuck
        at its last class forever.

        The energy-ceiling boundary is re-evaluated on the *same* schedule but
        from its own timestamp: spec 21 §2 counts ``boundary_confirm_days``
        consecutive daily evaluations, so it must not be driven by episode
        closes the way :meth:`evaluate` is, or a busy sensor would confirm a
        three-day-stable boundary in an afternoon.

        ``open_gates`` are the gates with an episode currently in progress;
        a boundary retreat that would suppress one of them is deferred.
        ``open_starts`` are those episodes' start times, which is what holds a
        brief episode unresolved while the dwell it may have led to still runs.
        """
        interval = self._config.class_eval_interval_s
        boundary_transitions = self.evaluate_boundary(ts, open_gates=open_gates)
        resolved = self._resolve_briefs(ts, open_starts)
        last = self._last_eval_ts
        if not resolved and last is not None and 0.0 <= ts - last < interval:
            return (), boundary_transitions
        return self.evaluate(ts), boundary_transitions

    def _resolve_briefs(self, ts: float, open_starts: tuple[float, ...]) -> bool:
        """Call every brief episode past its lead window leading or dead-end.

        One whose window holds a still-open episode waits: a dwell is a minute
        long, so its verdict cannot exist yet.
        """
        if not self._pending_briefs:
            self._sustained_starts.clear()
            return False
        config = self._config
        window = config.lead_window_s
        half_life_s = config.stats_half_life_s
        unresolved: list[_PendingBrief] = []
        resolved = False
        for pending in self._pending_briefs:
            if ts < pending.close_ts + window:
                unresolved.append(pending)
                continue
            if _within(self._sustained_starts, pending.close_ts, window):
                leading = True
            elif _within(open_starts, pending.close_ts, window):
                unresolved.append(pending)
                continue
            else:
                leading = False
            stat = self._stats[pending.gate]
            stat.advance(ts, half_life_s)
            if leading:
                stat.n_lead += 1.0
            else:
                stat.n_dead += 1.0
            resolved = True
        self._pending_briefs = unresolved
        oldest = min((pending.close_ts for pending in unresolved), default=None)
        if oldest is None:
            self._sustained_starts.clear()
        else:
            self._sustained_starts = [
                start for start in self._sustained_starts if start >= oldest - window
            ]
        return resolved

    def evaluate_boundary(
        self, ts: float, *, open_gates: tuple[int, ...] = ()
    ) -> tuple[BoundaryTransition, ...]:
        """Run the spec 21 §2 boundary inference if a day has elapsed.

        Returns whatever boundary transitions this produced - including a
        deferred retreat finally landing, which can happen on a tick that ran
        no new inference at all.
        """
        transitions: list[BoundaryTransition] = []
        last = self._last_boundary_eval_ts
        due = last is None or not 0.0 <= ts - last < self._config.class_eval_interval_s
        if due:
            self._last_boundary_eval_ts = ts
            self._step_candidate(ts)
        transitions.extend(self._apply_boundary(ts, open_gates))
        return tuple(transitions)

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
        """Spec 21 §2: the first range past which every gate with evidence is low.

        Returns the candidate ``boundary_gate`` (``k - 1``), ``None`` for "no
        boundary, the whole range is in-room", or :data:`_UNEVALUATED` when
        there is not yet enough evidence to ask the question.
        """
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
        failing to apply until the episode blocking it closes, and then
        applies on the very next frame.
        """
        if self._confirm_count < self._config.boundary_confirm_days:
            return ()
        target = self._pending_boundary
        if target is _UNEVALUATED or target == self._boundary_gate:
            return ()

        current = self._boundary_gate
        retreat = target is not None and (current is None or target < current)
        if retreat and any(gate > target for gate in open_gates):
            # Spec 21 §3: never yank a gate out from under a person the
            # sensor is watching right now.
            if self._deferred_boundary == target:
                return ()  # this deferral has already been reported
            self._deferred_boundary = target
            return (
                BoundaryTransition(
                    ts=ts, previous=current, current=target, deferred=True
                ),
            )

        self._deferred_boundary = _UNEVALUATED
        self._boundary_gate = target
        return (BoundaryTransition(ts=ts, previous=current, current=target),)

    def evaluate(self, ts: float) -> tuple[GateTransition, ...]:
        """Reclassify every gate as of ``ts`` and return the changes."""
        self._last_eval_ts = ts
        transitions: list[GateTransition] = []
        for stat in self._stats:
            current = self._classify(stat, ts)
            if current != stat.gate_class:
                transitions.append(
                    GateTransition(
                        gate=stat.gate,
                        ts=ts,
                        previous=stat.gate_class,
                        current=current,
                    )
                )
                stat.gate_class = current
        return tuple(transitions)

    def _classify(self, stat: GateStats, ts: float) -> str:
        """Apply the spec 20 §3 rule to one gate's learned class.

        The manual ``max_gate`` override is deliberately not applied here -
        see :meth:`gate_class` - so it can be lifted without discarding what
        the gate had learned.
        """
        config = self._config
        half_life_s = config.stats_half_life_s
        n_sustained, n_brief = stat.decayed(ts, half_life_s)
        if n_sustained >= _IN_ROOM_SUSTAINED:
            return CLASS_IN_ROOM
        n_lead, n_dead = stat.decayed_outcomes(ts, half_life_s)
        if (
            n_lead >= config.n_portal_min
            and n_lead >= config.portal_lead_frac * (n_lead + n_dead)
        ):
            return CLASS_PORTAL
        stale = (
            stat.last_sustained_ts is None or ts - stat.last_sustained_ts > half_life_s
        )
        if (
            n_brief >= config.n_bleed_min
            and n_sustained < _BLEED_SUSTAINED_MAX
            and stale
        ):
            return CLASS_BLEED
        if stat.gate_class == CLASS_IN_ROOM:
            # Spec 20 §3 allows exactly one way out of IN_ROOM: the bleed rule
            # above. Falling back to UNKNOWN the instant the decayed count
            # slips under 1.0 - which is the very next frame after the episode
            # that promoted it - would make the class flap without changing
            # any behaviour, and would make the boundary_gate entity useless.
            return CLASS_IN_ROOM
        return CLASS_UNKNOWN

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe snapshot of the learned classification."""
        pending = self._pending_boundary
        return {
            "version": SCHEMA_VERSION,
            "last_eval_ts": self._last_eval_ts,
            "gates": [stat.to_dict() for stat in self._stats],
            "boundary_gate": self._boundary_gate,
            # A confirmation run that survived a restart is a confirmation run
            # that happened; throwing it away would make every restart cost
            # three more days before the boundary could take effect.
            "pending_boundary": None if pending is _UNEVALUATED else pending,
            "pending_evaluated": pending is not _UNEVALUATED,
            "confirm_count": self._confirm_count,
            "last_boundary_eval_ts": self._last_boundary_eval_ts,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], config: DetectorConfig) -> GateClassifier:
        """Rebuild a classifier from :meth:`to_dict` output.

        Accepts v1 (pre-energy-ceiling) as well as the current version: the
        ceiling fields are simply absent and start empty. Any *other* version
        raises ``ValueError``; callers treat that as "no persisted
        classification" and relearn, which costs one permissive month rather
        than acting on counts whose meaning has changed.
        """
        version = int(data["version"])
        if version not in _SUPPORTED_VERSIONS:
            raise ValueError(f"unsupported gate classifier schema version {version}")
        classifier = cls(config)
        gates = data["gates"]
        if len(gates) != GATE_COUNT:
            raise ValueError("gate classifier state has the wrong gate count")
        for stat, gate_data in zip(classifier.stats, gates, strict=True):
            stat.restore(gate_data)
        last_eval = data.get("last_eval_ts")
        classifier._last_eval_ts = None if last_eval is None else float(last_eval)
        boundary = data.get("boundary_gate")
        classifier._boundary_gate = None if boundary is None else int(boundary)
        if data.get("pending_evaluated"):
            pending = data.get("pending_boundary")
            classifier._pending_boundary = None if pending is None else int(pending)
            classifier._confirm_count = int(data.get("confirm_count", 0))
        last_boundary = data.get("last_boundary_eval_ts")
        classifier._last_boundary_eval_ts = (
            None if last_boundary is None else float(last_boundary)
        )
        return classifier
