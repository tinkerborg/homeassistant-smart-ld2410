"""Run-length behaviour of candidate profile rules inside each ground-truth span."""

from __future__ import annotations

import numpy as np

import data
import stats

GAP_S = 2.0
WINDOW_S = 2.0


def rule_depth(st):
    return st["g5"] >= 6.0


def rule_n_gates(st):
    return st["n_gates"] >= 4.0


def rule_lead(st):
    return st["lead_frac"] >= 0.481


def rule_deep_mass(st):
    return st["deep_mass"] >= 6.0


def rule_lead_and_depth(st):
    return (st["lead_frac"] >= 0.481) & (st["g5"] >= 6.0)


def rule_lead_and_n_gates(st):
    return (st["lead_frac"] >= 0.481) & (st["n_gates"] >= 4.0)


def rule_level(st):
    return np.maximum(st["g2"], st["g3"]) >= 20.0


def rule_shoulder(st):
    return st["shoulder"] >= 0.107


def rule_g3(st):
    return st["g3"] >= 1.0


def rule_g4(st):
    return st["g4"] >= 0.667


def rule_shoulder_and_mass(st):
    return (st["shoulder"] >= 0.107) & (st["mass"] >= 6.0)


RULES = {
    "d06e": [
        ("still g5>=6", rule_depth),
        ("still n_gates>=4", rule_n_gates),
        ("still lead_frac>=0.481", rule_lead),
        ("still deep_mass>=6", rule_deep_mass),
        ("still lead_frac & g5", rule_lead_and_depth),
        ("still lead_frac & n_gates", rule_lead_and_n_gates),
        ("baseline level max(g2,g3)>=20", rule_level),
    ],
    "fd68": [
        ("still shoulder>=0.107", rule_shoulder),
        ("still g3>=1", rule_g3),
        ("still g4>=0.667", rule_g4),
        ("still shoulder & mass>=6", rule_shoulder_and_mass),
        ("still n_gates>=4", rule_n_gates),
        ("baseline level max(g2,g3)>=20", rule_level),
    ],
}


def longest_run(ts, ok, want, break_on_gap):
    best = 0.0
    start = None
    prev = None
    for i in range(len(ts)):
        broken = prev is not None and break_on_gap and ts[i] - prev > GAP_S
        if ok[i] == want:
            if start is None:
                start = ts[i]
            elif broken:
                best = max(best, prev - start)
                start = ts[i]
        elif start is not None:
            best = max(best, prev - start)
            start = None
        prev = ts[i]
    if start is not None:
        best = max(best, prev - start)
    return best


def main() -> None:
    fixtures = data.all_fixtures()
    floors = data.sensor_floors(fixtures)
    computed = {
        n: stats.compute(fx.still, fx.ts, floors[fx.sensor]["still"], "still", WINDOW_S, None)
        for n, fx in fixtures.items()
    }
    for sensor, rules in RULES.items():
        for name, rule in rules:
            print(f"\n===== {sensor} :: {name}")
            print(f"{'fixture':30} {'class':6} {'span':19} {'len_s':>7} {'IN%':>6} {'longestIN':>10} {'longestNOT':>11}")
            worst_in_gap = 0.0
            worst_neg_run = 0.0
            for n, fx in fixtures.items():
                if fx.sensor != sensor:
                    continue
                st = computed[n]
                ok = np.nan_to_num(rule(st).astype(float), nan=0.0) > 0
                for cls, a, b in fx.spans:
                    m = fx.mask(a, b)
                    if m.sum() < 20:
                        continue
                    ts, o = fx.ts[m], ok[m]
                    r_in = longest_run(ts, o, True, True)
                    r_out = longest_run(ts, o, False, False)
                    if cls == "IN":
                        worst_in_gap = max(worst_in_gap, r_out)
                    elif cls in ("TW", "EMPTY"):
                        worst_neg_run = max(worst_neg_run, r_in)
                    span = f"{data.clock(a)}-{data.clock(b)}"
                    print(f"{n:30} {cls:6} {span:19} {b-a:7.0f} {o.mean()*100:6.1f} {r_in:10.1f} {r_out:11.1f}")
            print(f"  worst IN gap (hold must survive): {worst_in_gap:.1f}s ; "
                  f"worst TW/EMPTY run (hold must not exceed): {worst_neg_run:.1f}s ; "
                  f"margin: {worst_neg_run - worst_in_gap:+.1f}s")


if __name__ == "__main__":
    main()
