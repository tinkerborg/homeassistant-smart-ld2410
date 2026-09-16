"""Exponential decay of learned per-gate evidence, in frame time.

Every gate statistic is decayed with the same half-life so the model tracks a
home that changes: move a sofa and the old dwell gate demotes itself over a
month, without ever needing a reset button.
"""

from __future__ import annotations


def decay_factor(updated_ts: float | None, ts: float, half_life_s: float) -> float:
    """Return the decay multiplier between ``updated_ts`` and ``ts``."""
    if updated_ts is None or half_life_s <= 0.0:
        return 1.0
    elapsed = ts - updated_ts
    if elapsed <= 0.0:
        # Frame time can repeat, and a recording can be replayed out of order
        # by a caller; neither may resurrect decayed evidence.
        return 1.0
    return 0.5 ** (elapsed / half_life_s)
