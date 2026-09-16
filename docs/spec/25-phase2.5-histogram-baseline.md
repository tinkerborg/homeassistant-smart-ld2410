# 25 — Phase 2.5: Histogram Baseline Estimator

Goal: learn each gate's true noise floor and spread from the data's
distribution shape rather than its time share, so learning is correct even
when the room is occupied for most of the window — including a learning
reset performed with someone sitting in front of the sensor. Acceptance
criteria are §4.

## 1. Floor

Per gate, per channel: the floor is the dominant low mode of the energy
amplitude distribution over the baseline window — the histogram peak, not
a time quantile. An occupied room's distribution is a sharp ambient peak
with an activity tail hanging off it; the peak stays put no matter how
much of the window the tail covers, because quiet frames arrive in blocks
between movements even under continuous occupancy.

Saturation guard: until a gate has observed `mode_min_s` (default 60 s) of
samples, its mode is untrusted and the previous floor (or cold-start
behavior) stands — a freshly power-cycled channel reads saturated and
every mode estimator follows it.

## 2. Spread

Per gate: the mode-local MAD — the median absolute deviation of the
samples within `mode_band` (default ±6 energy units) of the mode, floored
by `min_mad`. A whole-window spread is inflated by the activity tail far
more than the floor is; the mode-local form measures only the quiet
population's width, which is what exceedance scoring needs.

## 3. Effect

Floors and spreads feed residual z-scores exactly as before; no detector
rule changes. The estimator replaces the windowed-quantile floor and
spread; window length, bucketing, persistence, and resize semantics are
unchanged.

## 4. Acceptance

1. Occupied-only learning: on the recorded reset-while-seated fixture,
   floor within 2 energy units of the empty-window truth within 5 minutes
   of occupied-only data at the seat gates; spread within 1 unit.
2. Empty-window agreement: on empty references, floor and spread match
   the current estimator within 1 unit at every gate, and the mode is not
   dragged by pet activity at other gates.
3. Downstream: seated still z-scores on the fixture recover against
   contaminated-learning, with no regression anywhere on the standing
   replay suite (still-presence asymmetry rule applies).
4. Cold start: time-to-learned unchanged; the saturation guard holds the
   floor untrusted only while the mode is saturated.

Measured against the recorded corpus in
`validation/25-v1-histogram-baseline.md`.
