# 23. Footprint shape similarity versus strength

## Question

Can normalized cross-gate footprint shape retain a quiet bathroom occupant as
the amplitude falls, while rejecting a remaining kitchen footprint?  This
isolates shape from strength with a matched amplitude-only control.

## Method

The replay uses only bathroom-sensor gates 2--8.  It keeps experiment 21's
causal background (`tau=15 s`), motion bar 40, candidate initialization, best
candidate replacement, and gap reset.  The template is frozen while a
footprint exists.  Unlike experiment 21, the shape and amplitude-only variants
retain that template after a failed frame, so later low-amplitude frames are
actually evaluated; only a recording gap clears it.

The shape score is cosine similarity between the current positive still excess
and the motion-anchored template.  A fixed residual L2 activity guard is
required before normalization, preventing a near-zero noise vector from
becoming a perfect shape match.  The descriptive grid was fixed in advance:
cosine thresholds 0.75/0.90 and activity guards 1/5 raw residual units.  The
amplitude-only control uses residual/template L2 ratio 0.4 with guard 1.  The
experiment 21 projection is the baseline.  There is no supervised learning,
label-tuned winner, timer, peak hold, or kitchen data.

## Result

Baseline equivalence and causal prefix checks passed.  Results below are
percent positive frames; `IN` missed is 100 minus the displayed `IN` rate.

| configuration | Sept 15 loop IN / TW | Sept 15 walk IN / TW | older toilet IN / TW | through-wall morning TW |
|---|---:|---:|---:|---:|
| experiment 21 projection | 99.49 / 7.74 | 95.96 / 2.63 | 47.49 / 8.04 | 14.14 |
| amplitude-only, .4 / guard 1 | 99.49 / 8.06 | 95.96 / 18.04 | 61.30 / 74.79 | 19.62 |
| shape .75 / guard 1 | 99.49 / 77.26 | 95.96 / 44.48 | 57.27 / 41.30 | 33.76 |
| shape .90 / guard 1 | 95.25 / 15.65 | 92.64 / 7.36 | 43.57 / 7.26 | 29.09 |
| shape .75 / guard 5 | 99.49 / 70.97 | 95.96 / 41.16 | 56.55 / 41.30 | 26.21 |
| shape .90 / guard 5 | 95.25 / 13.55 | 92.64 / 7.36 | 43.13 / 7.26 | 25.65 |

The higher similarity threshold reduces kitchen false positives in the Sept 15
walk relative to the permissive shape threshold, but it also drops more
bathroom frames: IN missed rises from 4.04% at baseline to 7.36% on the walk
and 56.43% on the older toilet visit.  The stronger activity guard removes
some empty/noise positives and gives only a modest through-wall improvement;
it does not make the normalized shape a wall discriminator.  The amplitude-
only control is clearly worse on the older and through-wall controls, showing
that retaining a template alone is not useful without spatial arrangement.

For the simultaneous walk, the shape `.90/5` visits have 15.79% and 0.43%
within-label missed frames, with label-relative first positive timings of
1.74 s and 0.12 s.  The baseline has 8.95% and 0% missed, with 1.69 s and
0.016 s first positives.  These timings use radar-derived labels and are not
independent physical latency measurements.  Some first-negative-after-exit
values are absent because the retained shape remains positive through the
10-second post-label window; label-relative exits are therefore only
diagnostic.

## Interpretation

The hypothesis is not supported by this bounded replay.  Normalized shape
similarity can evaluate fading frames, but kitchen activity often has a
similar gate arrangement after template capture, so normalization trades
amplitude sensitivity for false holds.  A guard prevents the mathematical
zero-vector failure mode, yet choosing it high enough to suppress bleed also
removes quiet bathroom evidence.  Same-gate mixtures, processed-energy
clipping, and circular motion-anchored template tracking mean a matching
shape is not proof of a physical wall or person.

No production files were changed.

## Reproduction

```text
.venv/bin/python docs/research/experiments/23-footprint-shape/analyze.py
```

