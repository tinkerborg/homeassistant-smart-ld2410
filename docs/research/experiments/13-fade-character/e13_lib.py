"""Experiment 13: fade-character discrimination. Shared loader + features."""
import sqlite3, math, datetime, zoneinfo
import numpy as np

TZ = zoneinfo.ZoneInfo("America/New_York")
BASE = "/Users/rmk/Repo/homeassistant-smart-ld2410/tests/fixtures/recordings/"

def load(db):
    c = sqlite3.connect(f"file:{db}?mode=ro&immutable=1", uri=True)
    rows = c.execute("select ts,move,still,distance_cm,device_occ from frames order by ts").fetchall()
    ts = np.array([r[0] for r in rows])
    mv = np.array([list(r[1]) for r in rows], dtype=float)
    st = np.array([list(r[2]) for r in rows], dtype=float)
    dist = np.array([r[3] for r in rows], dtype=float)
    occ = np.array([r[4] for r in rows], dtype=float)
    return dict(ts=ts, move=mv, still=st, dist=dist, occ=occ)

def lt(ts):
    return datetime.datetime.fromtimestamp(ts, TZ)

def span(day, a, b):
    """local HH:MM:SS -> (t0,t1) unix, day='2026-09-11'"""
    y, m, d = map(int, day.split("-"))
    def f(s):
        h, mi, se = map(int, s.split(":"))
        return datetime.datetime(y, m, d, h, mi, se, tzinfo=TZ).timestamp()
    return (f(a), f(b))

# ---------------- ground truth spans ----------------
# (fixture, class, t0, t1, note)
def spans():
    S = []
    D11 = "2026-09-11"
    D09 = "2026-09-09"
    # throughwall morning: bathroom EMPTY, kitchen person beyond wall
    for a, b in [("05:00:00", "05:46:00")]:
        S.append(("tw", "TW", *span(D11, a, b), "kitchen-beyond-wall"))
    # bathroom genuine visit (in-room), trim 3s off each end
    S.append(("bath", "IN", *span(D11, "22:04:04", "22:06:40"), "toilet-visit"))
    # living room seated (in-room), different sensor
    S.append(("lr", "IN", *span(D11, "21:04:30", "21:19:30"), "seated-1"))
    S.append(("lr", "IN", *span(D11, "21:40:10", "21:54:30"), "seated-2"))
    # labeled sessions
    S.append(("lab", "IN", *span(D09, "21:24:28", "21:25:14"), "toilet-a"))
    S.append(("lab", "IN", *span(D09, "23:15:32", "23:22:32"), "toilet-b"))
    for a, b, n in [("21:22:23", "21:22:42", "stove"), ("21:22:52", "21:22:59", "island"),
                    ("21:23:26", "21:23:37", "stove"), ("21:23:48", "21:23:53", "island"),
                    ("23:10:57", "23:12:32", "stove"), ("23:12:44", "23:13:41", "island")]:
        S.append(("lab", "TW", *span(D09, a, b), n))
    # labeled 'empty' control
    S.append(("lab", "EMPTY", *span(D09, "23:27:10", "23:33:40"), "empty"))
    return S

FIX = {
    "tw": BASE + "throughwall-morning-d06e.db",
    "bath": BASE + "bathroom-visit-2204-d06e.db",
    "lr": BASE + "livingroom-reset-seated-fd68.db",
    "lab": BASE + "labeled-sessions-0909-d06e.db",
}

# ---------------- features ----------------
def feats(x):
    """x: 1-D window of energies (float). Returns dict of fade features."""
    n = len(x)
    med = np.median(x)
    mu = x.mean()
    sd = x.std()
    out = {}
    out["mean"] = mu
    out["med"] = med
    out["cv"] = sd / mu if mu > 0 else 0.0
    # deep fade rate: fraction below q% of window median
    for q in (30, 50, 70):
        out[f"df{q}"] = float(np.mean(x < med * q / 100.0)) if med > 0 else 0.0
    # normalised envelope moments
    if sd > 1e-9:
        z = (x - mu) / sd
        out["skew"] = float(np.mean(z ** 3))
        out["kurt"] = float(np.mean(z ** 4)) - 3.0
    else:
        out["skew"] = 0.0
        out["kurt"] = 0.0
    # histogram entropy over integer amplitude values present
    vals, cnt = np.unique(x, return_counts=True)
    p = cnt / n
    out["ent"] = float(-(p * np.log2(p)).sum())
    out["entn"] = out["ent"] / math.log2(n) if n > 1 else 0.0
    # fade durations below 70% of median (run lengths)
    if med > 0:
        below = x < med * 0.7
        runs, cur = [], 0
        for b in below:
            if b:
                cur += 1
            elif cur:
                runs.append(cur); cur = 0
        if cur: runs.append(cur)
        out["fdur_mean"] = float(np.mean(runs)) if runs else 0.0
        out["fdur_max"] = float(max(runs)) if runs else 0.0
        out["fdur_n"] = len(runs) / (n / 10.0)  # fades per second
    else:
        out["fdur_mean"] = out["fdur_max"] = out["fdur_n"] = 0.0
    # peak-to-median ratio, dynamic range in dB
    out["ptm"] = float(x.max() / med) if med > 0 else 0.0
    out["mtm"] = float(x.min() / med) if med > 0 else 0.0
    out["dr_db"] = 20 * math.log10((x.max() + 1) / (x.min() + 1))
    # Rician K estimate via method of moments on amplitude
    m2 = float(np.mean(x ** 2)); m4 = float(np.mean(x ** 4))
    r = 2 * m2 ** 2 - m4
    if r > 0:
        s = math.sqrt(r)
        k = s / (m2 - s) if (m2 - s) > 1e-9 else 99.0
        out["K"] = min(k, 99.0)
    else:
        out["K"] = 0.0
    # lag-1 autocorrelation (smoothing diagnostic)
    if sd > 1e-9 and n > 2:
        out["ac1"] = float(np.corrcoef(x[:-1], x[1:])[0, 1])
    else:
        out["ac1"] = 0.0
    # mean |first difference| normalised by median
    out["mad1"] = float(np.mean(np.abs(np.diff(x))) / med) if med > 0 else 0.0
    return out

FEATNAMES = ["cv", "df30", "df50", "df70", "skew", "kurt", "ent", "entn",
             "fdur_mean", "fdur_max", "fdur_n", "ptm", "mtm", "dr_db", "K",
             "ac1", "mad1"]

def auc(a, b):
    """AUC of separating a (pos) from b (neg) by value."""
    a = np.asarray(a); b = np.asarray(b)
    if len(a) == 0 or len(b) == 0: return float("nan")
    allv = np.concatenate([a, b])
    r = allv.argsort().argsort().astype(float) + 1
    # tie handling
    order = np.argsort(allv)
    sv = allv[order]
    i = 0
    while i < len(sv):
        j = i
        while j + 1 < len(sv) and sv[j + 1] == sv[i]:
            j += 1
        if j > i:
            r[order[i:j + 1]] = (i + j) / 2.0 + 1
        i = j + 1
    na, nb = len(a), len(b)
    return (r[:na].sum() - na * (na + 1) / 2) / (na * nb)

def cohend(a, b):
    a = np.asarray(a); b = np.asarray(b)
    if len(a) < 2 or len(b) < 2: return float("nan")
    s = math.sqrt(((len(a) - 1) * a.var(ddof=1) + (len(b) - 1) * b.var(ddof=1)) / (len(a) + len(b) - 2))
    return (a.mean() - b.mean()) / s if s > 0 else 0.0
