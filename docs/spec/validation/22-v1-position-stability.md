# 22 V1 — Position-stability validation

Spec 22 §3, run against the recorded frames on 2026-09-06. Read-only replay of
a snapshot of `config/smart_ld2410/frames.db` through the shipping detector at
default `DetectorConfig`; positions sampled at 2 Hz inside every open episode.

**Verdict: FAIL on all four criteria, on every sensor. Spec 22 is shelved per
its own §3 ("if 1–3 show the estimates are unstable across the board, this spec
is shelved and the result recorded").**

## 0. Corpus

| sensor | name / room | frames | sessions | wall span (connected) | detection episodes |
| --- | --- | --- | --- | --- | --- |
| `99:CD:E0:3E:66:15` | (unnamed) | 177 651 | 10 | 73.6 h (13.2 h) | 569 |
| `D0:6E:81:D2:5D:A6` | Living Room / Kitchen | 1 871 831 | 53 | 194.6 h (53.3 h) | 237 |
| `FD:68:3B:41:6E:FF` | (unnamed) / Living Room | 1 732 611 | 51 | 85.2 h (49.1 h) | 630 |

"Connected" is frame time excluding gaps over five minutes; the BLE link drops
often enough that it is a good deal less than the wall span.

Two estimates per frame, per spec 22 §2: the device-reported target distance
(`frames.distance_cm`) and the residual-weighted centroid over elevated gates
(`centroid_gate × 0.75 m`).

## 1. The device estimate is not a signal at all

This is the finding that decides the spec, and it is prior to any variance
measurement:

| sensor | frames with `distance_cm == 0` | distinct non-zero values | most common value |
| --- | --- | --- | --- |
| `99:CD:E0:3E:66:15` | 0 % | 232 | 326 cm, on 27 % of *all* frames |
| `D0:6E:81:D2:5D:A6` | **95.2 %** | 420 | 207 cm, on 0.1 % |
| `FD:68:3B:41:6E:FF` | **67.5 %** | 483 | 105 cm, on 0.5 % |

Two distinct failures, neither recoverable:

- On the two busy sensors the device reports **no distance at all** for most
  frames — including frames where its own occupancy bit is set (it is set on
  100 % of frames on both, the permissive-threshold configuration). Within-
  episode coverage of a usable device reading is a **median of 0.00** on both
  (p75 = 0.00 and 0.15 respectively).
- On `99:CD` the channel is never zero but is **frozen**: a single value holds
  for tens of thousands of consecutive frames, and the within-episode standard
  deviation is **0.00 m at every percentile up to p90** across 560 episodes.
  A position estimate with zero variance during a walk-through is a latch, not
  a measurement.

Spec 22 §2 assumes "device-reported moving/static target distance (cm,
firmware-derived, single dominant target)" is available per frame. On this
hardware, at these settings, it is not. Everything in §3.1–§3.3 that involves
the device estimate is therefore reported below for completeness only.

## 2. §3.1 — Within-episode variance

Standard deviation of each estimate within one detection episode, in metres.

| sensor | estimate | n | p25 | median | p75 | p90 |
| --- | --- | --- | --- | --- | --- | --- |
| `99:CD` | centroid | 415 | 0.39 | **0.76** | 1.12 | 1.44 |
| `99:CD` | device | 560 | 0.00 | 0.00 | 0.00 | 0.00 |
| `D0:6E` | centroid | 226 | 0.73 | **1.03** | 1.35 | 1.61 |
| `D0:6E` | device | 30 | 0.29 | 0.40 | 0.47 | 0.69 |
| `FD:68` | centroid | 583 | 0.40 | **0.71** | 1.10 | 1.38 |
| `FD:68` | device | 213 | 0.27 | 0.43 | 0.55 | 0.73 |

Split by episode character (transit = gate span ≥ 2 and ≤ 30 s; dwell =
≥ 60 s and still-dominant), centroid standard deviation:

| sensor | transits (n) | median | p90 | dwells (n) | median | p90 |
| --- | --- | --- | --- | --- | --- | --- |
| `99:CD` | 61 | 0.93 | 1.50 | 6 | 0.62 | 0.65 |
| `D0:6E` | 9 | 0.96 | 1.81 | 6 | 0.90 | 0.94 |
| `FD:68` | 97 | 0.68 | 1.21 | 114 | 0.54 | 0.93 |

The decisive number is the **dwell** column. A stationary person is the best
case this estimator will ever see, and the centroid still moves with a
standard deviation of 0.54–0.90 m — comparable to a whole gate (0.75 m), and
between 2.7× and 4.5× the `d_margin` of 0.2 m that spec 22 §5 wants to
suppress entry on. There is no margin to work with.

## 3. §3.2 — Monotonicity across a crossing

Monotonicity is scored per episode as `|up − down| / (up + down)` over the
0.5 s-sampled series with a 5 cm deadband: 1.0 is a strictly one-way crossing,
0.0 is a series that reverses as often as it advances.

| sensor | centroid, all (median / p75) | centroid, transits (median / fraction > 0.8) |
| --- | --- | --- |
| `99:CD` | 0.14 / 0.60 | 0.33 / 0.25 |
| `D0:6E` | 0.04 / 0.17 | 0.14 / 0.00 |
| `FD:68` | 0.11 / 0.33 | 0.20 / 0.07 |

Even restricted to episodes that span two or more gates in under 30 seconds —
i.e. to walk-throughs — a clean one-way crossing is the exception: 0 %, 7 %
and 25 % of transits score above 0.8. The median transit reverses direction
nearly as often as it advances. The device estimate is no better where it
exists (medians 0.06–0.50).

## 4. §3.3 — Agreement between the two estimates

Mean absolute difference per episode, and Pearson correlation of the paired
series:

| sensor | n | \|device − centroid\| p25 / median / p75 | r (median) |
| --- | --- | --- | --- |
| `99:CD` | 415 / 62 | 1.01 / **1.15** / 1.45 m | **0.00** |
| `D0:6E` | 30 | 1.38 / **1.50** / 1.61 m | 0.35 |
| `FD:68` | 212 / 194 | 1.52 / **1.75** / 2.02 m | 0.13 |

The two estimates disagree by **1.15–1.75 m** in the median — one and a half
to two and a half gate widths — and their correlation is at best 0.35 and at
worst indistinguishable from zero. There is no regime in this corpus where the
two agree; spec 22 §3.3's "conditions under which they diverge" has the answer
"all of them". §5's ambiguity fallback ("estimates diverging → fall back to the
per-gate class") would therefore fire on essentially every episode, which makes
the whole mechanism a no-op even if the rest of it worked.

## 5. §3.4 — Distribution separation at straddled gates

Brief episodes (≤ 10 s) were classified leading / dead-end per spec 20 §3a — a
sustained-eligible episode opening within `lead_window_s` (5 s) of the brief
one's close — and the two populations' per-episode median positions compared by
histogram overlap coefficient (0.375 m bins). Spec 22 §3.4 passes a gate at
overlap < `sep_max` = 0.25.

`99:CD` produced **0** leading brief episodes at any gate and `D0:6E` produced
at most **1** per gate, so neither sensor can be tested at all. `FD:68`:

| gate | n_lead | n_dead | overlap (centroid) | overlap (device) | pass? |
| --- | --- | --- | --- | --- | --- |
| 3 | 8 | 218 | 0.680 | — | no |
| 4 | 6 | 239 | 0.431 | — | no |
| 5 | 8 | 307 | 0.578 | — | no |
| 6 | 20 | 440 | 0.629 | 0.844 | no |
| 7 | 14 | 554 | 0.617 | — | no |
| 8 | 12 | 493 | 0.702 | — | no |

**Zero gates pass, on any sensor.** The best gate in the corpus overlaps at
0.431, 1.7× the threshold; the median gate overlaps at 0.62. The device column
is almost entirely empty because a leading episode rarely coincides with a
frame carrying a device reading.

Secondary observation worth carrying forward: leading brief episodes are *rare*
(6–20 per gate over 85 hours, against 218–554 dead-end ones). Spec 20 §3a's
PORTAL rule needs `n_lead ≥ 5`, which these counts clear, but spec 22 §4 wants
to fit a per-gate split distance from them, and 6–20 samples per gate is thin
even before the overlap result rules it out.

## 6. Pass/fail against §3's four criteria

| criterion | result |
| --- | --- |
| §3.1 within-episode variance | **FAIL** — centroid σ 0.54–0.90 m during *dwells*, vs a 0.2 m `d_margin`; device estimate has zero variance (latched) or no coverage |
| §3.2 monotonicity | **FAIL** — median transit monotonicity 0.14–0.33; ≤ 25 % of transits are cleanly one-way |
| §3.3 agreement | **FAIL** — median disagreement 1.15–1.75 m, median r ≤ 0.35 |
| §3.4 separation at straddled gates | **FAIL** — 0 of 6 testable gates below `sep_max` = 0.25; 2 of 3 sensors have too few leading episodes to test |

## 7. Consequence

Per spec 22 §3, criteria 1–3 failing across the board shelves the spec. The
recorded reasons, in order of how fundamental they are:

1. **The device distance channel is unusable on this hardware/configuration.**
   Either it does not report (95 % / 68 % zeros) or it latches (zero variance).
   Spec 22 §2's premise of two independent estimates does not hold; there is
   one estimate.
2. **The surviving estimate is a gate-scale quantity.** A residual-weighted
   centroid over 0.75 m bins, smoothed by nothing, wanders ±0.5–0.9 m while its
   subject sits perfectly still. It cannot support a 0.2 m decision margin, and
   no amount of thresholding turns it into sub-gate resolution.
3. **The outcome statistics do not separate in distance anyway.** Even taking
   the centroid at face value, leading and dead-end episodes at the same gate
   occupy the same distances (overlap 0.43–0.70). Straddled gates, as spec 22
   §4 defines them, do not appear in this corpus.

Before reviving spec 22, the two things worth trying, in order: **(a)** check
whether the device's distance channel behaves differently at non-permissive
gate sensitivities — the current thresholds pin `device_occ` at 1 permanently
and may be what suppresses the distance report; **(b)** temporally smooth the
centroid (the detector already keeps a per-gate support EMA; a centroid over
`support` rather than raw peaks would cost nothing) and re-measure §3.1 before
touching anything downstream. Neither is worth doing until (a) either produces
a working second estimate or rules one out for good.
