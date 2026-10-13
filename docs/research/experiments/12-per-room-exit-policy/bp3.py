"""Bleed pressure v3: ORPHAN far-lead episodes (two-sided ownership).

Episodes cut at 60 s of fully quiet time.  An episode is far-lead if every
hot frame in it has suppressed lead >= 2 with g0/g1 not raw-hot (no near-band
frame anywhere inside it).  Such an episode is OWNED if a near-band frame
occurs within LOOK seconds before its start (someone walked in) or within
LOOK seconds after its end (someone walked out) -- a genuine occupant, even a
far-seated rear-sensor one, crosses the entry band on at least one side.
An ORPHAN episode has neither: far-band energy with nobody ever at the door.

bleed pressure P = orphan seconds per hour, and the count of orphan episodes
lasting >= MIN_LONG seconds per hour.  Purely label-free.

Usage: bp3.py <db> <sensor_prefix> <tag> [look_s]
"""
import sys, sqlite3, math, json
S = '/private/tmp/claude-500/-Users-rmk-Repo-home-assistant/5b47b34c-4417-452d-8f77-ce48ba08e904/scratchpad'
sys.path.insert(0, S)
sys.path.insert(0, '/Users/rmk/Repo/homeassistant-smart-ld2410')
from lead import Model, leading_suppressed, leading_raw, GATES, SUPPORT_TAU

GAP_S = 60.0
import os
MIN_LONG = float(os.environ.get('MIN_LONG','30'))


def main(db, pref, tag, look_s=300.0):
    c = sqlite3.connect('file:%s?mode=ro' % db, uri=True)
    cur = c.execute("select ts,move,still from frames where sensor_id like ? order by ts", (pref + '%',))
    m = Model(); sup = [0.0] * GATES; prev = None
    tot = hot_s = 0.0
    eps = []; ep = None
    nears = []          # timestamps of near-band frames (subsampled: >=1s apart)

    def close():
        nonlocal ep
        if ep is not None:
            eps.append(ep); ep = None

    while True:
        chunk = cur.fetchmany(20000)
        if not chunk:
            break
        for ts, mvb, stb in chunk:
            mv = list(mvb); st = list(stb)
            dt = 0.0 if prev is None else min(max(ts - prev, 0.0), 2.0)
            if m.ready:
                rm, rs = m.res(mv, st)
                peaks = [max(0.0, rm[g], rs[g]) for g in range(GATES)]
                a = 1.0 if prev is None else (1.0 - math.exp(-min(ts - prev, 2.0) / SUPPORT_TAU) if ts > prev else 0.0)
                for g in range(GATES):
                    sup[g] += a * (peaks[g] - sup[g])
                ls, _ = leading_suppressed(rm, sup)
                lr = leading_raw(rm)
                tot += dt
                if ls is None:
                    if ep is not None and ts - ep['end'] >= GAP_S:
                        close()
                else:
                    hot_s += dt
                    if ep is None or ts - ep['end'] >= GAP_S:
                        close()
                        ep = dict(start=ts, end=ts, hot=0.0, near=0, far=0.0, gates=[0] * GATES)
                    ep['hot'] += dt; ep['end'] = ts
                    if ls <= 1:
                        ep['near'] += 1
                        if not nears or ts - nears[-1] >= 1.0:
                            nears.append(ts)
                    elif lr is not None and lr >= 2:
                        ep['far'] += dt; ep['gates'][ls] += 1
            prev = ts
            m.add(ts, mv, st)
    close()

    import bisect
    def near_within(t0, t1, look):
        i = bisect.bisect_left(nears, t0 - look)
        return i < len(nears) and nears[i] <= t1 + look

    near_s = sum(e['hot'] for e in eps if e['near'] > 0)
    farep = [e for e in eps if e['near'] == 0 and e['far'] > 0]
    orph = [e for e in farep if not near_within(e['start'], e['end'], look_s)]
    olong = [e for e in orph if e['hot'] >= MIN_LONG]
    hours = tot / 3600.0
    out = dict(tag=tag, db=db, sensor=pref, look_s=look_s, hours=round(hours, 2),
               hot_s_per_hour=round(hot_s / max(hours, 1e-9), 1),
               n_ep=len(eps), n_far=len(farep), n_orphan=len(orph), n_orphan_long=len(olong),
               orphan_s_per_hour=round(sum(e['hot'] for e in orph) / max(hours, 1e-9), 2),
               orphan_long_s_per_hour=round(sum(e['hot'] for e in olong) / max(hours, 1e-9), 2),
               orphan_long_ep_per_hour=round(len(olong) / max(hours, 1e-9), 4),
               orphan_share_of_hot=round(100 * sum(e['hot'] for e in orph) / max(hot_s, 1e-9), 2),
               near_ep_s_per_hour=round(near_s / max(hours, 1e-9), 2),
               P=round(sum(e['hot'] for e in olong) / max(near_s, 1e-9), 4),
               P_all=round(sum(e['hot'] for e in orph) / max(near_s, 1e-9), 4),
               far_ep_orphan_pct=round(100 * len(orph) / max(len(farep), 1), 1),
               top=[[round(e['start'], 0), round(e['hot'], 1), max(range(GATES), key=lambda g: e['gates'][g])]
                    for e in sorted(olong, key=lambda e: -e['hot'])[:10]])
    print(json.dumps(out))


main(sys.argv[1], sys.argv[2], sys.argv[3], float(sys.argv[4]) if len(sys.argv) > 4 else 300.0)
