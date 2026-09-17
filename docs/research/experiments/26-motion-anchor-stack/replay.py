"""Experiment-only composition; does not register stages or alter defaults."""

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT))


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


old = load("hist25", HERE.parent / "25-histogram-motion-anchor/analyze.py")
from custom_components.smart_ld2410.algo.types import DetectorConfig, Frame
from custom_components.smart_ld2410.algo.roles import StageEnv
from custom_components.smart_ld2410.algo.scoring.runs import RunScorer
from custom_components.smart_ld2410.algo.scoring.suppression import LoneGateSuppression
from custom_components.smart_ld2410.algo.entry.energy_floor import EnergyFloor
from custom_components.smart_ld2410.algo.presence.motion_anchor import MotionAnchor


class SameGateBalanceAnchor(MotionAnchor):
    """Apply experiment 20's balance condition only when creating a template."""

    def update(self, ts_mono, move, still, floor, spread):
        previous = self._previous_ts
        existing = self.template is not None and (
            previous is None or 0 <= ts_mono - previous <= self.max_gap_s
        )
        qualifies = any(
            move[g] >= 40 and move[g] / max(move[g] + still[g], 1) >= 1 / 3
            for g in range(2, 9)
        )
        threshold = self.motion_threshold
        if not existing and not qualifies:
            self.motion_threshold = float("inf")
        try:
            return super().update(ts_mono, move, still, floor, spread)
        finally:
            self.motion_threshold = threshold


def estimates(f):
    # Spec25 estimator arithmetic, raw-sample adapter. Fixtures shorter than12h.
    assert f.ts[-1] - f.ts[0] < 43200
    readings = np.stack((f.move, f.still), axis=1).astype(int)
    counts = np.zeros((2, 9, 101), int)
    floor = readings[0].astype(float)
    spread = np.ones((2, 9))
    floors = np.zeros_like(readings, float)
    spreads = np.ones_like(readings, float)
    last = -float("inf")
    for i, t in enumerate(f.ts):
        for c in range(2):
            counts[c, np.arange(9), readings[i, c]] += 1
        if t - f.ts[0] >= 60 and t - last >= 5:
            for c in range(2):
                for g in range(9):
                    floor[c, g], spread[c, g] = old.hist_state(counts[c, g])
            last = t
        floors[i] = floor
        spreads[i] = spread
    return floors, spreads


def replay(f, fl, sp, with_anchor=True, hold_s=0.0, same_gate_balance=False, hold_support=None, hold_review=None, entry_only_anchor=False, anchor_factory=None):
    cfg = DetectorConfig(hold_s=hold_s)
    env = StageEnv(cfg)
    scorer = RunScorer(env, lone_gate_suppression=LoneGateSuppression(env))
    energy = EnergyFloor(env)
    anchor = anchor_factory() if anchor_factory is not None else SameGateBalanceAnchor() if same_gate_balance else MotionAnchor()
    occupied = False
    deadline = None
    deadline_start = None
    support = np.zeros(9)
    output = np.zeros(len(f.ts), bool)
    scores = np.zeros(len(f.ts))
    anchor_scores = np.zeros(len(f.ts))
    for i, t in enumerate(f.ts):
        dt = 0 if i == 0 else max(0.0, t - f.ts[i - 1])
        peaks = np.maximum(
            0,
            np.maximum(
                (f.move[i] - fl[i, 0]) / sp[i, 0], (f.still[i] - fl[i, 1]) / sp[i, 1]
            ),
        )
        alpha = 1.0 if i == 0 else 1 - np.exp(-dt / cfg.support_tau_s)
        support += alpha * (peaks - support)
        score, gates = scorer.best_run(peaks, support)
        scores[i] = score
        frame = Frame(
            ts_utc=float(t),
            ts_mono=float(t - f.ts[0]),
            move_gates=tuple(f.move[i].astype(int)),
            still_gates=tuple(f.still[i].astype(int)),
            target_distance_cm=0,
            device_occupancy=False,
        )
        ctx = SimpleNamespace(
            occupied=occupied, activity=bool(gates), frame=frame, active_gates=gates
        )
        energy.accumulate(ctx)
        anchor_result = anchor.update(
            float(t), frame.move_gates, frame.still_gates, fl[i, 1], sp[i, 1]
        )
        good = anchor_result.anchored
        hold_good = (
            hold_support.update(float(t), frame.move_gates, frame.still_gates,
                                fl[i, 1], sp[i, 1], anchor_result)
            if hold_support is not None else good
        )
        anchor_scores[i] = anchor.score
        if hold_review is not None:
            hold_review.observe(float(t), frame.still_gates)
            if hasattr(hold_review, "observe_anchor"):
                hold_review.observe_anchor(float(t), frame.move_gates, frame.still_gates,
                                           anchor_result)
        if not occupied:
            if (
                score >= cfg.enter_score
                and energy.verdict(ctx).admitted
                and (not with_anchor or good)
            ):
                occupied = True
                deadline = t + hold_s if entry_only_anchor else None
                deadline_start = t if entry_only_anchor else None
        else:
            if entry_only_anchor:
                if t >= deadline:
                    if hold_review is not None and hold_review.occupied_looking(deadline_start, float(t)):
                        deadline_start = t
                        deadline = t + hold_s
                    else:
                        occupied = False
                        deadline = None
                        deadline_start = None
            else:
                keep = hold_good if with_anchor else score >= cfg.exit_score
                if keep:
                    deadline = None
                    deadline_start = None
                elif hold_s == 0:
                    occupied = False
                    deadline = None
                    deadline_start = None
                elif deadline is None:
                    deadline = t + hold_s
                    deadline_start = t
                elif t >= deadline:
                    if hold_review is not None and hold_review.occupied_looking(deadline_start, float(t)):
                        deadline_start = t
                        deadline = t + hold_s
                    else:
                        occupied = False
                        deadline = None
                        deadline_start = None
        if not occupied and hold_support is not None and hasattr(hold_support, "reset"):
            hold_support.reset()
        if not occupied and hold_review is not None and hasattr(hold_review, "reset"):
            hold_review.reset()
        output[i] = occupied
    return output, scores, anchor_scores


def assessment(f, out):
    d = {
        "rates": {
            c: old.e.b.rate(out, old.e.b.mask(f, c)) for c in ("IN", "TW", "EMPTY")
        },
        "visits": [],
    }
    for c, a, z in f.spans:
        if c != "IN":
            continue
        ids = np.flatnonzero((f.ts >= a) & (f.ts < z))
        on = ids[out[ids]]
        end = min(
            (x for cls, x, y in f.spans if cls == "IN" and x >= z),
            default=float(f.ts[-1]) + 1e-6,
        )
        post = (f.ts >= z) & (f.ts < end)
        off = np.flatnonzero(post & ~out)
        clear = float(f.ts[off[0]]) if len(off) else None
        quiet = np.zeros(len(out), bool)
        if len(on):
            quiet = (f.ts >= f.ts[on[0]]) & (f.ts < z) & ~out
        drops = old.e.b.run_stats(quiet, f.ts, (f.ts >= a) & (f.ts < z))
        tw = old.e.b.mask(f, "TW") & post
        d["visits"].append(
            {
                "start": a,
                "entry_offset_s": float(f.ts[on[0]] - a) if len(on) else None,
                "pre_entry_positive_frames_1s": int(
                    np.sum(out & (f.ts >= a - 1) & (f.ts < a))
                ),
                "dropouts_after_detection": drops,
                "first_clear_offset_s": None if clear is None else clear - z,
                "clear_within_30s": clear is not None and clear - z <= 30,
                "later_kitchen_positive_frames": None
                if clear is None
                else int(np.sum(tw & out & (f.ts > clear))),
                "observation_end": end,
            }
        )
    return d


def main():
    result = {}
    for filename in ("labeled-walk-0915.db", "labeled-loop-0915.db"):
        f = old.e.b.new_fixture(filename)
        fl, sp = estimates(f)
        result[filename] = {}
        for enabled, hold in ((False, 0.0), (False, 20.0), (True, 0.0), (True, 20.0)):
            key = f"{'anchor' if enabled else 'score'}_hold{hold:g}"
            out, _, _ = replay(f, fl, sp, enabled, hold)
            d = assessment(f, out)
            result[filename][key] = d
        reference = old.replay_hist(f.ts, f.move, f.still, True)[0]
        assert np.array_equal(replay(f, fl, sp, True, 0.0)[0], reference)
        # Prefix causality includes independently recomputed histograms.
        from dataclasses import replace

        n = len(f.ts) - 700
        prefix = replace(f, ts=f.ts[:n], move=f.move[:n], still=f.still[:n])
        pf, ps = estimates(prefix)
        assert np.array_equal(pf, fl[:n]) and np.array_equal(ps, sp[:n])
        for enabled in (False, True):
            full = replay(f, fl, sp, enabled, 20.0)
            part = replay(prefix, pf, ps, enabled, 20.0)
            for x, y in zip(full, part):
                assert np.array_equal(x[:n], y)
    (HERE / "results.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
