"""The learned empty-room energy level, read as the lowest recurring peak.

A gate someone sits in front of can spend more of the window at the occupant's
level than at the empty room's, so its dominant peak is the occupant. The empty
room still recurs: any peak holding a minute's worth of samples is a level the
gate really rests at, and the lowest such peak is the one nobody adds energy
to.

All timing comes from ``Frame.ts_utc``; nothing here reads a clock.
"""

from __future__ import annotations

from ..roles import StageEnv
from ..types import CHANNEL_MOVE, Frame
from .histogram_floor import HistogramFloor

FLOOR_REFRESH_S = 5.0
"""Frame-time interval at which the recurring peak is re-read."""


class RecurringFloor(HistogramFloor):
    """Per-channel noise floor: the lowest histogram peak that recurs for ``mode_min_s``."""

    __slots__ = ("_refreshed_at",)

    def __init__(self, env: StageEnv) -> None:
        """Start an empty floor over the window ``env`` describes."""
        super().__init__(env)
        self._refreshed_at: float | None = None

    def add_frame(self, frame: Frame) -> None:
        """Ingest one frame, re-reading the peaks once per refresh interval."""
        super().add_frame(frame)
        recurring_s = self._config.mode_min_s
        if not self._channels[CHANNEL_MOVE][0].observed_enough(recurring_s):
            return
        if (
            self._refreshed_at is not None
            and frame.ts_utc - self._refreshed_at < FLOOR_REFRESH_S
        ):
            return
        for channels in self._channels.values():
            for channel in channels:
                channel.settle_on_recurring_peak(recurring_s)
        self._refreshed_at = frame.ts_utc

    def value(self, channel: str, gate: int) -> float:
        """The learned empty-room level of one channel (0.0 while untrusted)."""
        return self._channels[channel][gate].settled_floor

    def trusted(self, channel: str, gate: int) -> bool:
        """Whether the channel has settled on a peak yet."""
        return self._channels[channel][gate].settled
