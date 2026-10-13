# 22. Footprint retention with hysteresis

## Question

Does adding separate entry and exit retention fractions improve the causal
motion-anchored still-footprint prototype from experiment 21?

## Method

This is a bounded replay of every experiment 21 fixture: the two Sept 15
labeled recordings and the five older controls. It uses only bathroom sensor
gates 2--8, causal background tracking with `tau=15 s`, motion threshold 40,
no departure timer, no signed retention, and no ML. Labels evaluate the output
after replay; they are not independent subsecond truth. Older label spans can
also be conservatively trimmed.

The baseline is `on=0.4, off=0.4`. The illustrative hysteresis setting is
`on=0.7, off=0.3`; matched controls are `on=0.3, off=0.3` and
`on=0.7, off=0.4`. When the stored footprint is inactive, the on threshold is
used; while active, the off threshold is used. A footprint is discarded when
the applicable threshold is missed, preserving experiment 21's behavior for
single-threshold controls.

## Result

The requested exactness and causality checks passed. The `.4/.4` replay is
exactly equal to experiment 21 for every fixture, including state, score, and
residual arrays. Every configuration also passes a prefix replay check.

| configuration | Sept 15 loop IN / TW | Sept 15 walk IN / TW | Sept 9 sessions IN | bathroom visit IN | stove IN / TW |
|---|---:|---:|---:|---:|---:|
| `.4/.4` baseline | 99.49% / 7.74% | 95.96% / 2.63% | 47.49% | 49.63% | 79.21% / 9.07% |
| `.7/.3` hysteresis | 99.49% / 8.39% | 95.96% / 4.38% | 50.44% | 49.94% | 79.46% / 11.15% |
| `.3/.3` control | 99.49% / 8.39% | 95.96% / 4.38% | 50.44% | 49.94% | 79.46% / 11.15% |
| `.7/.4` control | 99.49% / 7.74% | 95.96% / 2.63% | 47.49% | 49.63% | 79.21% / 9.07% |

`IN` is the positive fraction during label-relative bathroom spans; `TW` is
the positive fraction during kitchen/through-wall spans. A missing rate is the
within-visit fraction of frames that are not positive. The full per-fixture
rates, dropout runs, longest dropouts, and label-relative entry/exit timings
are in `results.json` and `results.txt`.

On the Sept 15 walk, the two labeled visits keep the same entry timings under
all settings: 1.69 s and 0.016 s. Lowering the off threshold from .4 to .3
lengthens the first-negative-after-exit timings from 0.97/0.57 s to 1.49/1.08
s. On the loop, the exit timing changes from 6.86 s to 7.27 s. These are label-
relative measurements, not independent physical latency.

The older controls remain poor: the Sept 9 long visit still has 53.10%
missing bathroom frames with `.7/.3`, and the separate bathroom visit has
50.06% missing. Through-wall false fractions rise on every control with
available TW spans under `.7/.3` (for example, 2.63% to 4.38% on the walk and
9.07% to 11.15% on the stove case). Thus the illustrative hysteresis setting
does not improve the tested tradeoff.

## Mathematical interpretation

For nonnegative residual `r` and motion weights in `[0,1]`, initialization is
`h = r * (M/max(M))`. Therefore
`dot(r,h)/dot(h,h) >= 1` whenever this candidate is nonzero: each weighted
component of `r` is at least the corresponding component of `h`. Thresholds
at or below 1 are automatically satisfied on initialization. This is why
`.7/.4` matches `.4/.4`, and `.7/.3` matches `.3/.3`: in this prototype,
hysteresis only lowers the off threshold and does not create genuine entry
selectivity. This experiment records that limitation rather than redesigning
the initialization to conceal it.

No production files were changed.

## Reproduction

```text
.venv/bin/python docs/research/experiments/22-footprint-hysteresis/analyze.py
```
