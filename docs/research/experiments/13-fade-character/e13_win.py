"""Build windowed feature table."""
import numpy as np, pickle, sys
from e13_lib import *

WIN_S = 2.0
STEP_S = 0.5
MIN_MED = 8.0   # active gate: window median energy floor

def build(win_s=WIN_S, step_s=STEP_S, min_med=MIN_MED):
    rows = []
    data = {k: load(v) for k, v in FIX.items()}
    for fx, cls, t0, t1, note in spans():
        d = data[fx]
        ts = d["ts"]
        i0, i1 = np.searchsorted(ts, t0), np.searchsorted(ts, t1)
        if i1 - i0 < 20: continue
        # nominal 10 Hz
        nw = int(win_s * 10); ns = int(step_s * 10)
        for ch in ("move", "still"):
            A = d[ch]
            for g in range(9):
                x_all = A[i0:i1, g]
                t_all = ts[i0:i1]
                for s in range(0, len(x_all) - nw + 1, ns):
                    x = x_all[s:s + nw]
                    # reject windows spanning a frame gap > 0.5s
                    tt = t_all[s:s + nw]
                    if tt[-1] - tt[0] > win_s * 1.6: continue
                    if np.median(x) < min_med: continue
                    f = feats(x)
                    f.update(fx=fx, cls=cls, note=note, ch=ch, gate=g, t=tt[0])
                    rows.append(f)
    return rows

if __name__ == "__main__":
    rows = build()
    pickle.dump(rows, open("e13_rows.pkl", "wb"))
    import collections
    c = collections.Counter((r["fx"], r["cls"], r["ch"]) for r in rows)
    for k in sorted(c): print(k, c[k])
    print("total", len(rows))
