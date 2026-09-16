"""Per-room exit policy: ARMING (4e D') where bleed pressure is high,
RETENTION-ONLY (4d form c) where it is not.  Applies both policies to every
fixture stream so the matched and the mismatched assignment can be compared.
"""
import sys, collections, copy
S = '/private/tmp/claude-500/-Users-rmk-Repo-home-assistant/5b47b34c-4417-452d-8f77-ce48ba08e904/scratchpad'
sys.path.insert(0, S)
sys.path.insert(0, S + '/pinned')
import custom_components.smart_ld2410.algo.detector as _det   # pin to HEAD: the
import custom_components.smart_ld2410.algo.types as _ty       # worktree is being
assert _det.__file__.startswith(S), _det.__file__             # edited concurrently
exec(open(S + '/e4_dep.py').read().split("print('%-26s")[0])   # SRet, CD, STREAM, go, wdet, wret, T, hm, ...

# ---- form c (retention-only) runner over the same STREAM dict -------------
CRET = {}
def cret(sname):
    if sname not in CRET:
        warm = STREAM[sname][0]
        r = Retention(warm[0][2])
        for ts, mv, st in warm:
            r.add(ts, st)
        CRET[sname] = r
    return copy.deepcopy(CRET[sname])

CDET = {}
def cdet(sname, kw):
    warm = STREAM[sname][0]
    d = Composite(DetectorConfig(hold_s=30.), **kw)
    r = Retention(warm[0][2]); t0 = warm[0][0]
    for ts, mv, st in warm:
        r.add(ts, st); d.ret = r.score
        d.process(Frame(ts, ts - t0, tuple(mv), tuple(st), 0, False))
    return d, r, t0

def goc(sname, *, hold_s=30., seed=False, **kw):
    """form-c (retention-only) release."""
    key = (sname, tuple(sorted(kw.items())))
    if key not in CDET:
        CDET[key] = cdet(sname, kw)
    d, r, t0 = copy.deepcopy(CDET[key])
    d._config = DetectorConfig(hold_s=hold_s)
    if seed:
        d._occupied = True; d._hold_until_mono = None
        d.occ_gates = {2, 3}; d._occ_start = STREAM[sname][1][0][0] - t0
        d._last_near = STREAM[sname][1][0][0] - t0; d._last_far = None
    rec = []
    for ts, mv, st in STREAM[sname][1]:
        r.add(ts, st); d.ret = r.score
        o = d.process(Frame(ts, ts - t0, tuple(mv), tuple(st), 0, False))
        rec.append((ts, o.occupied, False))
    return rec

# ---- policies -------------------------------------------------------------
DPRIME = dict(grace_s=90., use_ret=True, ret_on=12., ret_all=True, near_max=1, lead_max=1,
              cross_n=20, cross_win=20., quiet_s=10., guard_s=0.)
FORMC = dict(grace_s=60., use_ret=True, ret_on=20., form='c', ret_all=True,
             near_max=1, lead_max=1)

def apply(policy, sname, hold_s=30., seed=False):
    if policy == 'arming':
        return go(sname, hold_s=hold_s, taup=90., seed=seed, **DPRIME)
    return goc(sname, hold_s=hold_s, seed=seed, **FORMC)

def edg(rec):
    tl = []; p = None
    for ts, o, _ in rec:
        if p is None: p = o; continue
        if o != p: tl.append((ts, o)); p = o
    return tl
def relafter(rec, t):
    was = None
    for ts, o, _ in rec:
        if ts < t: was = o; continue
        if was and not o: return ts
        was = o
    return None
def V(x): return hm(x) if x else '--'

def score(policy_bath, policy_fd, hold_s=30.):
    rb = apply(policy_bath, 'bath', hold_s); rm = apply(policy_bath, 'MAX', hold_s)
    rk = apply(policy_bath, 'kitchen', hold_s)
    rf = apply(policy_fd, 'fd', hold_s); rs = apply(policy_fd, 'fdseed', hold_s, seed=True)
    o = {}
    tlb = edg(rb); tlm = edg(rm)
    o['b_ent'] = next((t for t, x in tlb if x), None)
    o['b_early'] = next((t for t, x in tlb if not x and ARRIVE < t < DEPART), None)
    o['b_rel'] = relafter(rb, DEPART)
    o['m_ent'] = next((t for t, x in tlm if x), None)
    o['m_early'] = next((t for t, x in tlm if not x and ARRIVE < t < DEPART), None)
    o['m_rel'] = relafter(rm, ARRIVE)
    o['k_ent'] = next((t for t, x in edg(rk) if x), None)
    tlf = edg(rf)
    o['f_ent'] = next((t for t, x in tlf if x and t >= BACK - 20), None)
    o['drops'] = [t for t, x in tlf if not x and T(21, 40, 30) <= t < T(21, 55)]
    den = [1 for ts, _, _ in rf if T(21, 22) <= ts < T(21, 39)]
    o['emp'] = 100. * sum(1 for ts, oc, _ in rf if T(21, 22) <= ts < T(21, 39) and oc) / max(len(den), 1)
    o['srel'] = next((ts for ts, oc, _ in rs if not oc), None)
    return o

if __name__ == '__main__':
    for hold_s in (30., 60.):
        print('\n===== hold_s=%.0f =====' % hold_s, flush=True)
        print('%-34s %-9s %-9s %-9s %-9s %-7s | %-9s %-5s %-9s %s' % (
            'assignment (D0:6E / FD:68)', 'bathENT', 'bathREL', 'maxENT', 'maxREL',
            'kitch', 'fdENT', 'emp%', 'seedREL', 'fd drops'), flush=True)
        for pb, pf, nm in (('arming', 'retention', 'MATCHED  arming / retention'),
                           ('arming', 'arming', 'both arming (4e D-prime)'),
                           ('retention', 'retention', 'both retention (4d form c)'),
                           ('retention', 'arming', 'SWAPPED  retention / arming')):
            o = score(pb, pf, hold_s)
            print('%-34s %-9s %-9s %-9s %-9s %-7s | %-9s %-5.1f %-9s %s' % (
                nm, V(o['b_ent']),
                (V(o['b_early']) + '!') if o['b_early'] else V(o['b_rel']),
                V(o['m_ent']),
                (V(o['m_early']) + '!') if o['m_early'] else V(o['m_rel']),
                V(o['k_ent']) if o['k_ent'] else 'NEVER',
                V(o['f_ent']), o['emp'], V(o['srel']),
                ', '.join(hm(t) for t in o['drops']) or 'none'), flush=True)
