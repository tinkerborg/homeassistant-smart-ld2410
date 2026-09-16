"""Exp 9 round 2: give the HMM its best shot.
 - temporal aggregation (1s / 5s / 10s frames)
 - Dirichlet sticky prior on the transition matrix (= hysteresis handed to it)
 - cross-fixture fit (fit on throughwall, decode on bath -- same sensor)
 - posterior as a confidence layer: AUC vs ground truth, vs raw features
"""
import sys, math, json
import numpy as np
S = '/private/tmp/claude-500/-Users-rmk-Repo-home-assistant/5b47b34c-4417-452d-8f77-ce48ba08e904/scratchpad'
sys.path.insert(0, S)
import h9_base as H
import h9_hmm as M9

T, hm = H.T, H.hm
T2 = H.T2
np.set_printoptions(precision=5, suppress=True)

FEAT = {}
for s in ('fd', 'through', 'bathfix'):
    FEAT[s] = M9.features(s)
    print('features %-8s %s' % (s, FEAT[s][1].shape), flush=True)

def aggregate(ts, X, win):
    if win <= 0:
        return ts, X
    b = np.floor(ts / win).astype(np.int64)
    _, idx = np.unique(b, return_index=True)
    idx = np.sort(idx)
    ends = np.append(idx[1:], len(ts))
    out = np.array([X[a:e].mean(0) for a, e in zip(idx, ends)])
    return ts[idx], out

def fit_sticky(X, n_iter=200, seed=0, kappa=0.0, tol=1e-7):
    """Baum-Welch with a Dirichlet(kappa) pseudo-count on self-transitions."""
    rng = np.random.default_rng(seed)
    T_, D = X.shape
    w = rng.normal(size=D); p = X @ w
    g = np.zeros((T_, 2)); g[:, 0] = 0.5 + 0.4 * (p > np.median(p)); g[:, 1] = 1 - g[:, 0]
    mu = (g.T @ X) / g.sum(0)[:, None]
    var = np.maximum((g.T @ (X ** 2)) / g.sum(0)[:, None] - mu ** 2, 1e-3)
    A = np.full((2, 2), 0.5); pi = np.array([0.5, 0.5]); prev = -np.inf
    for it in range(n_iter):
        lB = -0.5 * (((X[:, None, :] - mu[None]) ** 2) / var[None]).sum(2) \
             - 0.5 * np.log(2 * np.pi * var).sum(1)[None, :]
        off = lB.max(1); B = np.exp(lB - off[:, None])
        al = np.zeros((T_, 2)); c = np.zeros(T_)
        al[0] = pi * B[0]; c[0] = al[0].sum(); al[0] /= c[0]
        for t in range(1, T_):
            al[t] = (al[t - 1] @ A) * B[t]; c[t] = al[t].sum(); al[t] /= c[t]
        ll = (np.log(c) + off).sum()
        be = np.zeros((T_, 2)); be[-1] = 1.0
        for t in range(T_ - 2, -1, -1):
            be[t] = (A @ (B[t + 1] * be[t + 1])) / c[t + 1]
        g = al * be; g /= g.sum(1, keepdims=True)
        xi = np.zeros((2, 2))
        for t in range(T_ - 1):
            xi += (al[t][:, None] * A) * (B[t + 1] * be[t + 1])[None, :] / c[t + 1]
        xi = xi + kappa * np.eye(2)
        A = xi / xi.sum(1, keepdims=True)
        pi = g[0] / g[0].sum()
        Nk = g.sum(0) + 1e-9
        mu = (g.T @ X) / Nk[:, None]
        var = np.maximum((g.T @ (X ** 2)) / Nk[:, None] - mu ** 2, 1e-3)
        if abs(ll - prev) < tol * abs(ll): break
        prev = ll
    return dict(A=A, pi=pi, mu=mu, var=var, ll=ll, iters=it + 1)

# ------------------------------------------------------------------ grading helpers
def summarize(rec, name, extra=''):
    o = H.grade(name, rec['fd'], rec['through'], rec['bathfix'])
    o['ba_rel'] = H.first_off(rec['bathfix'], o['ba_ent'] + 1) if o['ba_ent'] else None
    nd = len(o['fd_drops'])
    ent = ('%+.0f' % (o['fd_ent'] - T(21, 39, 40))) if o['fd_ent'] else 'n/a'
    be = ('%+.0f' % (o['ba_ent'] - T(22, 4, 1))) if o['ba_ent'] else 'n/a'
    br = ('%+.0f' % (o['ba_rel'] - T(22, 6, 43))) if o['ba_rel'] else 'n/a'
    nth = len([1 for t, oc in H.transitions(rec['through']) if oc])
    print('%-34s | seatB %5.1f%% drops %4d | empty %5.1f%% | ent %6ss | THRU %5.1f%%/%5.1f%% ent %4d '
          '| BATH %6ss/%7ss pre %4.1f%% %s'
          % (name, o['fd_seatB_drop'], nd, o['fd_empty'], ent, o['th_all'], o['th_bleed'],
             nth, be, br, o['ba_pre'], extra), flush=True)
    return o

def build(cols, win, kappa, seeds=(0, 1, 2, 3, 4), fit_on=None):
    rec = {}; info = {}
    shared = None
    order = ['fd', 'through', 'bathfix']
    if fit_on: order = [fit_on] + [s for s in order if s != fit_on]
    for s in order:
        ts, Xf = FEAT[s]
        tsa, Xa = aggregate(ts, Xf[:, cols], win)
        if fit_on and s != fit_on:
            mn, sd, best = shared
        else:
            mn, sd = Xa.mean(0), Xa.std(0) + 1e-9
            Z = (Xa - mn) / sd
            best = None
            for sd_ in seeds:
                m = fit_sticky(Z, seed=sd_, kappa=kappa)
                if best is None or m['ll'] > best['ll']: best = m
            if fit_on and s == fit_on: shared = (mn, sd, best)
        Z = (Xa - mn) / sd
        path, post = M9.decode(best, Z)
        occ = int(np.argmax(best['mu'][:, 0]))
        rec[s] = [(tsa[i], bool(path[i] == occ), float(post[i, occ])) for i in range(len(tsa))]
        info[s] = dict(A=best['A'], occ=occ,
                       dON=win / max(1e-12, 1 - best['A'][occ, occ]) if win else
                           0.1 / max(1e-12, 1 - best['A'][occ, occ]),
                       dOFF=(win or 0.1) / max(1e-12, 1 - best['A'][1 - occ, 1 - occ]))
    return rec, info

# ------------------------------------------------------------------ ground truth / AUC
def truth(s, ts):
    y = np.full(len(ts), -1)
    if s == 'fd':
        y[(ts >= T(21, 12)) & (ts < T(21, 20))] = 1
        y[(ts >= T(21, 22)) & (ts < T(21, 39))] = 0
        y[(ts >= T(21, 41)) & (ts < T(21, 55))] = 1
    elif s == 'through':
        y[:] = 0
    else:
        y[(ts >= T(22, 4, 1)) & (ts < T(22, 6, 43))] = 1
        y[(ts < T(22, 3)) | (ts >= T(22, 7, 30))] = 0
    return y

def auc(score, y):
    m = y >= 0
    s, yy = score[m], y[m]
    if yy.sum() == 0 or yy.sum() == len(yy): return float('nan')
    r = np.argsort(np.argsort(s, kind='stable'), kind='stable') + 1.0
    n1 = yy.sum(); n0 = len(yy) - n1
    return float((r[yy == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))

if __name__ == '__main__':
    print('\n--- aggregation sweep (feature set D all4, no prior) ---')
    for win in (0, 1.0, 5.0, 10.0):
        rec, info = build([0, 1, 2, 3], win, 0.0)
        summarize(rec, 'D all4 win=%-4s k=0' % win,
                  'dwellON %s' % '/'.join('%.0f' % info[s]['dON'] for s in info))
    print('\n--- aggregation sweep (feature set B score+ret, no prior) ---')
    for win in (0, 1.0, 5.0, 10.0):
        rec, info = build([3, 1], win, 0.0)
        summarize(rec, 'B score+ret win=%-4s k=0' % win,
                  'dwellON %s' % '/'.join('%.0f' % info[s]['dON'] for s in info))
    print('\n--- sticky Dirichlet prior (win=1s, set D) : hysteresis handed to it ---')
    for kappa in (1e2, 1e3, 1e4, 1e5):
        rec, info = build([0, 1, 2, 3], 1.0, kappa)
        summarize(rec, 'D all4 win=1 kappa=%-6g' % kappa,
                  'dwellON %s' % '/'.join('%.0f' % info[s]['dON'] for s in info))
    print('\n--- cross-fixture: fit on THROUGHWALL (100%% empty), decode everywhere ---')
    for win, kappa in ((1.0, 0.0), (1.0, 1e4), (5.0, 1e3)):
        rec, info = build([0, 1, 2, 3], win, kappa, fit_on='through')
        summarize(rec, 'fit=through win=%s k=%g' % (win, kappa),
                  'dwellON %s' % '/'.join('%.0f' % info[s]['dON'] for s in info))

    print('\n--- posterior as a confidence layer: AUC vs ground truth ---')
    rec, info = build([0, 1, 2, 3], 1.0, 1e4)
    tot_n = tot_s = 0.0
    print('%-10s %8s %8s %8s %8s %8s' % ('stream', 'HMMpost', 'score', 'ret', 'supmove', 'near'))
    for s in ('fd', 'through', 'bathfix'):
        ts = np.array([r[0] for r in rec[s]]); p = np.array([r[2] for r in rec[s]])
        y = truth(s, ts)
        tsf, Xf = FEAT[s]
        tsa, Xa = aggregate(tsf, Xf, 1.0)
        n = min(len(tsa), len(ts))
        row = [auc(p[:n], y[:n])] + [auc(Xa[:n, j], y[:n]) for j in (3, 1, 0, 2)]
        print('%-10s %8s' % (s, ' '.join('%8.3f' % v for v in row)))
        m = (y >= 0).sum(); tot_n += m; tot_s += row[0] * m
