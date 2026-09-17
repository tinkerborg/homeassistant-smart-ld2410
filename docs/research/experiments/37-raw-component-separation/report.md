# Independent raw-gate source-separation probe

This experiment asks whether a single sensor's gates can be decomposed into
distinct activity components before integrating anything into the detector
stack. It uses still and motion gates 2–8 from each sensor. Each gate is
background-subtracted using its own fifth percentile; nonnegative matrix
factorization (NMF) then fits one to three additive components. A second
two-component fit normalizes each frame's overall strength to emphasize gate
*shape*. Multiple fixed random starts are tried and the lowest reconstruction
error is kept. No labels or other sensors enter either fit.

The fit uses the **entire recording**, including future frames, so this is a
noncausal feasibility probe. At each raw same-gate-balanced motion event, the
component that increases most over the next three seconds is selected for
assessment. Labels identify which event and intervals to report, not which
component to fit or select. Entry latency is not tested here; the production
stack and hold mechanism are not replayed.

| Shape-normalized two-component fit | Person component dominant while truly in room | Same component dominant first 30 s after bathroom exit |
|---|---:|---:|
| Bathroom, labeled walk visit 1 | 100% | **82.7%** |
| Bathroom, labeled walk visit 2 | 100% | **57.3%** |
| Bathroom, solo loop | 99.6% | **87.0%** |
| Replacement living room, seated period | **97.8%** | — |

The living-room component has at most a 5.2 s contiguous loss during the
seated period in this offline decomposition, and its activation distinguishes
seated versus the fixture's empty interval with AUC 0.998. This shows the raw
recording contains a strong stable shape that the current exact anchor loses.
It does **not** establish a deployable causal tracker, because the fit saw the
whole recording and its motion-seeded component choice uses up to three
seconds after entry.

The bathroom result fails the critical departure test: the same extracted
component frequently remains dominant when the person has left and kitchen
activity continues through the wall. Using raw rather than shape-normalized
energy makes the additive components mostly reflect bathroom amplitude; it
does not create a clean independent kitchen source. A single raw component's
IN-versus-TW AUC is 0.983/0.984 on the two bathroom fixtures, but that
aggregate ranking hides the after-exit overlap and is essentially an energy
discriminator, not source separation.

Conclusion: simple linear additive source separation helps represent seated
living-room occupancy, but cannot independently solve bathroom release on
these fixtures. This does not rule out more expressive temporal or nonlinear
models. No production code or fixture changed.

Run `.venv/bin/python docs/research/experiments/37-raw-component-separation/analyze.py`.
All factor weights, scores, and episode metrics are in `results.json`.
