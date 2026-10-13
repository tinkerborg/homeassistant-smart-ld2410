"""Hold-timer simulation and the specific timing questions the spec needs answered."""

from __future__ import annotations

import numpy as np

import data
import stats

WINDOW_S = 2.0


def flags(fx, floors, rule):
    st = stats.compute(fx.still, fx.ts, floors[fx.sensor]["still"], "still", WINDOW_S, None)
    return np.nan_to_num(rule(st).astype(float), nan=0.0) > 0


def simulate(ts, ok, hold_s):
    held = np.zeros(len(ts), dtype=bool)
    last = None
    for i in range(len(ts)):
        if ok[i]:
            last = ts[i]
        held[i] = last is not None and ts[i] - last <= hold_s
    return held


def transitions(ts, held):
    out = []
    for i in range(1, len(held)):
        if held[i] != held[i - 1]:
            out.append((ts[i], "latch" if held[i] else "release"))
    return out


RULES = {
    "g5>=6": lambda st: st["g5"] >= 6.0,
    "n_gates>=4": lambda st: st["n_gates"] >= 4.0,
    "deep_mass>=6": lambda st: st["deep_mass"] >= 6.0,
    "shoulder>=0.107": lambda st: st["shoulder"] >= 0.107,
    "level g3>=20": lambda st: st["g3"] >= 20.0,
    "level max(g2,g3)>=20": lambda st: np.maximum(st["g2"], st["g3"]) >= 20.0,
}


def main() -> None:
    fixtures = data.all_fixtures()
    floors = data.sensor_floors(fixtures)

    print("### stove-case-0913-d06e: walk-out 09:25:20, far kitchen to 09:50")
    fx = fixtures["stove-case-0913-d06e"]
    for name, rule in RULES.items():
        ok = flags(fx, floors, rule)
        for hold_s in (30.0, 60.0, 90.0):
            held = simulate(fx.ts, ok, hold_s)
            tr = [t for t in transitions(fx.ts, held) if t[0] >= data.local("2026-09-13 09:25:15")]
            tr = [t for t in tr if t[0] < data.local("2026-09-13 09:50:00")]
            rel = next((t for t, k in tr if k == "release"), None)
            latches = [t for t, k in tr if k == "latch"]
            first = f"{data.clock(rel)} (+{rel - data.local('2026-09-13 09:25:20'):.0f}s)" if rel else "never"
            m = fx.mask(data.local("2026-09-13 09:25:20"), data.local("2026-09-13 09:50:00"))
            print(f"  {name:22} hold={hold_s:4.0f}s  first release {first:22} "
                  f"relatches {len(latches):2d}  held {held[m].mean() * 100:5.1f}% of far-kitchen span")

    print("\n### livingroom 21:49 still minute (shipped detector released 21:49:56)")
    fx = fixtures["livingroom-reset-seated-fd68"]
    a, b = data.local("2026-09-11 21:49:00"), data.local("2026-09-11 21:50:00")
    m = fx.mask(a, b)
    for name, rule in RULES.items():
        ok = flags(fx, floors, rule)
        print(f"  {name:22} IN% {ok[m].mean() * 100:5.1f}")
    st = stats.compute(fx.still, fx.ts, floors["fd68"]["still"], "still", WINDOW_S, None)
    idx = np.flatnonzero(m)[::100]
    print("  raw still frames:")
    for i in idx:
        print(f"    {data.clock(fx.ts[i])} {fx.still[i].astype(int)} shoulder={st['shoulder'][i]:.2f} mass={st['mass'][i]:.0f}")

    print("\n### cat span 21:28-21:33")
    a, b = data.local("2026-09-11 21:28:00"), data.local("2026-09-11 21:33:00")
    m = fx.mask(a, b)
    for name, rule in RULES.items():
        ok = flags(fx, floors, rule)
        print(f"  {name:22} IN% {ok[m].mean() * 100:5.1f}")
    print("  raw still frames:")
    for i in np.flatnonzero(m)[::250]:
        print(f"    {data.clock(fx.ts[i])} {fx.still[i].astype(int)} centroid={st['centroid'][i]:.2f} shoulder={st['shoulder'][i]:.2f}")


if __name__ == "__main__":
    main()
