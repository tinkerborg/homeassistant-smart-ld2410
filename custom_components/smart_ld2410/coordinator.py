"""Push-mode data coordinator driving the detector off streamed BLE frames."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .algo.detector import Detector
from .algo.types import DetectorConfig, DetectorOutput, Frame, GATE_COUNT
from .const import COORDINATOR_PUSH_INTERVAL_S, DOMAIN
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

        due = (
            self._last_push_mono is None
            or frame.ts_mono - self._last_push_mono >= COORDINATOR_PUSH_INTERVAL_S
        )
        if occupancy_changed or due:
            self._last_push_mono = frame.ts_mono
            self.async_set_updated_data(output)
        else:
            self.data = output

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
