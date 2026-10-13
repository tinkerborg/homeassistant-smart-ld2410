"""Distribution and single-threshold separation tables for the gate-profile stats."""

from __future__ import annotations


import numpy as np

import data
import stats

CLASSES = ("IN", "TW", "EMPTY", "PET")
WINDOWS = (0.0, 2.0, 5.0)
PCTS = (5, 25, 50, 75, 95)


def templates(floors, use_floor):
    fx = data.load("labeled-sessions-0909-d06e")
    floor = floors["d06e"] if use_floor else {"move": None, "still": None}
    out = {}
    for channel in ("move", "still"):
        gates = stats.STILL_GATES if channel == "still" else stats.MOVE_GATES
        v = getattr(fx, channel)
        r = stats.residual(v, floor[channel], gates)
        out[channel] = {}
        for cls in ("IN", "TW"):
            m = fx.class_mask(cls)
            mean = r[m].mean(axis=0)
            out[channel][cls] = mean / np.linalg.norm(mean)
    return out


def pooled(fixtures, floors, sensor, channel, window, use_floor, tmpl, skip_template_fixture):
    cols: dict[str, dict[str, list[np.ndarray]]] = {c: {} for c in CLASSES}
    for fx in fixtures.values():
        if fx.sensor != sensor:
            continue
        floor = floors[sensor][channel] if use_floor else None
        st = stats.compute(getattr(fx, channel), fx.ts, floor, channel, window,
                           tmpl[channel] if tmpl and channel in tmpl else None)
        for cls in CLASSES:
            m = fx.class_mask(cls)
            if not m.sum():
                continue
            for k, v in st.items():
                if k.startswith("cos") and skip_template_fixture and fx.name.startswith("labeled-sessions"):
                    continue
                cols[cls].setdefault(k, []).append(v[m])
    return {c: {k: np.concatenate(v) for k, v in d.items()} for c, d in cols.items()}


def rates(x_in, x_other, thr, high):
    a = np.nan_to_num(x_in, nan=-np.inf if high else np.inf)
    b = np.nan_to_num(x_other, nan=-np.inf if high else np.inf)
    if high:
        return (a >= thr).mean(), (b >= thr).mean()
    return (a <= thr).mean(), (b <= thr).mean()


def best_threshold(x_in, x_neg):
    finite = np.concatenate([x_in, x_neg])
    finite = finite[np.isfinite(finite)]
    if len(finite) == 0:
        return None
    cand = np.unique(np.percentile(finite, np.linspace(0, 100, 201)))
    best = None
    for high in (True, False):
        for t in cand:
            tpr, fpr = rates(x_in, x_neg, t, high)
            j = tpr - fpr
            if best is None or j > best[0]:
                best = (j, t, high, tpr, fpr)
    return best


def main() -> None:
    fixtures = data.all_fixtures()
    floors = data.sensor_floors(fixtures)
    for use_floor in (True, False):
        tmpl = templates(floors, use_floor)
        for sensor in ("d06e", "fd68"):
            for channel in ("still", "move"):
                for window in WINDOWS:
                    tag = f"[{sensor} {channel} win={window:.0f}s floor={'yes' if use_floor else 'no'}]"
                    p = pooled(fixtures, floors, sensor, channel, window, use_floor, tmpl, True)
                    if not p["IN"]:
                        continue
                    print(f"\n===== {tag}")
                    keys = [k for k in stats.STAT_NAMES if k in p["IN"]]
                    hdr = f"{'stat':12} {'class':6} {'n':>7} " + " ".join(f"p{q:<7d}" for q in PCTS)
                    print(hdr)
                    for k in keys:
                        for cls in CLASSES:
                            if k not in p[cls]:
                                continue
                            v = p[cls][k]
                            f = v[np.isfinite(v)]
                            if len(f) == 0:
                                continue
                            q = np.percentile(f, PCTS)
                            print(f"{k:12} {cls:6} {len(v):7d} " + " ".join(f"{x:8.3f}" for x in q))
                    print(f"\n{'stat':12} {'dir':>5} {'thr':>9} {'TPR_IN':>7} {'FPR_TW':>7} {'FPR_EMP':>7} {'FPR_PET':>7}  J")
                    for k in keys:
                        neg = np.concatenate([p[c][k] for c in ("TW", "EMPTY") if k in p[c]])
                        b = best_threshold(p["IN"][k], neg)
                        if b is None:
                            continue
                        _, thr, high, tpr, _ = b
                        ftw = rates(p["IN"][k], p["TW"][k], thr, high)[1] if k in p["TW"] else float("nan")
                        fem = rates(p["IN"][k], p["EMPTY"][k], thr, high)[1] if k in p["EMPTY"] else float("nan")
                        fpe = rates(p["IN"][k], p["PET"][k], thr, high)[1] if k in p["PET"] else float("nan")
                        d = ">=" if high else "<="
                        print(f"{k:12} {d:>5} {thr:9.3f} {tpr:7.3f} {ftw:7.3f} {fem:7.3f} {fpe:7.3f}  {tpr-max(ftw if ftw==ftw else 0, fem if fem==fem else 0):.3f}")


if __name__ == "__main__":
    main()
