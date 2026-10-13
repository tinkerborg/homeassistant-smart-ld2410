"""What ends an occupancy before its hold window would."""

from __future__ import annotations

from ..roles import Stage
from .changepoint import ChangepointRelease
from .nearest_gate import NearestGateRelease

STAGES: dict[str, type[Stage]] = {
    "nearest_gate_release": NearestGateRelease,
    "changepoint_release": ChangepointRelease,
}
"""The release paths, by the name a config lists them under."""
