"""Exp 14: accumulate trajectory structure over long history, with
stabilization checkpoints."""
import sys, json, math, sqlite3
sys.path.insert(0, '/private/tmp/claude-500/-Users-rmk-Repo-home-assistant/5b47b34c-4417-452d-8f77-ce48ba08e904/scratchpad')
from traj2 import cells, smooth, CELL_S
from traj3 import dense_runs, split_march, Stats, table
from lead import GATES
from collections import Counter

CKPT_H = [0.5, 1, 2, 4, 8, 12, 24, 48, 96, 168, 336]


def stream(db, sensor, hours=None):
    c = sqlite3.connect('file:%s?mode=ro' % db, uri=True)
    t0, t1 = c.execute("select min(ts),max(ts) from frames where sensor_id=?",
                       (sensor,)).fetchone()
    t_to = t1 if hours is None else min(t1, t0 + hours * 3600)
    seq = []
    for ci, x in cells(db, sensor, None, t_to, warm_s=0.0):
        seq.append((ci, x))
    return seq, t0, t1


def accumulate(seq, ckpt_secs):
    """Walk the cell sequence once; snapshot Stats at each checkpoint."""
    sm = smooth(seq)
    runs = dense_runs(seq, sm)
    ci0 = seq[0][0]
    snaps = {}
    st = Stats()
    ri = 0
    for cs in ckpt_secs:
        lim = ci0 + cs / CELL_S
        while ri < len(runs) and runs[ri][-1][0] <= lim:
            if len(runs[ri]) >= 2:
                st.add_run(runs[ri])
            ri += 1
        snaps[cs] = snapshot(st)
    while ri < len(runs):
        if len(runs[ri]) >= 2:
            st.add_run(runs[ri])
        ri += 1
    return st, snaps


def snapshot(st):
    return dict(nmarch=st.nmarch,
                origin=[st.origin[g] for g in range(GATES)],
                terminus=[st.terminus[g] for g in range(GATES)],
                tin=[st.tin[g] for g in range(GATES)],
                tout=[st.tout[g] for g in range(GATES)],
                presence=[st.presence[g] for g in range(GATES)],
                inplace=[st.inplace[g] for g in range(GATES)],
                march=[st.marchdwell[g] for g in range(GATES)])


def infer(sn, min_marches=15):
    """Label-free structure inference from a snapshot."""
    o = sn['origin']; t = sn['terminus']; ip = sn['inplace']
    mdw = sn['march']; tot = sum(o) or 1
    if sum(o) < min_marches:
        return None
    # entry band: gates holding the top of the origin mass
    def band(h):
        s = sum(h) or 1
        order = sorted(range(GATES), key=lambda g: -h[g])
        acc = 0; sel = []
        for g in order:
            sel.append(g); acc += h[g]
            if acc >= 0.6 * s:
                break
        return sorted(sel)
    entry = band(o); dwell = band(t)
    extent = [g for g in range(GATES) if mdw[g] > 0]
    # in-place-only gates: dwell present, essentially never inside a march
    ipo = [g for g in range(GATES)
           if ip[g] * CELL_S >= 20 and mdw[g] <= 0.05 * (max(mdw) or 1)]
    return dict(entry=entry, dwell=dwell,
                extent=(min(extent), max(extent)) if extent else None,
                inplace_only=ipo)


def jsd(a, b):
    sa = sum(a) or 1; sb = sum(b) or 1
    p = [x / sa for x in a]; q = [x / sb for x in b]
    m = [(x + y) / 2 for x, y in zip(p, q)]
    def kl(u, v):
        return sum(x * math.log(x / y) for x, y in zip(u, v) if x > 0 and y > 0)
    return 0.5 * kl(p, m) + 0.5 * kl(q, m)


if __name__ == '__main__':
    DBS = [
        ('prod', '/private/tmp/claude-500/-Users-rmk-Repo-home-assistant/5b47b34c-4417-452d-8f77-ce48ba08e904/scratchpad/prod-frames.db', 'D0:6E:81:D2:5D:A6', 'bath'),
        ('prod', '/private/tmp/claude-500/-Users-rmk-Repo-home-assistant/5b47b34c-4417-452d-8f77-ce48ba08e904/scratchpad/prod-frames.db', 'FD:68:3B:41:6E:FF', 'living'),
        ('dev', '/Users/rmk/Repo/home-assistant/config/smart_ld2410/frames.db', 'D0:6E:81:D2:5D:A6', 'bath'),
        ('dev', '/Users/rmk/Repo/home-assistant/config/smart_ld2410/frames.db', 'FD:68:3B:41:6E:FF', 'living'),
    ]
    out = {}
    for tag, db, sen, room in DBS:
        key = '%s-%s' % (tag, room)
        seq, t0, t1 = stream(db, sen)
        span_h = (t1 - t0) / 3600
        ck = [h * 3600 for h in CKPT_H if h <= span_h] + [span_h * 3600]
        st, snaps = accumulate(seq, ck)
        out[key] = dict(span_h=span_h, sensor=sen,
                        snaps={('%.1f' % (k / 3600)): v for k, v in snaps.items()},
                        final=snapshot(st))
        print(table(st, '%s  span=%.1fh' % (key, span_h)), flush=True)
        print(' inferred:', infer(snapshot(st)), flush=True)
    json.dump(out, open('t14long.json', 'w'))
