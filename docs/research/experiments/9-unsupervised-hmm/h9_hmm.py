"""Experiment 9: unsupervised 2-state Gaussian HMM over per-frame features.

Features reuse lead.py (suppressed move residuals / leading gate) and the 4e
signed peak-held retention. Fit with plain numpy Baum-Welch (scaled), decode
with Viterbi + posteriors, identify the occupied state post hoc.
"""
import sys, math, json
import numpy as np
S = '/private/tmp/claude-500/-Users-rmk-Repo-home-assistant/5b47b34c-4417-452d-8f77-ce48ba08e904/scratchpad'
sys.path.insert(0, S)
import h9_base as H          # streams, grader, baselines
from lead import Model, leading_suppressed, GATES, K, SUPPORT_TAU
SRet = H.SRet

T, hm = H.T, H.hm

# ----------------------------------------------------------------- features
FEATNAMES = ['supmove', 'ret', 'near', 'score']

def features(sname):
    warm, body = H.STREAM[sname]
    m = Model(); sup = [0.0] * GATES; prev = None
    ret = SRet(warm[0][2], 90.0)
    nearema = 0.0
    ts_out = []; X = []
    for rows, emit in ((warm, False), (body, True)):
        for ts, mv, st in rows:
            ret.add(ts, st)
            if m.ready:
                rm, rs = m.res(mv, st)
                peaks = [max(0.0, rm[g], rs[g]) for g in range(GATES)]
                a = 1.0 if prev is None else (1.0 - math.exp(-min(ts - prev, 2.0) / SUPPORT_TAU)
                                              if ts > prev else 0.0)
                for g in range(GATES):
                    sup[g] += a * (peaks[g] - sup[g])
                ls, runs = leading_suppressed(rm, sup)
                keep = set(g for r in runs for g in r)
                supmove = max([rm[g] for g in keep], default=0.0)
                rv = max(ret.out[g] for g in range(2, GATES))
                na = 1.0 - math.exp(-min(ts - prev, 2.0) / 10.0) if prev is not None else 1.0
                nearema += na * ((1.0 if (ls is not None and ls <= 1) else 0.0) - nearema)
                if emit:
                    ts_out.append(ts)
                    X.append([math.asinh(max(supmove, 0.0)), math.asinh(rv),
                              math.asinh(10.0 * nearema), math.asinh(max(peaks))])
            prev = ts
            m.add(ts, list(mv), list(st))
    return np.array(ts_out), np.array(X)

# ----------------------------------------------------------------- HMM
def fit(X, n_iter=120, seed=0, sticky_init=False, tol=1e-6):
    rng = np.random.default_rng(seed)
    T_, D = X.shape
    # init: random responsibilities -> M step (no threshold knowledge used)
    g = rng.random((T_, 2)); g /= g.sum(1, keepdims=True)
    # nudge with a random projection split so the two states differ at all
    w = rng.normal(size=D); p = X @ w
    g[:, 0] = 0.5 + 0.4 * (p > np.median(p)); g[:, 1] = 1 - g[:, 0]
    mu = (g.T @ X) / g.sum(0)[:, None]
    var = (g.T @ (X ** 2)) / g.sum(0)[:, None] - mu ** 2
    var = np.maximum(var, 1e-3)
    A = np.array([[0.9, 0.1], [0.1, 0.9]]) if sticky_init else np.full((2, 2), 0.5)
    pi = np.array([0.5, 0.5])
    prev_ll = -np.inf
    for it in range(n_iter):
        # emissions (log)
        lB = -0.5 * (((X[:, None, :] - mu[None]) ** 2) / var[None]).sum(2) \
             - 0.5 * np.log(2 * np.pi * var).sum(1)[None, :]
        B = np.exp(lB - lB.max(1, keepdims=True))
        off = lB.max(1)
        # forward
        al = np.zeros((T_, 2)); c = np.zeros(T_)
        al[0] = pi * B[0]; c[0] = al[0].sum(); al[0] /= c[0]
        for t in range(1, T_):
            al[t] = (al[t - 1] @ A) * B[t]; c[t] = al[t].sum(); al[t] /= c[t]
        ll = (np.log(c) + off).sum()
        # backward
        be = np.zeros((T_, 2)); be[-1] = 1.0
        for t in range(T_ - 2, -1, -1):
            be[t] = (A @ (B[t + 1] * be[t + 1])) / c[t + 1]
        g = al * be; g /= g.sum(1, keepdims=True)
        xi = np.zeros((2, 2))
        for t in range(T_ - 1):
            x = (al[t][:, None] * A) * (B[t + 1] * be[t + 1])[None, :] / c[t + 1]
            xi += x
        A = xi / xi.sum(1, keepdims=True)
        pi = g[0] / g[0].sum()
        Nk = g.sum(0) + 1e-9
        mu = (g.T @ X) / Nk[:, None]
        var = np.maximum((g.T @ (X ** 2)) / Nk[:, None] - mu ** 2, 1e-3)
        if abs(ll - prev_ll) < tol * abs(ll):
            break
        prev_ll = ll
    return dict(A=A, pi=pi, mu=mu, var=var, ll=ll, iters=it + 1)

def decode(M, X):
    A, pi, mu, var = M['A'], M['pi'], M['mu'], M['var']
    T_ = X.shape[0]
    lB = -0.5 * (((X[:, None, :] - mu[None]) ** 2) / var[None]).sum(2) \
         - 0.5 * np.log(2 * np.pi * var).sum(1)[None, :]
    lA = np.log(np.maximum(A, 1e-300))
    d = np.log(np.maximum(pi, 1e-300)) + lB[0]
    psi = np.zeros((T_, 2), int)
    for t in range(1, T_):
        cand = d[:, None] + lA
        psi[t] = cand.argmax(0); d = cand.max(0) + lB[t]
    path = np.zeros(T_, int); path[-1] = d.argmax()
    for t in range(T_ - 2, -1, -1):
        path[t] = psi[t + 1, path[t + 1]]
    # posteriors
    B = np.exp(lB - lB.max(1, keepdims=True))
    al = np.zeros((T_, 2)); c = np.zeros(T_)
    al[0] = pi * B[0]; c[0] = al[0].sum(); al[0] /= c[0]
    for t in range(1, T_):
        al[t] = (al[t - 1] @ A) * B[t]; c[t] = al[t].sum(); al[t] /= c[t]
    be = np.zeros((T_, 2)); be[-1] = 1.0
    for t in range(T_ - 2, -1, -1):
        be[t] = (A @ (B[t + 1] * be[t + 1])) / c[t + 1]
    g = al * be; g /= g.sum(1, keepdims=True)
    return path, g

# ----------------------------------------------------------------- glue
SETS = {'A score': [3], 'B score+ret': [3, 1], 'C sup+ret+near': [0, 1, 2],
        'D all4': [0, 1, 2, 3]}

def run_stream(sname, cols, seeds=(0, 1, 2, 3, 4), sticky_init=False, Xcache={}):
    if sname not in Xcache:
        Xcache[sname] = features(sname)
    ts, Xf = Xcache[sname]
    X = Xf[:, cols]
    mn, sd = X.mean(0), X.std(0) + 1e-9
    Z = (X - mn) / sd
    best = None
    for s in seeds:
        M = fit(Z, seed=s, sticky_init=sticky_init)
        if best is None or M['ll'] > best['ll']:
            best = M
    path, post = decode(best, Z)
    # occupied = state with higher mean on the energy feature (first column given)
    occ_state = int(np.argmax(best['mu'][:, 0]))
    rec = [(ts[i], bool(path[i] == occ_state), float(post[i, occ_state])) for i in range(len(ts))]
    return best, occ_state, rec, mn, sd

def dwell(A, i, dt=0.1):
    p = A[i, i]
    return dt / max(1e-12, 1 - p)

if __name__ == '__main__':
    out = {}
    for setname, cols in SETS.items():
        recs = {}
        info = {}
        for sname in ('fd', 'through', 'bathfix'):
            M, occ_state, rec, mn, sd = run_stream(sname, cols)
            recs[sname] = rec
            info[sname] = dict(A=M['A'].tolist(), occ=occ_state, ll=M['ll'],
                               mu=M['mu'].tolist(), var=M['var'].tolist(),
                               dwellON=dwell(M['A'], occ_state),
                               dwellOFF=dwell(M['A'], 1 - occ_state),
                               iters=M['iters'])
        o = H.grade(setname, recs['fd'], recs['through'], recs['bathfix'])
        o['ba_rel'] = H.first_off(recs['bathfix'], o['ba_ent'] + 1) if o['ba_ent'] else None
        print('### HMM feature set %s' % setname)
        H.show('hmm ' + setname, o)
        for sname in info:
            i = info[sname]
            print('   %-8s A=[[%.5f %.5f][%.5f %.5f]] dwell ON %.1fs OFF %.1fs  occ_state=%d it=%d'
                  % (sname, i['A'][0][0], i['A'][0][1], i['A'][1][0], i['A'][1][1],
                     i['dwellON'], i['dwellOFF'], i['occ'], i['iters']))
        # posterior usability
        for sname in recs:
            p = np.array([r[2] for r in recs[sname]])
            amb = float(((p > 0.1) & (p < 0.9)).mean() * 100)
            print('   %-8s posterior: %%ambiguous(0.1-0.9)=%.2f%%  mean=%.3f' % (sname, amb, p.mean()))
        print()
        out[setname] = dict(grade={k: (v if not isinstance(v, float) else round(v, 2))
                                   for k, v in o.items()}, info=info)
    json.dump(out, open(S + '/h9_hmm.json', 'w'), indent=1, default=str)
