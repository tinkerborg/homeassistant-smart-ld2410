# Experiment 17: continuous motion–still relationships

**Status: done — INCONCLUSIVE, NO ROBUST GAIN SHOWN.**

## Question

Can continuous rolling relationships between the move and still streams
distinguish bathroom `IN` from through-wall `TW` activity, without selecting
motion events or using entry/exit transitions?

## Method

This uses the bathroom recordings from experiment 15 only. For each labeled
span, the script evaluates every one-second anchor whose entire history is
inside that span. It uses 10-second and 30-second causal windows. One-second
anchors overlap and are therefore descriptive windows, not independent
trials. A 30-second-step rerun provides a sparse, non-overlapping sensitivity
check, with the caveat that the training sample size also changes.

For each window, fixed correlations compare move gate histories with still
gate histories at lags −5, −2, −1, −0.5, 0, 0.5, 1, 2, and 5 seconds. Both
directions are past-only at the decision timestamp. Features are predefined
aggregates over still targets 2–8: median and maximum absolute same-gate and
adjacent-gate correlations. Correlation move sources span gates 1–8, including
move gate 1 paired with still gate 2; the baseline also includes move gate 0.
The same aggregates are computed after
first differences to reduce sensitivity to slow level drift. Constant series produce
a defined correlation of zero. No quiet/motion condition or event peak is
used.

The baseline includes same-window move and still level, per-gate means and
standard deviations, saturation, spatial centroid, temporal variability, and
lag-1 autocorrelation. This is a stronger control for the possibility that a
correlation feature is only identifying a louder, more variable, or
differently located window. Still gates 0–1 are excluded because they are
structurally zero in these recordings. Windows with any timestamp
gap over 0.55 s, or incomplete endpoints, are rejected. Interpolation is
restricted to the causal window's frames.

Models are regularized linear probes: 46 baseline features and 36 features in
each correlation family. The primary evaluation holds out whole fixtures and
freezes the model's training orientation. No frame-level random split or
significance calculation treats overlapping windows as independent. The small
number of labeled sessions relative to this feature count is a material
limitation. The ridge penalty scales with training sample count (fixed
per-sample alpha 2), so anchor spacing does not change its effective strength.

## Results

The one-second-anchor run produced 5,802 10-second windows and 5,517
30-second windows. The two held-out fixtures containing both classes were
`labeled-sessions-0909-d06e` (the close stove/island case plus toilet spans)
and `stove-case-0913-d06e`.

Scores are AUC (0.5 is chance ranking; 1 is perfect ranking), not accuracy.

| Window | Held-out fixture | Baseline | + level correlations | + first-difference correlations |
|---:|---|---:|---:|---:|
| 10 s | labeled-sessions | 0.439 | 0.455 | 0.436 |
| 10 s | stove-case | 0.804 | 0.806 | 0.805 |
| 30 s | labeled-sessions | 0.550 | 0.617 | 0.565 |
| 30 s | stove-case | 0.742 | 0.724 | 0.732 |

The explicit late stove/island interval versus **all** labeled toilet spans
excludes the remaining hallway windows at 10 s and matches the full fixture
at 30 s: 490 windows at 10 s (402 IN, 88 TW) and 391 at 30 s (343 IN,
48 TW). The corresponding AUCs were:

| Window | Baseline | + level correlations | + first-difference correlations |
|---:|---:|---:|---:|
| 10 s | 0.449 | 0.465 | 0.445 |
| 30 s | 0.550 | 0.617 | 0.565 |

The sparse 30-second-step sensitivity run had only 15 hard-case windows (12
IN, 3 TW): baseline 0.472, level correlations 0.528, and first-difference
correlations 0.500. On the stove-case holdout, the same run gave 0.188,
0.176, and 0.186. The much smaller training set and tiny held-out class make
this a sensitivity check, not a significance test.

## Verdict

The continuous formulation is a better test of the original idea than
experiment 16, but these fixed rolling correlation features do not provide a
reliable gain after controlling for per-gate level and variability.
Ten-second features are effectively at the stronger baseline. Thirty-second
features improve the labeled-sessions holdout by 0.067 for level correlations
while decreasing the stove-case holdout by 0.018. The sparse sensitivity run
is too small to resolve the difference.

No shuffled-alignment control or nonlinear model was evaluated. Baseline
adjustment is not a controlled physical comparison of matched people and
positions on opposite sides of the wall. The result is therefore inconclusive
about whether wall-specific coupling exists.

This bounds the result to the tested rolling Pearson aggregates, lags, and
window lengths. It does not rule out every possible temporal model. It does
mean that adding lagged correlation thresholds to the current single-sensor
logic is not justified by these recordings.

Reproduction:

```sh
TZ=America/New_York ../../../../.venv/bin/python analyze.py > results_step1.txt 2>&1
EXP17_STEP=30 TZ=America/New_York ../../../../.venv/bin/python analyze.py > results_step30.txt 2>&1
```
