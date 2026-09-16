"""Leading-edge gate WITH isolated-gate suppression, over false vs genuine entries.

Uses lead.py (faithful replica of baseline.residuals + detector._score isolated-gate rule).
"""
import sys, datetime, zoneinfo, sqlite3, collections
sys.path.insert(0, '/private/tmp/claude-500/-Users-rmk-Repo-home-assistant/5b47b34c-4417-452d-8f77-ce48ba08e904/scratchpad')
from lead import scan, TZ, K, GATES

S = '/private/tmp/claude-500/-Users-rmk-Repo-home-assistant/5b47b34c-4417-452d-8f77-ce48ba08e904/scratchpad'
PROD = S + '/prod-frames.db'
DEV = '/Users/rmk/Repo/home-assistant/config/smart_ld2410/frames.db'

def hm(t): return datetime.datetime.fromtimestamp(t, TZ).strftime('%H:%M:%S')
def T(y, mo, d, h, mi, s=0):
    return datetime.datetime(y, mo, d, h, mi, s, tzinfo=TZ).timestamp()

def surviving(runs):
    return [g for r in runs for g in r]

def blocks(out, gap=5.0, min_dur=1.0):
    """Activity blocks: contiguous frames with any RAW-hot move gate."""
    bl = []; cur = None
    for rec in out:
        ts, lraw, lsup, rm, peaks, sup, runs = rec
        if lraw is not None:
            if cur and ts - cur[-1][0] <= gap:
                cur.append(rec)
            else:
                if cur: bl.append(cur)
                cur = [rec]
    if cur: bl.append(cur)
    return [b for b in bl if b[-1][0] - b[0][0] >= min_dur or len(b) >= 5]

def block_table(bl, title, marks=()):
    print('\n%s' % title)
    print('  %-9s %-9s %5s  %-8s %-8s  %s' % ('start', 'end', 'dur', 'lead_raw', 'lead_sup', 'lead_sup histogram (frames)'))
    for b in bl:
        t0, t1 = b[0][0], b[-1][0]
        raws = [r[1] for r in b if r[1] is not None]
        sups = [r[2] for r in b if r[2] is not None]
        hist = collections.Counter(sups)
        h = ' '.join('g%d:%d' % (g, hist[g]) for g in sorted(hist)) or '-- none survive --'
        tag = ''
        for m, lab in marks:
            if t0 - 3 <= m <= t1 + 3: tag = '  <<< %s' % lab
        print('  %-9s %-9s %5.0fs %-8s %-8s  %s%s' % (
            hm(t0), hm(t1), t1 - t0,
            min(raws) if raws else '-', min(sups) if sups else 'none', h, tag))

def window_detail(out, t0, t1, label):
    sel = [r for r in out if t0 <= r[0] <= t1]
    raws = [r[1] for r in sel if r[1] is not None]
    sups = [r[2] for r in sel if r[2] is not None]
    hr = collections.Counter(raws); hs = collections.Counter(sups)
    print('  %-26s frames=%-5d lead_raw min=%-4s %-30s lead_sup min=%-5s %s' % (
        label, len(sel), min(raws) if raws else '-',
        ' '.join('g%d:%d' % (g, hr[g]) for g in sorted(hr)),
        min(sups) if sups else 'none',
        ' '.join('g%d:%d' % (g, hs[g]) for g in sorted(hs)) or '(no surviving run)'))

# ---------------------------------------------------------------- 1. FALSE
print('=' * 100)
print('1) PROD D0:6E  2026-09-11 05:00-06:00 EDT  -- bathroom EMPTY (wife in kitchen through wall)')
print('=' * 100)
f0, f1 = T(2026, 9, 11, 5, 0), T(2026, 9, 11, 6, 0)
prod = scan(PROD, 'D0:6E%', f0, f1)
print('frames scored: %d  (%s -> %s)' % (len(prod), hm(prod[0][0]), hm(prod[-1][0])))
E1, E2 = 1789117909.94, 1789119384.96   # shipped detector "occupied" events
block_table(blocks(prod), 'activity blocks (>=1s of raw-hot move gates):',
            marks=[(E1, 'FALSE ENTRY 05:11:49'), (E2, 'FALSE ENTRY 05:36:24')])
print('\n  zoom on the two shipped false entries (entry-30s .. entry+15s):')
window_detail(prod, E1 - 30, E1 + 15, 'false entry 05:11:49')
window_detail(prod, E2 - 30, E2 + 15, 'false entry 05:36:24')

# ---------------------------------------------------------------- 3. GATE 0
print('\n' + '=' * 100)
print('3) GATE-0 chatter, whole 05:00-06:00 hour')
print('=' * 100)
n = len(prod)
raw0 = sum(1 for r in prod if r[3][0] >= K)
sup0 = sum(1 for r in prod if 0 in surviving(r[6]))
lead0_raw = sum(1 for r in prod if r[1] == 0)
lead0_sup = sum(1 for r in prod if r[2] == 0)
print('  frames                                        %7d' % n)
print('  raw move residual g0 >= k(%.1f)                %7d  (%.2f%%)' % (K, raw0, 100.0 * raw0 / n))
print('  g0 survives isolated-gate suppression          %7d  (%.2f%%)' % (sup0, 100.0 * sup0 / n))
print('  -> suppression kills                           %7d  (%.1f%% of g0-hot frames)' % (
    raw0 - sup0, 100.0 * (raw0 - sup0) / max(raw0, 1)))
print('  frames whose RAW leading gate      = 0         %7d  (%.2f%%)' % (lead0_raw, 100.0 * lead0_raw / n))
print('  frames whose SUPPRESSED leading gate = 0       %7d  (%.2f%%)' % (lead0_sup, 100.0 * lead0_sup / n))

# ---------------------------------------------------------------- 2. GENUINE
print('\n' + '=' * 100)
print('2) DEV DB D0:6E  2026-09-09 labelled GENUINE toilet sessions (30s lead-in included)')
print('=' * 100)
c = sqlite3.connect('file:%s?mode=ro' % DEV, uri=True)
evs = c.execute("select ts_utc,payload from events where sensor_id like 'D0:6E%' and kind='label' "
                "and ts_utc>=? and ts_utc<? order by ts_utc",
                (T(2026, 9, 9, 0, 0), T(2026, 9, 10, 0, 0))).fetchall()
sessions = []
for i, (t, p) in enumerate(evs):
    if '"toilet"' in p:
        end = next((e[0] for e in evs[i + 1:]), t + 300)
        sessions.append((t, end))
for t0, t1 in sessions:
    print('\n  session: toilet %s -> %s (%.0fs), scanning from %s (30s lead-in)' % (
        hm(t0), hm(t1), t1 - t0, hm(t0 - 30)))
    out = scan(DEV, 'D0:6E%', t0 - 30, t1)
    if not out:
        print('    (no scored frames)'); continue
    block_table(blocks(out), '  activity blocks:')
    window_detail(out, t0 - 30, t0 + 15, 'entry window (-30s..+15s)')
    window_detail(out, t0, t1, 'whole labelled session')
