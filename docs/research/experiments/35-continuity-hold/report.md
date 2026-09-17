# Per-gate continuity as a hold signal

This is an experiment-only replay of the full stack, including same-gate
motion/still balance for new anchors. Entry is unchanged. A motion-confirmed
entry saves each gate's still-energy increase over the preceding 0.5–2.5 s.
During hold, the 20th percentile over the last 3 s measures what remained
nearly continuous at each of those gates. Its capped sum, divided by the
initial increase, is the continuity score. A low score starts or continues
the existing 30 s departure countdown; the entry reference is retained so a
later strong window can cancel that countdown. Only the sensor under test is
used for inference, with labels used for evaluation.

| Full-stack replay, 30 s hold | Exact anchor | Continuity ≥0.4 | Continuity ≥0.3 | Continuity ≥0.2 |
|---|---:|---:|---:|---:|
| Seated living room: occupied frames | 29.0% | 28.8% | 28.8% | 76.8% |
| Seated living room: longest false vacancy | 529 s | 530 s | 530 s | 225 s |
| Labeled loop: bathroom clear after exit | 36.9 s | 95.9 s | 95.9 s | 95.9 s |
| Post-deploy: bathroom clear after exit | 36.9 s | 37.8 s | 165.2 s | 167.7 s |
| Post-deploy kitchen false-event window: occupied frames | 208 | 216 | 1,150 | 1,150 |
| New fixture bathroom walk-by: occupied frames | 0 | 0 | 0 | 0 |

The rule captures the proposed steady-versus-patchy distinction, but steady
through-wall kitchen energy can also persist in the bathroom sensor after a
real bathroom exit. The threshold permissive enough to help the living room
keeps the bathroom occupied much too long. A threshold that protects the
bathroom does not improve the living room. In `labeled-walk-0915`, the first
bathroom visit has no clear before the next visit under the continuity variants.

This does not disprove temporal continuity as a useful feature; it shows this
simple relative per-gate continuity score is insufficient as the sole hold
refresher. Baselines are fixture-reestimated; the live persisted baseline was
not exported. No production code or fixture was changed.

Run `.venv/bin/python docs/research/experiments/35-continuity-hold/analyze.py`.
Full metrics are in `results.json`.
