"""Analysis: per-sensor histograms of onset suppressed-leading-gate for
confirmed vs fizzled episodes, overlap coefficient, enable/disable decision,
contamination check and history-sensitivity sweep."""
import sys, json, glob, datetime, zoneinfo, collections
TZ = zoneinfo.ZoneInfo('America/New_York')
S = '/private/tmp/claude-500/-Users-rmk-Repo-home-assistant/5b47b34c-4417-452d-8f77-ce48ba08e904/scratchpad'
NEAR = (0, 1)          # candidate "entry" lead gates
MIN_N = 12             # minimum episodes per class before deciding


def ts(t):
    return datetime.datetime.fromtimestamp(t, TZ).strftime('%m-%d %H:%M:%S')


HZ = 'm10'

def hist(eps, cls):
    h = collections.Counter()
    for e in eps:
        if e['cls'] != cls:
            continue
        v = e.get(HZ)
        h[v if v is not None else 'none'] += 1
    return h


def norm(h):
    n = sum(h.values())
    return {k: v / n for k, v in h.items()} if n else {}


def overlap(a, b):
    """Overlap coefficient of two discrete distributions: sum min(p,q)."""
    pa, pb = norm(a), norm(b)
    return sum(min(pa.get(k, 0.0), pb.get(k, 0.0)) for k in set(pa) | set(pb))


def near_frac(h):
    n = sum(h.values())
    if not n:
        return None
    return sum(v for k, v in h.items() if k in NEAR) / n


def decide(conf, fizz):
    """Enable leading-edge entry rule iff the two classes separate on NEAR."""
    nc, nf = sum(conf.values()), sum(fizz.values())
    if nc < MIN_N or nf < MIN_N:
        return 'insufficient', None, None
    pc, pf = near_frac(conf), near_frac(fizz)
    ov = overlap(conf, fizz)
    # Separation criteria (justified in the report):
    #   * confirmed episodes must actually lead near  (pc >= 0.70)
    #   * fizzled episodes must mostly NOT lead near  (pf <= 0.30)
    #   * distributions must be mostly disjoint       (overlap <= 0.45)
    ok = pc >= 0.70 and pf <= 0.30 and ov <= 0.45
    return ('enable' if ok else 'disable'), ov, (pc, pf)


def fmt(h):
    keys = sorted([k for k in h if k != 'none']) + (['none'] if 'none' in h else [])
    n = sum(h.values())
    return 'n=%-4d ' % n + ' '.join('g%s:%d(%.0f%%)' % (k, h[k], 100 * h[k] / n) for k in keys)


def report(r, exclude=None, quiet=False):
    eps = r['episodes']
    if exclude:
        eps = [e for e in eps if not any(a <= e['t0'] <= b for a, b in exclude)]
    conf, fizz = hist(eps, 'confirmed'), hist(eps, 'fizzled')
    amb = hist(eps, 'ambiguous')
    dec, ov, pp = decide(conf, fizz)
    if not quiet:
        print('\n%-20s  frames=%d  episodes=%d  span=%.1fh' % (
            r['tag'], r['nframes'], len(eps), (eps[-1]['t0'] - eps[0]['t0']) / 3600 if eps else 0))
        print('  confirmed(>=60s) %s' % fmt(conf))
        print('  fizzled  (<20s)  %s' % fmt(fizz))
        print('  ambiguous        %s' % fmt(amb))
        if ov is not None:
            print('  overlap=%.2f  P(lead in 0-1 | confirmed)=%.2f  P(lead in 0-1 | fizzled)=%.2f  -> %s'
                  % (ov, pp[0], pp[1], dec.upper()))
        else:
            print('  -> %s' % dec.upper())
    return dec, ov, pp, conf, fizz


def sweep(r, exclude=None):
    """How much history until the decision stabilises?"""
    eps = r['episodes']
    if exclude:
        eps = [e for e in eps if not any(a <= e['t0'] <= b for a, b in exclude)]
    if not eps:
        return
    t0 = eps[0]['t0']
    print('  history sweep:')
    final = None
    rows = []
    for h in [1, 2, 3, 4, 6, 8, 12, 18, 24, 36, 48, 72, 120, 168, 240, 300]:
        sub = [e for e in eps if e['t0'] - t0 <= h * 3600]
        if not sub:
            continue
        if h * 3600 > eps[-1]['t0'] - t0 + 3600:
            break
        c, f = hist(sub, 'confirmed'), hist(sub, 'fizzled')
        d, ov, pp = decide(c, f)
        rows.append((h, d, ov, sum(c.values()), sum(f.values())))
    final = rows[-1][1]
    stable = None
    for i in range(len(rows)):
        if rows[i][1] == final and all(x[1] == final for x in rows[i:]):
            stable = rows[i][0]
            break
    for h, d, ov, nc, nf in rows:
        print('    %4dh  conf=%-4d fizz=%-4d overlap=%s  %s' % (
            h, nc, nf, '%.2f' % ov if ov is not None else ' -- ', d))
    print('    -> decision stable from %s onward (final=%s)' %
          ('%dh' % stable if stable else 'never', final))


if __name__ == '__main__':
    files = sorted(glob.glob(S + '/ep_*.json'))
    rs = {}
    for f in files:
        r = json.load(open(f))
        rs[r['tag']] = r
    order = ['prod-D06E-bath', 'prod-FD68-living', 'dev-D06E-bath', 'dev-FD68-living', 'dev-99CD']
    print('=' * 96)
    print('A) FULL DATA, no contamination handling')
    print('=' * 96)
    for t in order:
        if t in rs:
            report(rs[t])

    # ---- contamination: known through-wall false-occupancy window on prod D0:6E
    FALSE = [(datetime.datetime(2026, 9, 11, 4, 55, tzinfo=TZ).timestamp(),
              datetime.datetime(2026, 9, 11, 6, 5, tzinfo=TZ).timestamp())]
    print('\n' + '=' * 96)
    print('B) CONTAMINATION CHECK -- prod D0:6E with the 09-11 04:55-06:05 through-wall hour removed')
    print('=' * 96)
    if 'prod-D06E-bath' in rs:
        r = rs['prod-D06E-bath']
        dec0, ov0, pp0, c0, f0 = report(r, quiet=True)
        dec1, ov1, pp1, c1, f1 = report(r, exclude=FALSE)
        print('  contaminated-window episodes: %d (%d confirmed, %d fizzled)' % (
            sum(1 for e in r['episodes'] if FALSE[0][0] <= e['t0'] <= FALSE[0][1]),
            sum(c0.values()) - sum(c1.values()), sum(f0.values()) - sum(f1.values())))
        print('  decision with contamination: %s (ov=%.2f)   without: %s (ov=%.2f)' % (
            dec0, ov0 or -1, dec1, ov1 or -1))
        print('  through-wall confirmed episodes, lead gates:')
        tw = collections.Counter(e['lead'] for e in r['episodes']
                                 if FALSE[0][0] <= e['t0'] <= FALSE[0][1] and e['cls'] == 'confirmed')
        print('    ' + (fmt(collections.Counter({k if k is not None else 'none': v for k, v in tw.items()}))
                        if tw else '(none)'))

    print('\n' + '=' * 96)
    print('C) HISTORY SENSITIVITY')
    print('=' * 96)
    for t in order:
        if t in rs:
            print(' %s' % t)
            sweep(rs[t])
