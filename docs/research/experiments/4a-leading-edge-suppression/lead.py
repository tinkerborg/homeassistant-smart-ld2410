"""Leading-edge gate with isolated-gate suppression, replicated from the shipped
detector (algo/detector.py _score + _track_candidate, algo/baseline.py residuals).

Faithful pieces:
  * residual = (energy - floor) / spread        (baseline.residuals)
  * floor    = 25th pct of 60s-bucket q50s over the window
  * spread   = max(25th pct of bucket (q90-q50), min_mad=1.0)
  * support  = EMA(tau=support_tau_s=1.0s) of peaks = max(0, res_move, res_still)
  * isolated-gate rule: a run of exactly one hot gate survives only if a
    neighbour's SUPPORT >= k/2 (detector._score)
Shortcut: no classifier exclusion mask (no persisted gate classes available), so
`excluded()` is always False - i.e. the unmasked/holding pass. That only makes
suppression *weaker*, so any gate it still rejects would also be rejected with
the mask on.
"""
import sqlite3, datetime, zoneinfo, math, bisect
from collections import deque
TZ = zoneinfo.ZoneInfo('America/New_York')
GATES = 9
K = 4.5
MIN_MAD = 1.0
SUPPORT_TAU = 1.0
BUCKET_S = 60.0
MIN_BUCKETS = 5
WINDOW_S = 12*3600.0

def q(o, p):
    n = len(o)-1
    if n <= 0: return float(o[0])
    x = p*n; lo = int(x); hi = min(lo+1, n)
    return float(o[lo] + (o[hi]-o[lo])*(x-lo))

class Chan:
    def __init__(self):
        self.q50 = deque(maxlen=int(WINDOW_S/BUCKET_S))
        self.spr = deque(maxlen=int(WINDOW_S/BUCKET_S))
        self.open_i = None; self.buf = []
        self.cache = None
    def add(self, ts, v):
        i = int(ts//BUCKET_S)
        if self.open_i is None: self.open_i = i
        elif i != self.open_i:
            if self.buf:
                o = sorted(self.buf)
                self.q50.append(q(o, 0.5)); self.spr.append(max(0.0, q(o, 0.90)-q(o, 0.5)))
                self.cache = None
            self.open_i = i; self.buf = []
        self.buf.append(v)
    @property
    def ready(self): return len(self.q50) >= MIN_BUCKETS
    def fs(self):
        if self.cache is None:
            if self.ready:
                self.cache = (q(sorted(self.q50), 0.25), max(q(sorted(self.spr), 0.25), MIN_MAD))
            else:
                self.cache = (0.0, MIN_MAD)
        return self.cache

class Model:
    def __init__(self):
        self.mv = [Chan() for _ in range(GATES)]
        self.st = [Chan() for _ in range(GATES)]
    def add(self, ts, mv, st):
        for g in range(GATES):
            self.mv[g].add(ts, mv[g]); self.st[g].add(ts, st[g])
    @property
    def ready(self): return all(c.ready for c in self.mv)
    def res(self, mv, st):
        rm = []; rs = []
        for g in range(GATES):
            f, s = self.mv[g].fs(); rm.append((mv[g]-f)/s)
            f, s = self.st[g].fs(); rs.append((st[g]-f)/s)
        return rm, rs

def leading_suppressed(rm, sup):
    """First gate of the lowest surviving run of move-residual-hot gates."""
    runs = []; run = []
    for g in range(GATES+1):
        hot = g < GATES and rm[g] >= K
        if hot: run.append(g); continue
        if not run: continue
        if len(run) == 1:
            o = run[0]
            left = sup[o-1] if o > 0 else 0.0
            right = sup[o+1] if o+1 < GATES else 0.0
            if left < K/2 and right < K/2:
                run = []; continue
        runs.append(tuple(run)); run = []
    return (runs[0][0] if runs else None), runs

def leading_raw(rm):
    for g in range(GATES):
        if rm[g] >= K: return g
    return None

def scan(db, sensor_like, t_from, t_to, warm_s=6*3600.0, label=''):
    c = sqlite3.connect('file:%s?mode=ro' % db, uri=True)
    rows = c.execute("select ts,move,still from frames where sensor_id like ? and ts>=? and ts<? order by ts",
                     (sensor_like, t_from-warm_s, t_to)).fetchall()
    m = Model(); sup = [0.0]*GATES; prev = None
    out = []
    for ts, mvb, stb in rows:
        mv = list(mvb); st = list(stb)
        if m.ready:
            rm, rs = m.res(mv, st)
            peaks = [max(0.0, rm[g], rs[g]) for g in range(GATES)]
            a = 1.0 if prev is None else (1.0-math.exp(-min(ts-prev, 2.0)/SUPPORT_TAU) if ts > prev else 0.0)
            for g in range(GATES): sup[g] += a*(peaks[g]-sup[g])
            if ts >= t_from:
                ls, runs = leading_suppressed(rm, sup)
                out.append((ts, leading_raw(rm), ls, tuple(rm), tuple(peaks), tuple(sup), runs))
        prev = ts
        m.add(ts, mv, st)
    return out
