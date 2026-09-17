"""Diagnose living-room anchor loss: baseline drift versus footprint change."""

import importlib.util
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("experiment33", HERE.parent / "33-entry-change-hold/analyze.py")
e = importlib.util.module_from_spec(spec)
spec.loader.exec_module(e)
s = e.stack


def main():
    f, _, (_, _, _, entry) = e.new_recording()
    fl, sp = s.estimates(f)
    entry_i = int(np.searchsorted(f.ts, entry, side="left"))
    frozen_fl = fl.copy()
    frozen_sp = sp.copy()
    still_frozen_fl = fl.copy()
    frozen_fl[entry_i:] = fl[entry_i - 1]
    frozen_sp[entry_i:] = sp[entry_i - 1]
    still_frozen_fl[entry_i:, 1] = fl[entry_i - 1, 1]
    empty_mask = (f.ts >= 1789573130) & (f.ts < 1789573210)
    empty_still = np.median(f.still[empty_mask], axis=0)
    empty_corrected_fl = fl.copy()
    empty_corrected_fl[entry_i:, 1] = empty_still
    in_mask = s.old.e.b.mask(f, "IN")
    variants = {}
    for name, floors, spreads in (
        ("normal", fl, sp),
        ("freeze_still_floor", still_frozen_fl, sp),
        ("freeze_all_floor", frozen_fl, sp),
        ("freeze_spread", fl, frozen_sp),
        ("freeze_floor_and_spread", frozen_fl, frozen_sp),
        ("replace_still_floor_with_empty_interval", empty_corrected_fl, sp),
    ):
        out, _, _ = s.replay(f, floors, spreads, True, 30.0, same_gate_balance=True)
        variants[name] = {
            "occupied_fraction_after_entry": float(out[in_mask].mean()),
            "longest_false_vacancy_s": s.old.e.b.run_stats(in_mask & ~out, f.ts, in_mask)["longest_span_s"],
        }

    anchor = s.SameGateBalanceAnchor()
    first_loss = None
    first_live = None
    prev_supported = False
    snapshot = {}
    for i, t in enumerate(f.ts):
        old_template = anchor.template
        result = anchor.update(t, f.move[i], f.still[i], fl[i, 1], sp[i, 1])
        if t >= entry and result.anchored and first_live is None:
            first_live = i
        if first_live is not None and i > first_live and prev_supported and not result.anchored and first_loss is None:
            first_loss = i
            if old_template is not None:
                template = np.asarray(old_template)
                normal_residual = np.maximum((f.still[i, 2:9] - fl[i, 1, 2:9]) / sp[i, 1, 2:9], 0)
                fixed_floor_residual = np.maximum((f.still[i, 2:9] - fl[entry_i - 1, 1, 2:9]) / sp[i, 1, 2:9], 0)
                denom = float(np.dot(template, template))
                snapshot = {
                    "first_loss_ts": float(t),
                    "seconds_after_entry": float(t - entry),
                    "reported_anchor_score_at_loss": float(result.score),
                    "counterfactual_score_with_preentry_floor": float(np.dot(fixed_floor_residual, template) / denom),
                    "template_gates_2_8": template.tolist(),
                    "still_gates_2_8_at_loss": f.still[i, 2:9].tolist(),
                    "floor_gates_2_8_preentry": fl[entry_i - 1, 1, 2:9].tolist(),
                    "floor_gates_2_8_at_loss": fl[i, 1, 2:9].tolist(),
                    "residual_gates_2_8_at_loss": normal_residual.tolist(),
                    "cosine_at_loss": float(np.dot(normal_residual, template) / (np.linalg.norm(normal_residual) * np.linalg.norm(template))) if np.linalg.norm(normal_residual) else None,
                    "amplitude_ratio_at_loss": float(np.linalg.norm(normal_residual) / np.linalg.norm(template)),
                }
        prev_supported = result.anchored
    result = {"fixture": f.name, "sensor": f.sensor, "entry_ts": entry,
              "freeze_at_ts": float(f.ts[entry_i - 1]), "variants": variants,
              "empty_interval_median_still_gates_2_8": empty_still[2:9].tolist(),
              "first_supported_ts": float(f.ts[first_live]) if first_live is not None else None,
              "first_loss": snapshot,
              "limitation": "Replay re-estimates histogram state; deployed persisted baseline and live anchor score were not exported."}
    (HERE / "results.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
