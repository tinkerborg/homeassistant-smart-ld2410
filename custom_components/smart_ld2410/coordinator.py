"""Push-mode data coordinator driving the detector off streamed BLE frames."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .algo.detector import Detector
from .algo.types import GATE_COUNT, SCOPE_DETECTION, DetectorConfig, DetectorOutput, Frame
from .const import (
    COORDINATOR_PUSH_INTERVAL_S,
    DOMAIN,
    EVENT_EPISODE,
    EVENT_KIND_BOUNDARY,
    EVENT_KIND_LABEL,
    FEATURES_PUSH_INTERVAL_S,
    FEATURES_SCHEMA_VERSION,
    MODE_LEARNED,
    MODE_PASSTHROUGH,
    SIGNAL_FEATURES_V1,
)
from .store import FrameStore

if TYPE_CHECKING:
    from . import SmartLD2410ConfigEntry

_LOGGER = logging.getLogger(__name__)

_ZERO_RESIDUALS: tuple[float, ...] = (0.0,) * GATE_COUNT

_INITIAL_OUTPUT = DetectorOutput(
    occupied=False,
    confidence=0.0,
    score=0.0,
    active_gates=(),
    residuals_move=_ZERO_RESIDUALS,
    residuals_still=_ZERO_RESIDUALS,
    adaptation_frozen=False,
    baseline_age_s=0.0,
    baseline_ready=False,
)


def detector_mode(output: DetectorOutput) -> str:
    """Return 'learned'/'passthrough' from DetectorOutput.baseline_ready.

    Shared by the occupancy binary_sensor's ``mode`` attribute, the target
    distance sensor's fallback logic, and the feature stream (contract §1.1,
    §1.2), so the three can never disagree about what "learned" means.
    """
    return MODE_LEARNED if output.baseline_ready else MODE_PASSTHROUGH


def detector_peaks(output: DetectorOutput) -> tuple[float, ...]:
    """Clamp signed residuals to non-negative evidence, as Detector._score does.

    Negative residuals ("quieter than the noise floor") carry no evidence of
    presence for centroid/span purposes either.
    """
    residuals_move = output.residuals_move
    residuals_still = output.residuals_still
    return tuple(
        max(0.0, residuals_move[gate], residuals_still[gate])
        for gate in range(GATE_COUNT)
    )


def weighted_centroid_and_span(
    peaks: tuple[float, ...], active_gates: tuple[int, ...]
) -> tuple[float, float]:
    """Residual-weighted mean and std of gate index over ``active_gates``.

    Returns ``(0.0, 0.0)`` when there is no active band to weight over.
    """
    weight = 0.0
    total = 0.0
    for gate in active_gates:
        value = peaks[gate]
        if value <= 0.0:
            continue
        weight += value
        total += value * gate
    if weight <= 0.0:
        return 0.0, 0.0
    mean = total / weight
    variance = (
        sum(peaks[gate] * (gate - mean) ** 2 for gate in active_gates if peaks[gate] > 0.0)
        / weight
    )
    return mean, variance**0.5


def edge_band(active_gates: tuple[int, ...], last_in_room_gate: int | None) -> str:
    """near/far/none: whether the active band touches an edge (contract §1.2).

    ``near`` if it touches gate 0-1; ``far`` if it reaches the last in-room
    gate (:attr:`GateClassifier.last_in_room_gate`, not the spec 21 learned
    boundary - handoff cares about how far presence has actually been seen);
    ``none`` otherwise, including when nothing is active.
    """
    if not active_gates:
        return "none"
    if min(active_gates) <= 1:
        return "near"
    if last_in_room_gate is not None and max(active_gates) >= last_in_room_gate:
        return "far"
    return "none"


def build_features_payload(
    output: DetectorOutput, *, sensor_id: str, ts: float
) -> dict[str, Any]:
    """Build the smart_ld2410_features_v1 dispatcher payload (contract §1.2)."""
    peaks = detector_peaks(output)
    active_gates = output.active_gates
    centroid_gate, gate_span = weighted_centroid_and_span(peaks, active_gates)
    residual_mass_move = sum(
        max(0.0, output.residuals_move[gate]) for gate in active_gates
    )
    residual_mass_still = sum(
        max(0.0, output.residuals_still[gate]) for gate in active_gates
    )
    return {
        "schema": FEATURES_SCHEMA_VERSION,
        "sensor_id": sensor_id,
        "ts": ts,
        "occ": output.occupied,
        "confidence": output.confidence,
        "centroid_gate": centroid_gate,
        "gate_span": gate_span,
        "residual_mass_move": residual_mass_move,
        "residual_mass_still": residual_mass_still,
        "edge_band": edge_band(active_gates, output.last_in_room_gate),
        "mode": detector_mode(output),
    }


class SmartLD2410Coordinator(DataUpdateCoordinator[DetectorOutput]):
    """Runs the detector on every streamed frame and paces HA state writes.

    Frames arrive at ~10Hz from :class:`LD2410Client` and are queued to the
    store and run through the detector unconditionally (both are cheap, pure
    CPU / non-blocking). Only ``async_set_updated_data`` calls — the ones that
    trigger entity state writes — are paced: immediately on an occupancy flip
    or an availability change, otherwise at most once a second.
    """

    config_entry: SmartLD2410ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: SmartLD2410ConfigEntry,
        detector: Detector,
        store: FrameStore,
        address: str,
    ) -> None:
        """Initialise the coordinator over an already-built detector."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=DOMAIN,
            update_interval=None,
        )
        self.detector = detector
        self.address = address
        self.available = True
        self.latest_frame: Frame | None = None
        self.data = _INITIAL_OUTPUT
        self._store = store
        self._last_push_mono: float | None = None
        self._last_features_mono: float | None = None

    def reconfigure(self, config: DetectorConfig) -> None:
        """Apply new tuning knobs to the detector without losing state."""
        self.detector.reconfigure(config)

    @callback
    def async_on_frame(self, frame: Frame) -> None:
        """Handle one streamed frame: queue, detect, pace the HA update."""
        self._store.enqueue_frame(self.address, frame)
        self.latest_frame = frame

        previous_occupied = self.data.occupied
        output = self.detector.process(frame)

        occupancy_changed = previous_occupied != output.occupied
        if occupancy_changed:
            self._store.enqueue_event(
                self.address,
                frame.ts_utc,
                "occupied" if output.occupied else "vacant",
                {
                    "confidence": output.confidence,
                    "score": output.score,
                    "active_gates": list(output.active_gates),
                },
            )

        for episode in output.episodes:
            if episode.scope != SCOPE_DETECTION:
                # Per-gate episodes drive the classifier in-process only; the
                # interfaces contract's `episodes` table is detection-scope.
                continue
            self._store.enqueue_episode(self.address, episode)
            self.hass.bus.async_fire(
                EVENT_EPISODE,
                {
                    "sensor_id": self.address,
                    "t0": episode.t0,
                    "t1": episode.t1,
                    "peak_residual": episode.peak_residual,
                    "gate_lo": episode.gate_lo,
                    "gate_hi": episode.gate_hi,
                    "centroid_mean": episode.centroid_mean,
                    "centroid_vel": episode.centroid_vel,
                    "still_frac": episode.still_frac,
                    "result": episode.result,
                    "leading_gate": episode.leading_gate,
                },
            )

        for transition in output.gate_transitions:
            self._store.enqueue_event(
                self.address,
                transition.ts,
                transition.current,
                {
                    "gate": transition.gate,
                    "previous": transition.previous,
                    "current": transition.current,
                },
            )

        for boundary in output.boundary_transitions:
            self._store.enqueue_event(
                self.address,
                boundary.ts,
                EVENT_KIND_BOUNDARY,
                {
                    "previous": boundary.previous,
                    "current": boundary.current,
                    "deferred": boundary.deferred,
                    "enabled": self.detector.config.ceiling_enabled,
                },
            )

        features_due = (
            self._last_features_mono is None
            or frame.ts_mono - self._last_features_mono >= FEATURES_PUSH_INTERVAL_S
        )
        if features_due:
            self._last_features_mono = frame.ts_mono
            async_dispatcher_send(
                self.hass,
                SIGNAL_FEATURES_V1,
                build_features_payload(output, sensor_id=self.address, ts=frame.ts_utc),
            )

        due = (
            self._last_push_mono is None
            or frame.ts_mono - self._last_push_mono >= COORDINATOR_PUSH_INTERVAL_S
        )
        if occupancy_changed or due:
            self._last_push_mono = frame.ts_mono
            self.async_set_updated_data(output)
        else:
            self.data = output

    def enqueue_label_event(self, ts_utc: float, label: str) -> None:
        """Record a ground-truth label change for offline interval derivation."""
        self._store.enqueue_event(self.address, ts_utc, EVENT_KIND_LABEL, {"label": label})

    @callback
    def async_on_availability(self, available: bool) -> None:
        """Handle a BLE connect/disconnect transition from the client."""
        if available == self.available:
            return
        self.available = available
        self._store.enqueue_event(
            self.address,
            time.time(),
            "connect" if available else "disconnect",
        )
        self.async_update_listeners()
