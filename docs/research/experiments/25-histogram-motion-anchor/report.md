# Experiment 25: histogram floor/spread with motion-anchored still tracking

This bounded replay pairs exp21's causal motion anchor and still footprint
retention with the histogram mode/local-MAD estimator described in spec 25: amplitude bins of
width 2, dominant mode, mode-local MAD in a ±6 band, MAD floor 1, and a 60 s
trust guard.  The histogram state is built from each recording prefix and
refreshed every 5 seconds causally; labels
are evaluation metadata only and only bathroom gates 2..8 enter the replay.

The baseline is exp21 (`tau=15 s`, motion bar 40, retention 0.4).  The
floor-only ablation replaces the inactive EMA background with the histogram
floor but keeps raw residuals.  The floor+spread variant uses
`z_g=max(still_g-floor_g,0)/spread_g` for the anchor candidate and footprint
score.  The existing motion normalization and release behavior are unchanged.

## Results

See `results.json` for all per-visit values.  The script asserts exact exp21
default equality and causal prefix equality for both histogram variants.

## Reproduction

```text
.venv/bin/python docs/research/experiments/25-histogram-motion-anchor/analyze.py
```

## Verified outcome after implementation correction

The corrected replay, including baseline and causal-prefix checks, completed
in approximately **0.9 seconds**. Incremental integer histogram counts replace
repeated scans of growing raw-sample lists. The local MAD is centered on the
estimated mode itself. This is an experiment using the histogram estimator,
not an exact drop-in reproduction of production bucket/persistence semantics:
all observed raw samples are accumulated, with an assertion that each fixture
is shorter than the default 12-hour baseline window. Estimates refresh every
5 seconds, including during occupancy; template and spread are not frozen.
Before 60 seconds, residuals use the first frame and unit spread. These visits
occur after warmup. Missing-frame gaps discard the template before scoring.
The motion anchor remains raw motion >=40, so this pairing does not change
entry sensitivity. No thresholds were selected from labels.

| Visit | Entry, all variants | Baseline clear | Floor+spread clear |
|---|---:|---:|---:|
| Walk first | 1.693 s | .970 s | 1.078 s |
| Walk second | .016 s | .567 s | 1.185 s |
| Loop | .385 s | 6.859 s | 6.859 s |

All three variants have **zero premature dropouts after detection** and
**zero later kitchen positives after clearing** in the bounded labeled spans.
Floor-only and floor+spread produce identical occupancy outputs here. The
pairing maintains the successful retention/clear behavior within the user's
30-second release allowance, but adds no demonstrated benefit and does not
improve first entry. Timings are label-relative, not independently measured
physical latency. Only the two September 15 fixtures are validation evidence.
