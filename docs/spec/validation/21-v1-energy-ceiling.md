# 21 V1 — Energy-ceiling boundary validation

Spec 21 §5, run against the recorded frames on 2026-09-07. Read-only replay of
a `sqlite3 .backup` snapshot of `config/smart_ld2410/frames.db` through the
shipping detector at default `DetectorConfig`.

**Verdict: the feature stays disabled, and is not recommended as per-sensor
opt-in on any sensor in this corpus. It is now safe — it suppresses nothing on
every recorded sensor, which is what §5.0 and §5.2 ask for — but it is also
inert: on two of the three sensors the near gates are clipped at the top of the
energy scale, so there is nothing left to fit the falloff against and no
boundary can be inferred at all. `max_gate` remains the answer for a known
through-wall band.**

## 0. Corpus

| sensor | name / room | frames | sessions | connected span |
| --- | --- | --- | --- | --- |
| `99:CD:E0:3E:66:15` | (unnamed) | 177 651 | 10 | 13.2 h |
| `D0:6E:81:D2:5D:A6` | Living Room / Kitchen | 1 924 034 | 53 | 54.7 h |
| `FD:68:3B:41:6E:FF` | (unnamed) / Living Room | 1 785 447 | 51 | 50.5 h |

## 1. What the ceiling learned

`ceil_q` is the decayed q99 of episode peak raw move energy; `e` is that value
over what the sensor's own fitted range falloff predicts for the gate (spec 21
§2.2); `n_epi` and `n_sus` are decayed at the end of the recording. A gate is
`fit` when it has `n_epi ≥ 10` and `ceil_q < ceil_sat` (95).

### `99:CD:E0:3E:66:15` — fit over gates 3-8, slope −2.28

| gate | ceil_q | e | n_epi | n_sus | in fit | dwell class |
| --- | --- | --- | --- | --- | --- | --- |
| 0 | 100 | 0.008 | 48.2 | 0.0 | clipped | bleed |
| 1 | 100 | 0.096 | 30.4 | 0.0 | clipped | unknown |
| 2 | 100 | 0.308 | 46.2 | 6.0 | clipped | in_room |
| 3 | 74 | 0.490 | 27.4 | 4.0 | yes | in_room |
| 4 | 51 | 0.598 | 28.5 | 5.0 | yes | in_room |
| 5 | 54 | 1.000 | 72.8 | 4.0 | yes | in_room |
| 6 | 16 | 0.433 | 59.0 | 5.9 | yes | in_room |
| 7 | 12 | 0.450 | 22.6 | 2.0 | yes | in_room |
| 8 | 12 | 0.598 | 28.5 | 0.0 | yes | in_room |

### `D0:6E:81:D2:5D:A6` — fit over gates 6-8, slope +1.71

| gate | ceil_q | e | n_epi | n_sus | in fit | dwell class |
| --- | --- | --- | --- | --- | --- | --- |
| 0 | 100 | 132.6 | 51.4 | 2.0 | clipped | in_room |
| 1 | 100 | 20.19 | 51.5 | 10.5 | clipped | in_room |
| 2 | 100 | 8.418 | 173.4 | 107.4 | clipped | in_room |
| 3 | 100 | 4.730 | 210.8 | 127.6 | clipped | in_room |
| 4 | 100 | 3.076 | 113.6 | 56.9 | clipped | in_room |
| 5 | 100 | 2.181 | 83.9 | 40.0 | clipped | in_room |
| 6 | 48 | 0.786 | 89.6 | 34.4 | yes | in_room |
| 7 | 78 | 1.000 | 81.4 | 26.7 | yes | in_room |
| 8 | 76 | 0.786 | 69.3 | 27.6 | yes | in_room |

### `FD:68:3B:41:6E:FF` — two fittable gates, no fit

| gate | ceil_q | e | n_epi | n_sus | in fit | dwell class |
| --- | --- | --- | --- | --- | --- | --- |
| 0 | 100 | — | 15.0 | 3.7 | clipped | in_room |
| 1 | 100 | — | 45.4 | 13.6 | clipped | in_room |
| 2 | 100 | — | 340.4 | 19.3 | clipped | in_room |
| 3 | 100 | — | 101.8 | 35.6 | clipped | in_room |
| 4 | 100 | — | 105.5 | 35.6 | clipped | in_room |
| 5 | 100 | — | 142.6 | 40.3 | clipped | in_room |
| 6 | 100 | — | 166.6 | 35.6 | clipped | in_room |
| 7 | 55 | — | 200.2 | 53.0 | yes | in_room |
| 8 | 54 | — | 124.0 | 43.3 | yes | in_room |

Two points fit any line, so nothing is published: `ceil_profile` is nine nulls
and every evaluation returns "unevaluated" rather than a verdict.

## 2. §5.0 — free-space immunity

| sensor | evaluations in the recording | candidate history | boundary published |
| --- | --- | --- | --- |
| `99:CD` | 3 | unevaluated, unevaluated, 5 | **none** |
| `D0:6E` | 6 | unevaluated ×2, then null ×4 | **none** (null confirmed) |
| `FD:68` | 4 | unevaluated ×4 | **none** |

No sensor suppresses a gate, so zero in-room gates are lost and no
still-presence is affected: the armed detector and the watching detector
produce identical output on all three recordings.

`D0:6E` is the only sensor that reaches a *confirmed* answer, and the answer is
"the whole range is in-room" — held for four consecutive daily evaluations.

`99:CD` produced a single candidate at `k` = 6 (boundary gate 5) on its last
evaluation and would need two more agreeing days to act on it. That candidate
is not obviously a wall: gate 6 carries 5.9 decayed sustained episodes, more
than any gate below it, and its compensated value is 0.433 — barely under
`ceil_drop`, with gates 7 and 8 at 0.450 and 0.598 above it. By the end of the
recording the profile no longer supports any `k` at all (the tightest is 0.598
for every `k ≥ 6`). This is the §5.3 far-couch risk in miniature: a real
dwell zone whose ceiling sits marginally under the trend.

## 3. §5.2 / §5.3 — what suppression would have cost

Nothing is suppressed, so the question is counterfactual. Pinning each sensor's
boundary from frame zero to the value the *uncompensated* profile chose on this
same corpus, and re-running with `ceiling_enabled`:

| sensor | pinned boundary | occupied s (watch → armed) | entries (watch → armed) | entries lost |
| --- | --- | --- | --- | --- |
| `99:CD` | 2 | 2 575 → 645 (**−75.0 %**) | 45 → 8 | **43** |
| `D0:6E` | 5 | 26 985 → 26 575 (−1.5 %) | 120 → 116 | 7 |
| `FD:68` | 6 | 118 885 → 113 922 (−4.2 %) | 195 → 108 | **95** |

Sustained (≥ 60 s, still-dominant) gate episodes beyond each pinned boundary —
the dwell that suppression would have refused:

| sensor | gate | sustained episodes | total dwell |
| --- | --- | --- | --- |
| `99:CD` | 3 / 4 / 5 / 6 / 7 / 8 | 1 / 5 / 17 / 12 / 3 / 4 | 0.16 / 0.33 / 0.68 / 0.56 / 0.19 / 0.12 h |
| `D0:6E` | 6 / 7 / 8 | 26 / 21 / 19 | 2.8 / 2.2 / 1.3 h |
| `FD:68` | 7 / 8 | 106 / 61 | 29.7 / 23.8 h |

Every one of those cuts is refused by the compensated rule. `FD:68`'s far band
is where people sit — 53 hours of dwell across 50 hours of connected recording,
half the sensor's entries — and it is left entirely alone. `99:CD` keeps all 45
of its entries instead of 8.

## 4. What the compensated profile says about the known walls

The two walls that motivated this feature are not visible in the ceiling on
this corpus, and the reason is the same on both sensors: **the in-room band is
clipped**.

- `FD:68` (kitchen wall): gates 0-6 all sit at `ceil_q` = 100. The only gates
  carrying a real number are 7 and 8, which are the band on the far side. There
  is no unobstructed sample to measure attenuation against, so no fit exists.
- `D0:6E`: gates 0-5 are clipped; the fit is therefore built out of gates 6, 7
  and 8 alone — the suspected through-wall band. A fit taken entirely on the
  far side of a wall makes the wall the trend, so the compensated values there
  are 0.79 / 1.00 / 0.79: no excess attenuation, by construction. The slope it
  reports is *positive* (+1.71), which is not a physical falloff at all, just
  three noisy points.

The design holds — a fit on unobstructed gates is what separates a wall from
distance — but it needs unclipped in-room evidence, and q99 of episode peak
move energy does not provide it on these installs: motion in front of a
wall-mounted LD2410 pegs the near gates at 100 routinely.

## 5. Result against spec 21 §5's gating list

| item | result |
| --- | --- |
| 0. falloff immunity: synthetic free-space profile yields null, no healthy sensor confirms a boundary below its dwell gates | **PASS** — the synthetic case is pinned in `tests/algo/test_ceiling.py`; no recorded sensor publishes a boundary, and the one candidate that appeared never confirmed |
| 1. island recordings: boundary at/below the wall gate, island dwell suppressed, real still-presence retained | **not demonstrated** — no bathroom/island sensor in this corpus, and the two sensors with a known through-wall band cannot form a fit at all |
| 2. every healthy sensor: boundary null or at a real wall, zero in-room gates suppressed | **PASS** — all three null; zero gates suppressed; the counterfactual in §3 is what the rule now refuses |
| 3. far-couch scenario not truncated | **PASS** — `FD:68` gates 7-8 (53 h of dwell, half its entries) are untouched |
| 4. ship path | remains **disabled**, and not recommended as opt-in: safe but inert on this corpus |
| 5. spec 22 V1 report from the same pass | delivered: `docs/spec/validation/22-v1-position-stability.md` |

## 6. What would make this useful

The rule is no longer wrong; it is starved. In rough order of how much they
buy:

1. **Give the ceiling headroom.** A q99 of peak move energy is pinned at 100 on
   six to seven of nine gates on two of three sensors. A lower quantile, or a
   ceiling taken from a longer-tailed statistic than the episode peak, would
   restore the dynamic range the fit needs where it needs it — the near band.
2. **Require the fit to span the candidate.** Even with more headroom, a fit
   built only from gates beyond a wall describes the wall. Refusing to infer a
   boundary at `k` unless at least two fitted gates lie below `k` would make
   `D0:6E`'s "no boundary" an explicit abstention rather than an accident.
3. **Bound the step from below.** A wall costs an order of magnitude two-way.
   `99:CD`'s candidate rested on a 0.433, one hundredth under the threshold;
   a wall would have shown 0.1 or less.

## 7. Reproducing

The replay script is not checked in (it reads a private recording). It is a
plain replay of the `frames` table through `Detector` at default config, with a
second detector whose `GateClassifier._boundary_gate` is pinned per sensor to
measure the counterfactual in §3. Nothing touches the live database: the
snapshot was taken with `sqlite3 .backup` from a read-only connection.
