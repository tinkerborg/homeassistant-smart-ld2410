"""How far the very-still living-room minute sits above the empty floor."""

from __future__ import annotations

import numpy as np

import data
import stats

fx = data.all_fixtures()
floors = data.sensor_floors(fx)
lr = fx["livingroom-reset-seated-fd68"]

for window in (0.0, 2.0, 5.0, 30.0):
    st = stats.compute(lr.still, lr.ts, floors["fd68"]["still"], "still", window, None)
    quiet = lr.mask(data.local("2026-09-11 21:49:00"), data.local("2026-09-11 21:50:00"))
    empty = lr.class_mask("EMPTY")
    pet = lr.class_mask("PET")
    for k in ("mass", "shoulder", "deep_mass", "centroid"):
        q = st[k][quiet]
        e = st[k][empty]
        q, e = q[np.isfinite(q)], e[np.isfinite(e)]
        pct = (e[:, None] < q[None, :]).mean(axis=0).mean() * 100
        print(f"w={window:4.0f} {k:10} quiet p50={np.median(q):7.3f} empty p50={np.median(e):7.3f} "
              f"empty p95={np.percentile(e, 95):7.3f}  quiet sits at empty-percentile {pct:5.1f}")
    print()

st = stats.compute(lr.still, lr.ts, floors["fd68"]["still"], "still", 30.0, None)
for name, a, b in (("quiet 21:49", "2026-09-11 21:49:00", "2026-09-11 21:50:00"),
                   ("empty 21:22", "2026-09-11 21:22:00", "2026-09-11 21:27:00"),
                   ("empty 21:35", "2026-09-11 21:35:00", "2026-09-11 21:39:00"),
                   ("pet 21:30", "2026-09-11 21:30:00", "2026-09-11 21:32:00")):
    m = lr.mask(data.local(a), data.local(b))
    print(f"{name:12} mean raw still {lr.still[m].mean(axis=0).round(2)}")
