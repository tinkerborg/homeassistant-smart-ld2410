"""Exp 14 v2: continuous-centroid trajectories + zigzag march segmentation.

Fixes v2 over v1: argmax teleports (gate 3<->7 flips in 0.5 s) were being
counted as marches. Now the per-frame position is the residual-weighted
centroid of the suppression-surviving hot gates (continuous, sub-gate), and a
march must satisfy a physical speed bound.
"""
import sqlite3, math, sys
from collections import Counter

sys.path.insert(0, '/private/tmp/claude-500/-Users-rmk-Repo-home-assistant/5b47b34c-4417-452d-8f77-ce48ba08e904/scratchpad')
from lead import Model, GATES, K, SUPPORT_TAU, leading_suppressed

CELL_S = 0.5
MEDIAN_W = 3
TRACK_GAP_CELLS = 3
ZIGZAG = 0.9          # gates: swing amplitude that defines a turning point
MARCH_MIN_NET = 1.8   # gates
MARCH_MIN_S = 1.0
MARCH_MAX_SPEED = 3.0  # gates/s  (~2.2 m/s)
MARCH_MIN_SPEED = 0.15
CELL_MIN_FRAC = 0.5


def frame_pos(rm, sup):
    """(centroid, argmax) over suppression-surviving hot gates, or None."""
    _, runs = leading_suppressed(rm, sup)
    num = den = 0.0; best = None; bestv = 0.0
    for run in runs:
        for g in run:
            w = rm[g]
            num += g * w; den += w
            if w > bestv:
                bestv = w; best = g
    if den <= 0:
        return None, None
    return num / den, best


def cells(db, sensor, t_from=None, t_to=None, warm_s=6 * 3600.0):
    c = sqlite3.connect('file:%s?mode=ro' % db, uri=True)
    sql = "select ts,move,still from frames where sensor_id=?"
    args = [sensor]
    if t_from is not None:
        sql += " and ts>=?"; args.append(t_from - warm_s)
    if t_to is not None:
        sql += " and ts<?"; args.append(t_to)
    sql += " order by ts"
    m = Model(); sup = [0.0] * GATES; prev = None
    cur_i = None; buf = []; nf = 0
    for ts, mvb, stb in c.execute(sql, args):
        mv = list(mvb); st = list(stb)
        if m.ready:
            rm, rs = m.res(mv, st)
            peaks = [max(0.0, rm[g], rs[g]) for g in range(GATES)]
            a = 1.0 if prev is None else (
                1.0 - math.exp(-min(ts - prev, 2.0) / SUPPORT_TAU) if ts > prev else 0.0)
            for g in range(GATES):
                sup[g] += a * (peaks[g] - sup[g])
            if t_from is None or ts >= t_from:
                p, _am = frame_pos(rm, sup)
                ci = int(ts // CELL_S)
                if cur_i is None:
                    cur_i = ci
                elif ci != cur_i:
                    yield cur_i, _med(buf, nf)
                    for k in range(cur_i + 1, ci):
                        yield k, None
                    cur_i = ci; buf = []; nf = 0
                nf += 1
                if p is not None:
                    buf.append(p)
        prev = ts
        m.add(ts, mv, st)
    if cur_i is not None:
        yield cur_i, _med(buf, nf)


def _med(buf, nf):
    if not buf or nf == 0 or len(buf) < CELL_MIN_FRAC * nf:
        return None
    b = sorted(buf)
    return b[len(b) // 2]


def smooth(seq):
    v = [x[1] for x in seq]
    n = len(v); out = [None] * n; h = MEDIAN_W // 2
    for i in range(n):
        if v[i] is None:
            continue
        w = sorted(x for x in v[max(0, i - h):i + h + 1] if x is not None)
        out[i] = w[len(w) // 2]
    return out


def tracks(seq, sm):
    out = []; cur = []; gap = 0
    for (ci, _), x in zip(seq, sm):
        if x is None:
            gap += 1
            if cur and gap > TRACK_GAP_CELLS:
                out.append(cur); cur = []
            continue
        gap = 0
        cur.append((ci, x))
    if cur:
        out.append(cur)
    return out


def zigzag(track, thr=ZIGZAG):
    """Turning points with minimum swing `thr` gates."""
    pts = [track[0]]
    d = 0  # current direction
    ext = track[0]
    for ci, x in track[1:]:
        if d == 0:
            if x > ext[1] + thr:
                d = 1; pts.append((ci, x)); ext = (ci, x)
            elif x < ext[1] - thr:
                d = -1; pts.append((ci, x)); ext = (ci, x)
            elif (x > pts[-1][1]) != (ext[1] > pts[-1][1]):
                ext = (ci, x) if abs(x - pts[-1][1]) > abs(ext[1] - pts[-1][1]) else ext
            else:
                ext = (ci, x)
        elif d > 0:
            if x >= ext[1]:
                ext = (ci, x)
            elif x < ext[1] - thr:
                pts.append(ext); d = -1; ext = (ci, x)
        else:
            if x <= ext[1]:
                ext = (ci, x)
            elif x > ext[1] + thr:
                pts.append(ext); d = 1; ext = (ci, x)
    if ext[0] != pts[-1][0]:
        pts.append(ext)
    return pts


def march_legs(track):
    """Returns (marches, inplace_cells). march = (s_ci,e_ci,p0,p1)."""
    if len(track) < 2:
        return [], track
    pts = zigzag(track)
    ms = []
    for (c0, p0), (c1, p1) in zip(pts, pts[1:]):
        net = p1 - p0
        dur = (c1 - c0) * CELL_S
        if dur <= 0:
            continue
        sp = abs(net) / dur
        if abs(net) >= MARCH_MIN_NET and dur >= MARCH_MIN_S and \
                MARCH_MIN_SPEED <= sp <= MARCH_MAX_SPEED:
            ms.append((c0, c1, p0, p1))
    covered = set()
    for s, e, _, _ in ms:
        covered.update(range(s, e + 1))
    inplace = [(ci, x) for ci, x in track if ci not in covered]
    return ms, inplace


class Stats:
    def __init__(self):
        self.origin = Counter(); self.terminus = Counter()
        self.tin = Counter(); self.tout = Counter()
        self.inplace = Counter(); self.marchdwell = Counter()
        self.nmarch = 0; self.ntrack = 0; self.cells_seen = 0
        self.march_list = []

    def add_track(self, track):
        self.ntrack += 1
        ms, ip = march_legs(track)
        self.nmarch += len(ms)
        for s, e, p0, p1 in ms:
            g0 = int(round(p0)); g1 = int(round(p1))
            self.origin[g0] += 1; self.terminus[g1] += 1
            self.march_list.append((s * CELL_S, e * CELL_S, p0, p1))
            lo, hi = min(g0, g1), max(g0, g1)
            for g in range(lo, hi + 1):
                self.marchdwell[g] += 1
            if g1 < g0:
                for g in range(g1, g0):
                    self.tin[g] += 1
            else:
                for g in range(g0 + 1, g1 + 1):
                    self.tout[g] += 1
        for ci, x in ip:
            self.inplace[int(round(x))] += 1
        self.cells_seen += len(track)


def run(db, sensor, t_from=None, t_to=None, **kw):
    seq = [(ci, x) for ci, x in cells(db, sensor, t_from, t_to, **kw)]
    sm = smooth(seq)
    st = Stats()
    trs = tracks(seq, sm)
    for tr in trs:
        st.add_track(tr)
    return st, seq, sm, trs


def table(st, title):
    tot_ip = sum(st.inplace.values()) or 1
    L = ['', '== %s   tracks=%d marches=%d active=%.0fs' % (
        title, st.ntrack, st.nmarch, st.cells_seen * CELL_S),
        'gate  origin  termin  tr_in  tr_out  inplace_s  march_s  ip_only']
    for g in range(GATES):
        ip = st.inplace[g] * CELL_S; md = st.marchdwell[g] * CELL_S
        flag = 'YES' if ip >= 5.0 and (st.tin[g] + st.tout[g]) <= max(1, 0.05 * (
            sum(st.tin.values()) + sum(st.tout.values()))) else ''
        L.append('  %d   %6d  %6d  %5d  %6d   %8.1f %8.1f   %s' % (
            g, st.origin[g], st.terminus[g], st.tin[g], st.tout[g], ip, md, flag))
    return '\n'.join(L)
