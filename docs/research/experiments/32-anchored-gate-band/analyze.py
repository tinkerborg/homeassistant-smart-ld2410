"""Experiment-only anchored gate-band hold against the full experiment 26 stack."""

import importlib.util
import json
import sqlite3
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("stack32", HERE.parent / "26-motion-anchor-stack/replay.py")
stack = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stack)
Fixture = stack.old.e.b.data.Fixture


class GateBandHold:
    """Keep the still energy in the anchor's gate band, allowing lateral drift."""

    def __init__(self, halo=1, retention=0.4):
        self.halo = halo
        self.retention = retention
        self.mask = None
        self.reference = 0.0
        self.previous = None

    def update(self, ts, move, still, floor, spread, anchor):
        if self.previous is not None and (ts < self.previous or ts - self.previous > 0.55):
            self.mask = None
        self.previous = ts
        residual = np.maximum((np.asarray(still)[2:9] - np.asarray(floor)[2:9]) / np.asarray(spread)[2:9], 0)
        if self.mask is not None:
            strength = float(residual[self.mask].sum()) / self.reference
            if strength >= self.retention:
                return True
            self.mask = None
        # A band is born only from a motion anchor admitted by the same-gate
        # balance rule. Stillness alone cannot create or replace it.
        balanced_motion = any(
            move[g] >= 40 and move[g] / max(move[g] + still[g], 1) >= 1 / 3
            for g in range(2, 9)
        )
        if not (anchor.anchored and balanced_motion and anchor.template):
            return False
        template = np.asarray(anchor.template)
        support = template >= 0.2 * template.max()
        for _ in range(self.halo):
            support = support | np.r_[False, support[:-1]] | np.r_[support[1:], False]
        reference = float(residual[support].sum())
        if reference <= 0:
            return False
        self.mask = support
        self.reference = reference
        return True


def living_fixture():
    db = stack.ROOT / "tests/fixtures/recordings/living-room-continuous-occupancy-2026-09-16.db"
    with sqlite3.connect(f"file:{db}?mode=ro", uri=True) as con:
        sensor = con.execute("SELECT sensor_id FROM frames WHERE sensor_id LIKE '68:%' LIMIT 1").fetchone()[0]
        rows = con.execute("SELECT ts,move,still FROM frames WHERE sensor_id=? ORDER BY ts", (sensor,)).fetchall()
        a, b = con.execute("SELECT ts_start,ts_end FROM labels WHERE person=? AND room=? ORDER BY ts_start DESC LIMIT 1", ("rob", "living_room")).fetchone()
    return Fixture("living-room-continuous-occupancy-2026-09-16", sensor, np.array([r[0] for r in rows]), np.array([list(r[1]) for r in rows], float), np.array([list(r[2]) for r in rows], float), [("IN", a, b)])


def summarize(f, out):
    onsets = np.flatnonzero(out & ~np.r_[False, out[:-1]])
    in_mask = stack.old.e.b.mask(f, "IN")
    result = {
        "occupied_fraction_in": float(out[in_mask].mean()) if in_mask.any() else None,
        "onsets": [float(f.ts[i]) for i in onsets],
    }
    if f.name.startswith("living-room"):
        gaps = stack.old.e.b.run_stats(in_mask & ~out, f.ts, in_mask)
        result["vacancy_runs_while_present"] = gaps
        result["occupied_first_3min_fraction"] = float(out[(f.ts >= f.ts[0]) & (f.ts < f.ts[0] + 180)].mean())
    else:
        result["assessment"] = stack.assessment(f, out)
    if f.name == "post-deploy-0915":
        target = 1789526209.163709
        window = (f.ts >= target - 5) & (f.ts < target + 110)
        result["reported_false_event_occupied"] = bool(out[np.argmin(abs(f.ts - target))])
        result["false_window_positive_frames"] = int(out[window].sum())
        result["false_window_onsets"] = [float(f.ts[i]) for i in onsets if window[i]]
    return result


def main():
    post = stack.load("post32", HERE.parent / "28-strength-confirmation/analyze.py").post_fixture()
    fixtures = [stack.old.e.b.new_fixture(n) for n in ("labeled-walk-0915.db", "labeled-loop-0915.db")]
    fixtures += [post, living_fixture()]
    results = {}
    for f in fixtures:
        fl, sp = stack.estimates(f)
        results[f.name] = {}
        for hold in (0.0, 30.0):
            for variant, band in (("exact", None), ("band_core", GateBandHold(halo=0)),
                                  ("band_halo", GateBandHold(halo=1))):
                out, _, _ = stack.replay(f, fl, sp, True, hold, same_gate_balance=True, hold_support=band)
                results[f.name][f"{variant}_hold{hold:g}"] = summarize(f, out)
    (HERE / "results.json").write_text(json.dumps(results, indent=2))
    for name, variants in results.items():
        print(name)
        for variant, result in variants.items():
            print(variant, "IN", round(result["occupied_fraction_in"], 3) if result["occupied_fraction_in"] is not None else None,
                  "onsets", len(result["onsets"]), "false_window", result.get("false_window_positive_frames"))


if __name__ == "__main__":
    main()
