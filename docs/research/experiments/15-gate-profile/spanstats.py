"""Per-span medians of the candidate shape statistics."""

from __future__ import annotations

import numpy as np

import data
import stats

KEYS = ["mass", "n_gates", "deep_mass", "deep_frac", "lead_frac", "shoulder", "tail", "fall1", "fall2", "centroid", "spread"]


def main() -> None:
    fixtures = data.all_fixtures()
    floors = data.sensor_floors(fixtures)
    print(f"{'fixture':28} {'cls':6} {'span':19} {'len':>6} " + " ".join(f"{k:>9}" for k in KEYS))
    for fx in fixtures.values():
        st = stats.compute(fx.still, fx.ts, floors[fx.sensor]["still"], "still", 2.0, None)
        for cls, a, b in fx.spans:
            m = fx.mask(a, b)
            if m.sum() < 20:
                continue
            row = []
            for k in KEYS:
                v = st[k][m]
                v = v[np.isfinite(v)]
                row.append(np.median(v) if len(v) else float("nan"))
            span = f"{data.clock(a)}-{data.clock(b)}"
            print(f"{fx.name:28} {cls:6} {span:19} {b-a:6.0f} " + " ".join(f"{x:9.3f}" for x in row))


if __name__ == "__main__":
    main()
