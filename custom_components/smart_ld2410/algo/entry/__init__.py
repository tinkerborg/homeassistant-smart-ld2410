"""The filters a candidate must clear before it becomes an occupancy."""

from __future__ import annotations

from ..roles import Stage
from .arrival import ArrivalGate
from .energy_floor import EnergyFloor
from .leading_edge import LeadingEdge

STAGES: dict[str, type[Stage]] = {
    "energy_floor": EnergyFloor,
    "arrival": ArrivalGate,
    "leading_edge": LeadingEdge,
}
"""The entry filters, by the name a config lists them under."""
