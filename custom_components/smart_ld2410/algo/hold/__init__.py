"""What keeps an occupancy alive for another hold window."""

from __future__ import annotations

from ..roles import Stage
from .attributed_hold import AttributedHold
from .retention_hold import RetentionHold
from .score_hold import ScoreHold

STAGES: dict[str, type[Stage]] = {
    "score_hold": ScoreHold,
    "attributed_hold": AttributedHold,
    "retention_hold": RetentionHold,
}
"""The hold refreshers, by the name a config lists them under."""
