# Exp21 reassessment on the trusted Sept 15 labels

This is a narrow reassessment of the original motion-anchored footprint replay
(`tau=15 s`, motion bar `40`, retention `0.4`) on only
`labeled-walk-0915.db` and `labeled-loop-0915.db`.  The existing replay is
imported unchanged.  Labels are used only for evaluation; only the bathroom
sensor enters the replay.  Older labels are treated as uncertain ground truth
and do not disqualify this reassessment.

The script first asserts exact equality with the historical exp21 default
output for both fixtures.  It then reports additional label-relative details
and descriptive raw-signal controls.  It does not select a new threshold or
make production changes.

## Default exp21 replay

| fixture / visit | detected | first detection after label | premature dropouts after first detection | first clear after exit label | post-exit behavior |
|---|---:|---:|---:|---:|---|
| walk visit 1 | 173/190 (91.1%) | 1.693 s | 0 | 0.970 s | clear; no re-trigger in 10 s |
| walk visit 2 | 231/231 (100%) | 0.016 s | 0 | 0.567 s | clear; no re-trigger in 10 s |
| loop visit | 775/779 (99.5%) | 0.385 s | 0 | 6.859 s | clear; no re-trigger in 10 s |

The fixed-run rates are 95.962% IN / 2.627% TW for the walk and 99.487% IN
/ 7.742% TW for the loop.  These are positive-frame fractions, not accuracy.
The loop retains positive evidence for 99.487% of the first 78 seconds of its
78-second visit.

There were no premature dropouts after the first detection in any trusted
visit.  The first post-exit clear is sustained in the replay: the positive
frames counted in the ten-second post-exit window occur before that clear, and
the active state does not re-trigger afterward.

## Through-wall false fractions

The walk's two labeled kitchen spans begin exactly at the visit end.  Their
release tails contain 10 and 5 positive frames respectively (the full 15
walk TW positives); there are no positive frames later in those kitchen spans
after the first sustained clear.

For the loop, the bathroom exit label is 1789514738 while the labeled kitchen
span starts at 1789514740, two seconds later.  The unlabeled two-second gap has
20/20 positives; the labeled kitchen portion before the first sustained clear
has 48 positive frames, all of its 48 frames.  The remaining labeled kitchen
frames after clear have 0 positives.  This timing difference is retained
explicitly instead of silently assigning the two-second gap to the kitchen
label.

## Descriptive raw controls

| fixture | raw motion >=40 IN / TW | still max >=40 IN / TW | still max >=60 IN / TW | still max >=80 IN / TW |
|---|---:|---:|---:|---:|
| walk | 49.881% / 0.000% | 100.000% / 51.489% | 95.962% / 9.282% | 94.537% / 1.226% |
| loop | 57.253% / 0.000% | 97.689% / 15.806% | 97.561% / 8.065% | 97.561% / 7.258% |

These comparisons are descriptive only; no threshold winner is selected.  The
label-relative offsets come from labels correlated with radar motion and must
not be presented as subsecond physical latency measurements.  The loop's
quiet retention result is a within-recording observation, not evidence of a
general person or wall signature.

## Reproduction

```text
.venv/bin/python docs/research/experiments/21-component-retention/reassessment-0915/reassess.py
```

Outputs are `results.json` and `results.txt` in this directory.  Historical
exp21 files remain unchanged.
