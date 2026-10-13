"""4d: leading-edge-conditioned RELEASE on top of the 4c composite entry.

Entry   = shipped score/hysteresis AND arrival gate AND suppressed leading gate <= lead_max
Release = while occupied, hold is only refreshed by ATTRIBUTABLE evidence:
    near   : score >= exit_score AND suppressed leading gate <= near_max   (room's own)
    ret    : retention stat elevated at the occupancy's gates AND no far-lead
             activity within far_hold_s                                    (fade-in-place)
  Anything else (score over exit but leading >=2, i.e. the neighbour) does NOT
  reset the countdown.

Variants: A = near only, B = near OR retention.
"""
import sqlite3, datetime, zoneinfo, math, sys, collections

S = '/private/tmp/claude-500/-Users-rmk-Repo-home-assistant/5b47b34c-4417-452d-8f77-ce48ba08e904/scratchpad'
sys.path.insert(0, S)
sys.path.insert(0, '/Users/rmk/Repo/homeassistant-smart-ld2410')
from lead import leading_suppressed
from custom_components.smart_ld2410.algo.detector import Detector
from custom_components.smart_ld2410.algo.types import DetectorConfig, Frame

TZ = zoneinfo.ZoneInfo('America/New_York')
PROD = S + '/prod-frames.db'
FIX = '/Users/rmk/Repo/homeassistant-smart-ld2410/tests/fixtures/recordings/livingroom-reset-seated-fd68.db'
def T(h, m, s=0): return datetime.datetime(2026, 9, 11, h, m, s, tzinfo=TZ).timestamp()
def hm(t): return datetime.datetime.fromtimestamp(t, TZ).strftime('%H:%M:%S')

# ------------------------------------------------------------------ retention stat
TAU_F, TAU_S, FLOOR_MIN = 2.0, 60.0, 0.10

class Retention:
    """acc3.py statistic: |fastEMA - slowEMA| of still / EMA10 |dframe| floor."""
    def __init__(self, st0):
        self.f = list(map(float, st0)); self.s = list(self.f)
        self.fl = [0.3] * 9; self.prev_st = list(map(float, st0)); self.prev_ts = None
        self.score = [0.0] * 9
    def add(self, ts, st):
        dt = 2.0 if self.prev_ts is None else min(max(ts - self.prev_ts, 0.0), 2.0)
        self.prev_ts = ts
        af = 1 - math.exp(-dt / TAU_F); a_s = 1 - math.exp(-dt / TAU_S); a10 = 1 - math.exp(-dt / 10.)
        for g in range(9):
            x = float(st[g])
            self.f[g] += af * (x - self.f[g]); self.s[g] += a_s * (x - self.s[g])
            dc = min(abs(x - self.prev_st[g]), 4 * self.fl[g] + 0.5)
            self.fl[g] += a10 * (dc - self.fl[g])
            self.score[g] = abs(self.f[g] - self.s[g]) / max(self.fl[g], FLOOR_MIN)
        self.prev_st = [float(v) for v in st]
        return self.score

# ------------------------------------------------------------------ composite
class Composite(Detector):
    def __init__(self, cfg, *, lead_max=1, near_max=1, far_min=2, grace_s=0.0,
                 use_ret=False, ret_on=20.0, far_hold_s=10.0, occ_gate_win_s=0.0,
                 form='a', ret_all=False):
        super().__init__(cfg)
        self.lead_max, self.near_max, self.far_min = lead_max, near_max, far_min
        self.grace_s = grace_s
        self.use_ret, self.ret_on = use_ret, ret_on
        self.far_hold_s, self.occ_gate_win_s = far_hold_s, occ_gate_win_s
        self.form, self.ret_all = form, ret_all
        self.lead_sup = None
        self.ret = [0.0] * 9
        self.occ_gates = set(); self._occ_start = None
        self._last_far = None; self._last_near = None
        self._cur_active = ()
        self.dbg = None

    def _track_candidate(self, frame, active_gates, residuals_move):
        super()._track_candidate(frame, active_gates, residuals_move)
        ls, _ = leading_suppressed(list(residuals_move), self._support)
        self.lead_sup = ls
        self._cur_active = active_gates

    def _advance(self, score, ts_mono, *, entry_suppressed=False):
        cfg = self._config
        ls = self.lead_sup
        near = ls is not None and ls <= self.near_max
        far = ls is not None and ls >= self.far_min
        if far:
            self._last_far = ts_mono
        if near:
            self._last_near = ts_mono
        if not self._occupied:
            if ls is None or ls > self.lead_max:
                entry_suppressed = True
            if score >= cfg.enter_score and not entry_suppressed:
                self._occupied = True
                self._hold_until_mono = None
                self.occ_gates = set(self._cur_active)
                self._occ_start = ts_mono
                self._last_far = None
            self.dbg = (score, ls, near, far, False, False)
            return
        # widen the occupancy's gate set over the first occ_gate_win_s
        if self._occ_start is not None and ts_mono - self._occ_start <= self.occ_gate_win_s:
            self.occ_gates |= set(self._cur_active)
        near_recent = near or (self._last_near is not None
                               and (ts_mono - self._last_near) <= self.grace_s)
        far_recent = self._last_far is not None and (ts_mono - self._last_far) <= self.far_hold_s
        gates = set(range(2, 9)) if self.ret_all else (self.occ_gates or set(range(9)))
        ret_hi = self.use_ret and max(self.ret[g] for g in gates) >= self.ret_on
        if self.form == 'a':      # near OR (retention when the neighbourhood is quiet)
            ret_elev = ret_hi and not far_recent
            block = (score >= cfg.exit_score and near_recent) or ret_elev
        elif self.form == 'b':    # evidence must exist AND be attributable
            ret_elev = ret_hi
            block = score >= cfg.exit_score and (near_recent or ret_hi)
        else:                     # 'c': near OR retention, no far veto
            ret_elev = ret_hi
            block = (score >= cfg.exit_score and near_recent) or ret_hi
        self.dbg = (score, ls, near_recent, far_recent, ret_elev, block)
        if block:
            self._hold_until_mono = None
        elif self._hold_until_mono is None:
            self._hold_until_mono = ts_mono + cfg.hold_s
        elif ts_mono >= self._hold_until_mono:
            self._occupied = False
            self._hold_until_mono = None
            self._freeze_until_mono = ts_mono + cfg.freeze_hold_s


def run(warm, rows, *, mode='composite', hold_s=30.0, **kw):
    cfg = DetectorConfig(hold_s=hold_s)
    d = Detector(cfg) if mode == 'shipped' else Composite(cfg, **kw)
    ret = Retention(warm[0][2] if warm else rows[0][2])
    t0 = warm[0][0] if warm else rows[0][0]
    for ts, mv, st in warm:
        ret.add(ts, st)
        if mode != 'shipped': d.ret = ret.score
        d.process(Frame(ts, ts - t0, tuple(mv), tuple(st), 0, False))
    rec = []
    for ts, mv, st in rows:
        ret.add(ts, st)
        if mode != 'shipped': d.ret = ret.score
        o = d.process(Frame(ts, ts - t0, tuple(mv), tuple(st), 0, False))
        rec.append((ts, o.occupied, o.score, o.active_gates,
                    None if mode == 'shipped' else d.lead_sup,
                    None if mode == 'shipped' else d.dbg,
                    max(ret.score[g] for g in range(2, 9))))
    return d, rec


def edges(rec):
    tl = []; prev = None
    for ts, occ, *_ in rec:
        if prev is None: prev = occ; continue
        if occ != prev: tl.append((ts, occ)); prev = occ
    return tl

def fmt_tl(tl):
    return ' '.join('%s%s' % ('ON@' if o else 'off@', hm(t)) for t, o in tl) or '(flat)'

def occ_seconds(rec):
    tot = 0.0; on = None
    for ts, occ, *_ in rec:
        if occ and on is None: on = ts
        elif not occ and on is not None: tot += ts - on; on = None
    if on is not None: tot += rec[-1][0] - on
    return tot
