"""Exp 14 v3: marches require CONTINUITY, not just displacement.

Diagnostic from v2 showed: a genuine walk-in is a dense, gap-free, monotone
centroid ramp (living room 21:39:55: 5.7 -> 3.3 over 6 s, every cell filled).
Seated typing and through-wall kitchen activity are ~50% empty cells with the
centroid alternating between two bands. So the discriminator is
density+monotonicity, and v2's marches were mostly alternation artefacts.
"""
import sys
from collections import Counter
sys.path.insert(0, '/private/tmp/claude-500/-Users-rmk-Repo-home-assistant/5b47b34c-4417-452d-8f77-ce48ba08e904/scratchpad')
from traj2 import cells, smooth, CELL_S
from lead import GATES

MAX_GAP = 1          # cells: a run tolerates a single missing 0.5 s cell
RUN_MIN_CELLS = 4    # 2.0 s
MARCH_MIN_NET = 1.5  # gates
MONO = 0.65          # |net| / total-variation
MARCH_MAX_SPEED = 3.0
MARCH_MIN_SPEED = 0.12


def dense_runs(seq, sm, max_gap=MAX_GAP):
    """Maximal runs of cells with no gap longer than max_gap. -> [[(ci,x)..]]"""
    out = []; cur = []; gap = 0
    for (ci, _), x in zip(seq, sm):
        if x is None:
            gap += 1
            if cur and gap > max_gap:
                out.append(cur); cur = []
            continue
        if cur and gap:
            # linear-interpolate the single missing cell
            c0, x0 = cur[-1]
            for k in range(1, gap + 1):
                cur.append((c0 + k, x0 + (x - x0) * k / (gap + 1)))
        gap = 0
        cur.append((ci, x))
    if cur:
        out.append(cur)
    return out


def run_features(run):
    xs = [x for _, x in run]
    net = xs[-1] - xs[0]
    tv = sum(abs(b - a) for a, b in zip(xs, xs[1:]))
    dur = (run[-1][0] - run[0][0]) * CELL_S
    mono = abs(net) / tv if tv > 0 else 0.0
    sp = abs(net) / dur if dur > 0 else 0.0
    return dict(n=len(run), dur=dur, net=net, tv=tv, mono=mono, speed=sp,
                x0=xs[0], x1=xs[-1], lo=min(xs), hi=max(xs))


def is_march(f):
    return (f['n'] >= RUN_MIN_CELLS and abs(f['net']) >= MARCH_MIN_NET
            and f['mono'] >= MONO
            and MARCH_MIN_SPEED <= f['speed'] <= MARCH_MAX_SPEED)


def split_march(run):
    """Extract ALL non-overlapping marches in a dense run, left to right,
    each one maximal (longest displacement from its start). Remainder cells
    are in-place."""
    n = len(run)
    ms = []; used = [False] * n
    i = 0
    while i < n:
        bestj = None; bestf = None; bests = 0.0
        for j in range(i + RUN_MIN_CELLS - 1, n):
            f = run_features(run[i:j + 1])
            if is_march(f):
                s = abs(f['net']) * f['mono']
                if s > bests:
                    bests = s; bestj = j; bestf = f
            if j - i > 120:   # 60 s cap on a single march
                break
        if bestj is None:
            i += 1
            continue
        ms.append((run[i:bestj + 1], bestf))
        for k in range(i, bestj + 1):
            used[k] = True
        i = bestj + 1
    rest = [run[k] for k in range(n) if not used[k]]
    return ms, rest


class Stats:
    def __init__(self):
        self.origin = Counter(); self.terminus = Counter()
        self.tin = Counter(); self.tout = Counter()
        self.inplace = Counter(); self.marchdwell = Counter()
        self.presence = Counter()
        self.nmarch = 0; self.nrun = 0; self.cells_seen = 0
        self.march_list = []

    def add_run(self, run):
        self.nrun += 1
        self.cells_seen += len(run)
        for _, x in run:
            self.presence[int(round(x))] += 1
        ms, rest = split_march(run)
        for cellsm, f in ms:
            self.nmarch += 1
            g0 = int(round(f['x0'])); g1 = int(round(f['x1']))
            self.origin[g0] += 1; self.terminus[g1] += 1
            self.march_list.append((cellsm[0][0] * CELL_S, f))
            lo, hi = min(g0, g1), max(g0, g1)
            for g in range(lo, hi + 1):
                self.marchdwell[g] += 1
            if g1 < g0:
                for g in range(g1, g0):
                    self.tin[g] += 1
            else:
                for g in range(g0 + 1, g1 + 1):
                    self.tout[g] += 1
        for _, x in rest:
            self.inplace[int(round(x))] += 1


def run(db, sensor, t_from=None, t_to=None, **kw):
    seq = [(ci, x) for ci, x in cells(db, sensor, t_from, t_to, **kw)]
    sm = smooth(seq)
    runs = dense_runs(seq, sm)
    st = Stats()
    for r in runs:
        if len(r) >= 2:
            st.add_run(r)
    return st, seq, sm, runs


def table(st, title):
    L = ['', '== %s  dense_runs=%d marches=%d active=%.0fs' % (
        title, st.nrun, st.nmarch, st.cells_seen * CELL_S),
        'gate  origin  termin  tr_in  tr_out   pres_s  inplace_s  march_s']
    for g in range(GATES):
        L.append('  %d   %6d  %6d  %5d  %6d %8.1f %10.1f %8.1f' % (
            g, st.origin[g], st.terminus[g], st.tin[g], st.tout[g],
            st.presence[g] * CELL_S, st.inplace[g] * CELL_S,
            st.marchdwell[g] * CELL_S))
    return '\n'.join(L)
