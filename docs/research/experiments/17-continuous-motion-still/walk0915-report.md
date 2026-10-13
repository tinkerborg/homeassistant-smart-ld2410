# Held-out validation: `labeled-walk-0915.db`

**Status: complete — frozen evaluation only.** This report applies the
experiment-17 feature definitions and normalized ridge model trained on the
original bathroom fixtures. The new recording was not used for fitting,
feature selection, sign selection, or threshold selection.

## Scope and labels

The file contains five sensors. This evaluation uses only the downstairs
bathroom sensor `D0:6E:81:D2:5D:A6`, identified by the recording README and
the expected bathroom event. The kitchen sensor and the other sensors are not
inputs to the model; the per-person labels define evaluation targets only.

Within the explicitly tracked scope where the wife is in the kitchen
(18:50:40–18:52:20), the label table yields these conservative bathroom
states:

| State | Local interval | Duration |
|---|---|---:|
| TW | 18:50:40–18:50:52 | 12 s |
| IN | 18:50:52–18:51:11 | 19 s |
| TW | 18:51:11–18:51:47 | 36 s |
| IN | 18:51:48–18:52:11 | 23 s |
| TW | 18:52:11–18:52:20 | 9 s |

`IN` means Rob is explicitly labeled in the bathroom. `TW` means the wife is
explicitly in the kitchen while Rob is explicitly elsewhere; the bathroom is
treated as the negative target for this single-sensor evaluation. No bathroom
empty state is inferred from missing labels, and the one-second unlabeled gap
before the second visit is excluded. Both bathroom visits overlap the wife's
kitchen activity, so they test the requested local-positive/BOTH condition.

The table is narrative/raw-trace ground truth rather than an independent
instrumented occupancy reference. The README's prose also describes a
both-at-the-stove interval that overlaps the labeled room table differently;
this evaluation follows the explicit interval table and does not claim a
separate stove sublabel.

## Strict within-state result

All history must be inside one state span. The frozen training set contained
5,802 old-fixture windows at 10 s and 5,517 at 30 s.

At 10 s, the held-out recording produced 50 strict windows: 22 IN and 28 TW.
All three frozen models scored AUC 1.000:

| Model | AUC |
|---|---:|
| Baseline level/profile/variability features | 1.000 |
| + rolling level correlations | 1.000 |
| + rolling first-difference correlations | 1.000 |

The perfect score is already present in the baseline, so it is not evidence
that correlations add anything. Per-state frozen level-model score ranges
were:

| State span | Windows | Baseline | Level correlation | First difference |
|---|---:|---:|---:|---:|
| TW, 12 s | 2 | 0.422–0.453 | 0.336–0.442 | 0.427–0.443 |
| IN, 19 s | 9 | 1.058–1.100 | 0.989–1.122 | 1.065–1.106 |
| TW, 36 s | 26 | 0.062–0.497 | 0.018–0.465 | 0.085–0.521 |
| IN, 23 s | 13 | 0.897–1.079 | 0.859–1.063 | 0.878–1.093 |
| TW, 9 s | 0 | — | — | — |

There are no strict 30-second IN windows because both bathroom visits are
shorter than 30 seconds. The strict 30-second output therefore contains six
TW windows and no positive class; no AUC is reported.

## Optional all-timeline diagnostic

Using the same frozen 1 Hz features over the known-label scope, windows whose
history crossed a truth boundary were separated from clean windows. This is a
latency diagnostic, not a strict occupancy result:

| Window | Known anchors | Clean | Transition-straddling | Baseline AUC | Level AUC | First-difference AUC |
|---:|---:|---:|---:|---:|---:|---:|
| 10 s | 99 | 50 | 49 | 0.860 | 0.877 | 0.856 |
| 30 s | 99 | 6 | 93 | 0.489 | 0.501 | 0.470 |

## Verdict

The frozen model handled both short bathroom visits cleanly in this recording,
but the baseline already did so perfectly at 10 seconds. This held-out file
does not show an incremental benefit from the continuous correlation features.
The 30-second strict test has no positive windows, so it cannot test a 30 s
occupancy decision on these visits.

Reproduction:

```sh
TZ=America/New_York ../../../../.venv/bin/python validate_walk0915.py > walk0915-results.txt 2>&1
```
