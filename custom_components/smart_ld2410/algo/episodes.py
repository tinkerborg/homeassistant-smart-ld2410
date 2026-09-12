"""Episode segmentation over the detector's own smoothed residuals (spec 20 §1).

An *episode* is a maximal interval during which one gate's smoothed residual
stays elevated. The smoothing is not a second pipeline: it is literally the
support EMA the detector already maintains for its neighbour-support test, so
an episode boundary and a coherence decision can never disagree about how hot
a gate was.

Two scopes come out of the same pass:

* **Per-gate episodes** are what the dwell-character classifier learns from.
  A gate that only ever sees three-second sweeps is bleed; a gate that
  regularly settles into a minute of still presence is in-room.
* **The detection-scope episode** spans the union of the open gate episodes.
  It is the row the interfaces contract describes - a band with a centroid
  that moves - because a single gate has no centroid worth recording.

All timing comes from ``Frame.ts_utc``: episode rows are persisted and
compared against wall-clock-stamped data, and ``ts_mono`` restarts partway
through any recording that spans a restart. Nothing here reads a clock.

Three things close an episode:

* the gate falls under ``s_gate_off`` and stays there for ``gap_close_s``;
* occupancy releases, for a detection-scope episode that entered it. An
  entered episode is bounded by the occupancy it belongs to; waiting for every
  gate in the band to fall quiet at once is a condition a lived-in room can go
  days without meeting;
* the frame stream stalls for longer than ``episode_stall_s``. Everything open
  then closes as of the last frame *before* the gap, never at the resuming
  frame's timestamp, so ``t1`` is always the last moment the signal was
  observed up and no duration contains unmeasured time.
"""

from __future__ import annotations

from .types import (
    GATE_COUNT,
    RESULT_ENTERED,
    RESULT_REJECTED_ARRIVAL,
    RESULT_REJECTED_COHERENCE,
    RESULT_REJECTED_ENERGY_FLOOR,
    RESULT_REJECTED_HYSTERESIS,
    RESULT_REJECTED_LEADING_EDGE,
    SCOPE_DETECTION,
    SCOPE_GATE,
    DetectorConfig,
    Episode,
)


def _active_frac(active_time: float, span: float) -> float:
    """Share of ``span`` the signal was up, clamped to 0..1."""
    if span <= 0.0:
        return 1.0
    return min(1.0, active_time / span)


def _result(
    saw_occupied: bool,
    saw_active: bool,
    saw_energy_floor: bool,
    saw_arrival: bool,
    saw_leading_edge: bool,
) -> str:
    """Classify how an episode ended relative to the occupancy decision."""
    if saw_occupied:
        return RESULT_ENTERED
    if not saw_active:
        # The gate was hot but never survived the spatial-coherence test, so
        # it never even reached the hysteresis machine.
        return RESULT_REJECTED_COHERENCE
    # Each entry rule only ever blocks a frame the ones before it let through,
    # so the last one to fire is the most specific answer to "why not".
    if saw_leading_edge:
        return RESULT_REJECTED_LEADING_EDGE
    if saw_arrival:
        return RESULT_REJECTED_ARRIVAL
    if saw_energy_floor:
        return RESULT_REJECTED_ENERGY_FLOOR
    return RESULT_REJECTED_HYSTERESIS


def _nearer(current: int | None, candidate: int | None) -> int | None:
    """The nearer of two gates, either of which may be absent."""
    if candidate is None:
        return current
    if current is None:
        return candidate
    return min(current, candidate)


class _OpenGateEpisode:
    """Accumulator for one gate's in-progress episode."""

    __slots__ = (
        "active_time",
        "below_since",
        "gate",
        "last_ts",
        "leading_gate",
        "peak",
        "peak_raw",
        "saw_active",
        "saw_arrival",
        "saw_energy_floor",
        "saw_leading_edge",
        "saw_occupied",
        "still_time",
        "t0",
        "t1",
    )

    def __init__(self, gate: int, ts: float) -> None:
        """Open an episode for ``gate`` at frame time ``ts``."""
        self.gate = gate
        self.t0 = ts
        self.t1 = ts
        self.last_ts = ts
        self.peak = 0.0
        # Peak raw move energy at this gate: one scalar, because a per-gate
        # episode's span is one gate. It becomes gate_peaks[gate] at close.
        self.peak_raw = 0
        self.active_time = 0.0
        self.still_time = 0.0
        self.below_since: float | None = None
        self.saw_active = False
        self.saw_occupied = False
        self.saw_energy_floor = False
        self.saw_arrival = False
        self.saw_leading_edge = False
        self.leading_gate: int | None = None

    def close(self) -> Episode:
        """Freeze this accumulator into an :class:`Episode` row."""
        still_frac = (
            self.still_time / self.active_time if self.active_time > 0.0 else 0.0
        )
        gate_peaks = [0] * GATE_COUNT
        active_frac = _active_frac(self.active_time, self.t1 - self.t0)
        gate_peaks[self.gate] = self.peak_raw
        return Episode(
            scope=SCOPE_GATE,
            gate=self.gate,
            t0=self.t0,
            t1=self.t1,
            peak_residual=self.peak,
            gate_lo=self.gate,
            gate_hi=self.gate,
            centroid_mean=float(self.gate),
            centroid_vel=0.0,
            still_frac=still_frac,
            result=_result(
                self.saw_occupied,
                self.saw_active,
                self.saw_energy_floor,
                self.saw_arrival,
                self.saw_leading_edge,
            ),
            active_frac=active_frac,
            gate_peaks=tuple(gate_peaks),
            leading_gate=self.leading_gate,
        )


class _OpenDetectionEpisode:
    """Accumulator for the union-of-gates episode."""

    __slots__ = (
        "active_time",
        "centroid_time_sum",
        "first_centroid",
        "gate_hi",
        "gate_lo",
        "gate_peaks",
        "last_centroid",
        "last_ts",
        "leading_gate",
        "peak",
        "saw_active",
        "saw_arrival",
        "saw_energy_floor",
        "saw_leading_edge",
        "saw_occupied",
        "still_time",
        "t0",
        "t1",
    )

    def __init__(self, ts: float, gate: int) -> None:
        """Open the detection episode at ``ts`` with its first hot gate."""
        self.t0 = ts
        self.t1 = ts
        self.last_ts = ts
        self.gate_lo = gate
        self.gate_hi = gate
        self.peak = 0.0
        self.gate_peaks = [0] * GATE_COUNT
        self.active_time = 0.0
        self.still_time = 0.0
        self.centroid_time_sum = 0.0
        self.first_centroid: float | None = None
        self.last_centroid = float(gate)
        self.saw_active = False
        self.saw_occupied = False
        self.saw_energy_floor = False
        self.saw_arrival = False
        self.saw_leading_edge = False
        self.leading_gate: int | None = None

    def close(self) -> Episode:
        """Freeze this accumulator into an :class:`Episode` row."""
        duration = self.t1 - self.t0
        first = (
            self.last_centroid if self.first_centroid is None else self.first_centroid
        )
        # Gates per second across the episode: enough to separate a sweep
        # through the band from a body that arrived and stayed.
        velocity = (self.last_centroid - first) / duration if duration > 0.0 else 0.0
        if self.active_time > 0.0:
            centroid_mean = self.centroid_time_sum / self.active_time
            still_frac = self.still_time / self.active_time
        else:
            centroid_mean = self.last_centroid
            still_frac = 0.0
        return Episode(
            scope=SCOPE_DETECTION,
            gate=None,
            t0=self.t0,
            t1=self.t1,
            peak_residual=self.peak,
            gate_lo=self.gate_lo,
            gate_hi=self.gate_hi,
            centroid_mean=centroid_mean,
            centroid_vel=velocity,
            still_frac=still_frac,
            result=_result(
                self.saw_occupied,
                self.saw_active,
                self.saw_energy_floor,
                self.saw_arrival,
                self.saw_leading_edge,
            ),
            active_frac=_active_frac(self.active_time, duration),
            gate_peaks=tuple(self.gate_peaks),
            leading_gate=self.leading_gate,
        )


class EpisodeTracker:
    """Turns a stream of smoothed residuals into closed :class:`Episode` rows."""

    __slots__ = ("_awaiting_quiet", "_config", "_detection", "_last_frame_ts", "_open")

    def __init__(self, config: DetectorConfig) -> None:
        """Create a tracker reading its thresholds from ``config``."""
        self._config = config
        self._open: dict[int, _OpenGateEpisode] = {}
        self._detection: _OpenDetectionEpisode | None = None
        self._last_frame_ts: float | None = None
        self._awaiting_quiet = False

    def reconfigure(self, config: DetectorConfig) -> None:
        """Adopt new thresholds without dropping episodes already open."""
        self._config = config

    @property
    def open_gates(self) -> tuple[int, ...]:
        """Gates with an episode currently open, ascending."""
        return tuple(sorted(self._open))

    @property
    def open_starts(self) -> tuple[float, ...]:
        """Start times of the episodes currently open, by ascending gate."""
        return tuple(self._open[gate].t0 for gate in sorted(self._open))

    def process(
        self,
        *,
        ts: float,
        peaks: tuple[float, ...],
        support: list[float],
        residuals_move: tuple[float, ...],
        residuals_still: tuple[float, ...],
        move_raw: tuple[int, ...],
        active_gates: tuple[int, ...],
        occupied: bool,
        entry_suppressed: bool = False,
        arrival_suppressed: bool = False,
        lead_suppressed: bool = False,
        leading_gate: int | None = None,
    ) -> tuple[Episode, ...]:
        """Fold one frame in and return whatever episodes it closed.

        Per-gate episodes come first, then the detection-scope episode when it
        ends with this frame.

        ``move_raw`` is the frame's unmodified move-channel energies, feeding
        the energy ceiling, which must not depend on the baseline.
        ``occupied`` is the detector's post-hysteresis state for this frame;
        ``entry_suppressed`` says a rule held it down; ``arrival_suppressed``
        and ``lead_suppressed`` say which one. ``leading_gate`` is the nearest
        gate elevated above its learned quiet level.
        """
        config = self._config
        on = config.s_gate_on
        off = config.s_gate_off
        gap = config.episode_gap_close_s
        closed: list[Episode] = []
        any_elevated = False
        if occupied:
            self._awaiting_quiet = False

        previous_frame_ts = self._last_frame_ts
        self._last_frame_ts = ts
        if (
            previous_frame_ts is not None
            and ts - previous_frame_ts > config.episode_stall_s
        ):
            # Closed before this frame is folded in, so nothing open is
            # stretched across the outage.
            closed.extend(self._close_all())

        for gate in range(GATE_COUNT):
            level = support[gate]
            episode = self._open.get(gate)
            if episode is None:
                if level < on:
                    continue
                episode = _OpenGateEpisode(gate, ts)
                self._open[gate] = episode
                self._widen_detection(ts, gate)

            # Clamped so a sparse stretch of frames cannot credit an episode
            # with more active time than was measured.
            elapsed = min(max(ts - episode.last_ts, 0.0), gap)
            stalled = ts - episode.last_ts > gap
            episode.last_ts = ts

            if level >= off:
                any_elevated = True
                episode.below_since = None
                episode.t1 = ts
                episode.peak = max(episode.peak, peaks[gate])
                episode.peak_raw = max(episode.peak_raw, move_raw[gate])
                episode.active_time += elapsed
                if residuals_still[gate] > residuals_move[gate]:
                    episode.still_time += elapsed
                episode.saw_active |= gate in active_gates
                episode.saw_occupied |= occupied
                episode.saw_energy_floor |= (
                    entry_suppressed and not arrival_suppressed and not lead_suppressed
                )
                episode.saw_arrival |= arrival_suppressed
                episode.saw_leading_edge |= lead_suppressed
                episode.leading_gate = _nearer(episode.leading_gate, leading_gate)
                self._widen_detection(ts, gate)
                continue

            if episode.below_since is None:
                episode.below_since = ts
            # A gap longer than gap_close_s that resumes with a quiet gate
            # closes at once: the quiet is already known to have outlasted the
            # close window.
            if stalled or ts - episode.below_since >= gap:
                closed.append(episode.close())
                del self._open[gate]

        if any_elevated:
            self._accumulate_detection(
                ts=ts,
                gap=gap,
                on=on,
                peaks=peaks,
                support=support,
                residuals_move=residuals_move,
                residuals_still=residuals_still,
                move_raw=move_raw,
                active_gates=active_gates,
                occupied=occupied,
                entry_suppressed=entry_suppressed,
                arrival_suppressed=arrival_suppressed,
                lead_suppressed=lead_suppressed,
                leading_gate=leading_gate,
            )

        detection = self._detection
        if not self._open:
            self._awaiting_quiet = False
        if detection is not None and (
            not self._open or (detection.saw_occupied and not occupied)
        ):
            closed.append(detection.close())
            self._detection = None
            # A gate still hot here is the tail of the departure, so it must
            # not open a fresh detection episode of its own.
            self._awaiting_quiet = bool(self._open)
        return tuple(closed)

    def _close_all(self) -> list[Episode]:
        """Close every open episode, gates first, and forget them."""
        closed = [self._open[gate].close() for gate in sorted(self._open)]
        self._open.clear()
        if self._detection is not None:
            closed.append(self._detection.close())
            self._detection = None
        self._awaiting_quiet = False
        return closed

    def _widen_detection(self, ts: float, gate: int) -> None:
        """Start the detection-scope episode, or stretch it over ``gate``."""
        detection = self._detection
        if detection is None and self._awaiting_quiet:
            return
        if detection is None:
            self._detection = _OpenDetectionEpisode(ts, gate)
            return
        detection.gate_lo = min(detection.gate_lo, gate)
        detection.gate_hi = max(detection.gate_hi, gate)
        detection.t1 = max(detection.t1, ts)

    def _accumulate_detection(
        self,
        *,
        ts: float,
        gap: float,
        on: float,
        peaks: tuple[float, ...],
        support: list[float],
        residuals_move: tuple[float, ...],
        residuals_still: tuple[float, ...],
        move_raw: tuple[int, ...],
        active_gates: tuple[int, ...],
        occupied: bool,
        entry_suppressed: bool,
        arrival_suppressed: bool,
        lead_suppressed: bool,
        leading_gate: int | None,
    ) -> None:
        """Fold this frame's band-wide quantities into the detection episode.

        Runs exactly once per frame, after every gate has been stepped, so the
        centroid it records is the whole band's and not one gate's view of it.
        """
        detection = self._detection
        if detection is None:
            return
        elapsed = min(max(ts - detection.last_ts, 0.0), gap)
        detection.last_ts = ts
        detection.active_time += elapsed
        detection.peak = max(detection.peak, max(peaks))
        # Only gates that are actually elevated contribute to the raw-energy
        # profile: an idle gate's floor is not evidence about this episode.
        for gate in range(GATE_COUNT):
            if support[gate] >= on and move_raw[gate] > detection.gate_peaks[gate]:
                detection.gate_peaks[gate] = move_raw[gate]
        detection.saw_active |= bool(active_gates)
        detection.saw_occupied |= occupied
        detection.saw_energy_floor |= (
            entry_suppressed and not arrival_suppressed and not lead_suppressed
        )
        detection.saw_arrival |= arrival_suppressed
        detection.saw_leading_edge |= lead_suppressed
        detection.leading_gate = _nearer(detection.leading_gate, leading_gate)

        centroid = _centroid(peaks, support, on)
        if centroid is not None:
            if detection.first_centroid is None:
                detection.first_centroid = centroid
            detection.last_centroid = centroid
        detection.centroid_time_sum += detection.last_centroid * elapsed

        move_mass = sum(value for value in residuals_move if value > 0.0)
        still_mass = sum(value for value in residuals_still if value > 0.0)
        if still_mass > move_mass:
            detection.still_time += elapsed


def _centroid(
    peaks: tuple[float, ...], support: list[float], on: float
) -> float | None:
    """Residual-weighted mean gate index over the currently elevated gates."""
    weight = 0.0
    total = 0.0
    for gate in range(GATE_COUNT):
        if support[gate] < on:
            continue
        value = peaks[gate]
        if value <= 0.0:
            continue
        weight += value
        total += value * gate
    if weight <= 0.0:
        return None
    return total / weight
