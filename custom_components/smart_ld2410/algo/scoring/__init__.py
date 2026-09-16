"""How a frame's per-gate elevations become one score and one active band."""

from __future__ import annotations

from ..roles import Stage
from .runs import RunScorer
from .suppression import LoneGateSuppression

STAGES: dict[str, type[Stage]] = {
    "run_score": RunScorer,
    "lone_gate_suppression": LoneGateSuppression,
}
"""The scoring stages, by the name a config lists them under."""
