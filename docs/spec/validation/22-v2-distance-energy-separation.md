# 22 V2 — Position-estimator rescue attempt and distance+energy separation

Follow-up to `22-v1-position-stability.md` (FAIL on all four §3 criteria) and
`21-v1-energy-ceiling.md` (feature safe but inert). Read-only replay of a
`sqlite3 .backup` snapshot of `config/smart_ld2410/frames.db` (same corpus as
both V1 reports — three sensors, `99:CD:E0:3E:66:15`, `D0:6E:81:D2:5D:A6`
(Living Room / Kitchen), `FD:68:3B:41:6E:FF` (bathroom, per user ground
truth)) through the shipping `Detector` at default `DetectorConfig`. Nothing
in `algo/` was changed; every number below is computed offline from detector
output and, for Q2's energy work, from the raw `frames` table directly.

**Verdicts:**

- **Q1 — position estimate: not rescued to spec 22's bar, but meaningfully
  improved.** No variant reaches the 0.2–0.3 m within-dwell target across the
  board. The best variant (a ~5 s EMA of the residual, weighted centroid)
  gets `FD:68` into that range at its lower quartile (p25 = 0.19 m, median
  0.25 m) but the other two sensors stay at 0.36–0.43 m median even with the
  same smoothing. Transit monotonicity improves dramatically with any
  multi-second smoothing (medians go from ~0.1–0.4 to 1.0, `frac > 0.8` from
  ~0.2 to 0.5–0.67) — smoothing fixes *directionality* far better than it
  fixes *precision*. Spec 22 §4's per-gate `d_split` boundary still has no
  usable estimate to fit against.
- **Q2 — distance+energy separation: energy separates, distance does not,
  and the literal stated kitchen ground-truth window turns out not to be a
  through-wall contamination case at all — the wall is doing its job there.**
  The corpus's *other* weak, long-duration, low-still-fraction episodes on
  all three sensors are what actually exercise the through-wall case, and on
  those, peak raw energy (move channel *and* still channel, combined)
  separates cleanly from genuine dwells at matched distance, with a threshold
  that loses zero of `FD:68`'s 47 candidate toilet-still episodes in this
  corpus. Distance alone does not separate (overlap coefficient 0.33–0.37,
  consistent with V1). A concrete rule is proposed in §7, not implemented.

---

## 1. Corpus and method

Same three sensors and recordings as `22-v1-position-stability.md` (`§0`
there has full frame/session/span counts). All computation goes through
`Detector.process()` at default config; nothing about the detector or its
episode segmentation was modified. `algo/baseline.py`, `algo/detector.py`,
`algo/episodes.py`, `algo/classifier.py`, `algo/types.py` were read in full
before writing any analysis code, specifically to match: the support EMA
(`support_tau_s = 1.0 s`), the episode open/close thresholds
(`s_gate_on = k·0.5 = 2.25`, `s_gate_off = k·0.25`), the detection-scope
episode's own centroid (`episodes._centroid`, support-gated, peak-weighted),
and `Episode.gate_peaks` (peak *raw move* energy per gate, by design — see
`classifier.py`'s module docstring on why the ceiling reads move, not
residual, and not still).

Local times below are `America/New_York` (the HA instance's configured time
zone); `frames.ts` is a UTC epoch, confirmed against the recording's known
span.

## 2. Q1 — position estimator variants

### 2.1 What was tried

All variants compute a residual-weighted centroid
(`Σ weight[g]·g / Σ weight[g]` over gates at/above the `s_gate_on` threshold,
in gate units, then ×0.75 m), differing only in what `weight` is:

| variant | weight |
| --- | --- |
| `raw` | per-frame peak residual (what V1 measured) |
| `support_ema1` | the detector's own support EMA, τ = 1 s (already computed every frame; "smooth over the same time-constant the detector uses") |
| `ema3` / `ema5` | an independent EMA over peak residuals, τ = 3 s / 5 s |
| `median3` / `median5` | median of the raw per-frame centroid over a trailing 3 s / 5 s window |
| `clipped` | raw peak residual, each gate's contribution capped at `3·k` (13.5) before weighting — the "clipped-peak handling" variant, meant to stop one saturated gate from dragging the centroid |

Samples are drawn at 2 Hz inside every open detection-scope episode (matching
V1 §method), by hooking `detector._episodes._detection` (the tracker's own
in-progress accumulator) directly rather than re-deriving episode boundaries
— so a variant's episode set is *exactly* V1's episode set, letting the
comparison be apples-to-apples. Episode character (`transit`: gate span ≥ 2,
duration ≤ 30 s; `dwell`: duration ≥ 60 s, `still_frac ≥ 0.5`) is read off
the same closed `Episode` V1 used.

### 2.2 Within-episode σ, dwells (metres; the decisive column per V1)

| sensor | raw | support_ema1 | ema3 | ema5 | median3 | median5 | clipped |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `99:CD` (n=6) | 1.02 | 0.57 | 0.44 | **0.36** | 1.21 | 1.31 | 1.01 |
| `D0:6E` (n=49) | 0.67 | 0.53 | 0.44 | **0.43** | 0.65 | 0.59 | 0.68 |
| `FD:68` (n=97) | 0.58 | 0.41 | 0.28 | **0.25** | 0.76 | 0.68 | 0.61 |

(medians shown; p25/p75/p90 for every variant are in
`q1_summary.json` in the analysis scratch directory)

`ema5` is the best performer everywhere, consistent with "more smoothing
helps a within-dwell estimate" — expected, since a dwell has no real motion
to track and pure smoothing only removes noise. It roughly halves σ versus
`raw` on all three sensors. `FD:68` at `ema5` reaches **p25 = 0.19 m, median
0.25 m** — inside or at the edge of spec 22's 0.2–0.3 m target. `D0:6E` and
`99:CD` do not: 0.36–0.43 m median even at the most aggressive smoothing
tried. `median3`/`median5` are *worse* than raw on two of three sensors —
a sliding median over a noisy, sparsely-supported centroid amplifies rather
than damps, because when few gates are elevated the underlying raw centroid
itself jumps between few discrete gate values and the median just picks one
of them. `clipped` is barely different from `raw`: this residual signal's
problem is not a single dominant outlier gate, it is broad multi-gate noise,
so clipping the peak does little.

**Verdict on σ: no variant reaches the target on two of three sensors. One
sensor gets close at its most favourable quartile.** This is real
improvement — σ nearly halved — but it does not clear the bar spec 22 needs
(0.2 m `d_margin`, per §5) for the two busier, longer-recorded sensors.

### 2.3 Transit monotonicity

| sensor | raw (median / frac>0.8) | ema3 | ema5 |
| --- | --- | --- | --- |
| `99:CD` (n=3-5) | 0.07 / 0.20 | 1.00 / 0.67 | 1.00 / 0.67 |
| `D0:6E` (n=16-20) | 0.43 / 0.25 | 1.00 / 0.53 | 1.00 / 0.56 |
| `FD:68` (n=27-31) | 0.25 / 0.19 | 1.00 / 0.52 | 1.00 / 0.56 |

This is the strongest result in the whole exercise: median transit
monotonicity goes from "reverses about as often as it advances" (0.07–0.43)
to a clean 1.0 with any multi-second EMA, and the fraction of transits that
are cleanly one-way (score > 0.8) roughly doubles to triples (to 0.5–0.67).
Smoothing over 3–5 s removes enough of the frame-to-frame noise that a real
walk-through reads as a walk-through. Sample counts are thin (16–31
transits per sensor, and only those with ≥ 2 post-decimation samples count
toward monotonicity) — this is qualitative confidence, not a tight interval
— but the direction and size of the effect is large enough to trust.

`support_ema1` (the detector's *existing* 1 s support EMA, free — no new
computation) gets roughly halfway there (median 0.6–0.8, frac>0.8 around
0.2–0.47): a real, no-cost improvement over the raw centroid V1 measured,
just not as strong as a dedicated 3–5 s smoother.

### 2.4 What this means for spec 22

Spec 22 §3's four criteria: §3.1 (within-dwell σ) still fails outright on
two of three sensors and only marginally clears the bar on the third; §3.2
(monotonicity) is fixed well by smoothing but was never gated on a specific
number in §3, so "much better, still not perfect" is the honest read; §3.3
(agreement between device distance and centroid) and §3.4 (straddled-gate
separation) were not re-run — V1's finding that the device channel is
unusable (0 % / 95.2 % / 67.5 % zero, or fully latched) is a hardware/config
fact unaffected by any offline smoothing of the *centroid* side, and §3.4's
finding (0 gates passed a 0.25 overlap threshold, two sensors had too few
leading episodes to test at all) is a statement about outcome populations,
not about the position estimator's precision — smoothing the estimator
does not manufacture leading episodes where V1 found six to twenty per
gate over 85 hours.

**Recommendation:** a support-style EMA in the 3–5 s range is worth carrying
forward as the position estimate wherever position is used for anything
softer than a hard boundary decision (diagnostics, `dist_est` at episode
close per spec 22 §6) — it is a strict improvement at zero new state (the
detector already runs a 1 s EMA; widening its time constant, or running a
second one at this cadence, is cheap). It is not enough on its own to revive
spec 22's boundary-suppression mechanism: §3.1 still fails on two of three
sensors, and §3.4 was never about the estimator's precision to begin with.

---

## 3. Q2 — does distance+energy separate through-wall from in-room?

### 3.1 The stated ground-truth window did not turn out to be what it was expected to be

The prompt's anchor was `FD:68` (bathroom) showing kitchen through-wall
activity 2026-09-07 ~01:47–01:55 local, peaking at ~22. The recording covers
this exactly (frames run through 01:57:24 that day, the last timestamp in
the corpus). Replaying `FD:68` through the detector for that window:

| time (local) | what happened |
| --- | --- |
| 01:46:00 – 01:48:45 | residuals near zero on every gate (`occ=False`); this stretch matches "quiet, weak, uniform" |
| 01:49:00 | occupancy flips `True` |
| 01:49:15 | **raw move [g3,g4,g5] = 30, 50, 79; residual up to 37.0** — a strong, real burst, not a weak one |
| 01:49:30 – 01:50:16 | quiet again |
| 01:50:31 / 01:50:46 | a second burst, raw move up to 40, residual up to 17.5 |
| 01:51:01 – 01:55:51 | quiet residuals, but `occ` stays `True` throughout (hysteresis holding on the two bursts) |

The two closed detection-scope episodes covering this window
(`01:48:47–01:49:46`, peak raw move 100; `01:50:20–01:53:43`, peak raw move
100, `still_frac` 0.996) are strong, real, `result=entered` episodes — not a
weak uniform kitchen signature. Cross-checking `D0:6E` (Living Room /
Kitchen, so it *should* see genuine kitchen activity strongly): it has one
detection episode overlapping this exact window,
`01:33:38–01:50:53` (17.25 min), `gate_peaks = [100,100,100,100,76,38,16,11,9]`,
`still_frac 0.94` — a strong, sustained, correctly-attributed in-room kitchen
session on the sensor that owns the kitchen. `FD:68` is **silent** (residuals
at or below zero) for the entire body of that session (01:33:38–01:48:45,
~15 of its ~17 minutes) and only shows activity in the last two minutes,
which — given its strength (peak 79–100) and timing right at the tail of
the kitchen session — reads as a real, separate, nearby presence event
(plausibly someone stepping into or near the bathroom as the kitchen
session wound down), not through-wall bleed from the kitchen itself.

**This is good news read the other way: the wall between `D0:6E`'s kitchen
and `FD:68`'s bathroom is functioning as physical isolation in this
recording — the strong kitchen session produces no elevated response
whatsoever on the other side of it for 15 of its 17 minutes.** The
recollected "~22 peak" figure does not match anything in this specific
window on `FD:68`; it most plausibly refers to gate 1's chronic idle-noise
ceiling (raw move sits at 18–26 there more or less permanently, all day,
every day, on this sensor — visible in every 30 s bucket sampled across
01:40–01:57) rather than to a discrete kitchen episode. This is flagged
plainly rather than forced to fit: the literal anchor window is not usable
as the through-wall exemplar the prompt intended.

### 3.2 The corpus's real weak-episode population, used instead

`FD:68` has 268 detection-scope episodes total over the recording. Three
non-overlapping tag groups (by data, not by the ground-truth window) carry
the analysis:

- **`pegged`** (n=61): peak raw move energy ≥ 95 somewhere in the episode.
- **`long_still_dwell`** (n=47): duration ≥ 300 s and `still_frac ≥ 0.6` —
  candidate toilet-still episodes, exactly the case the prompt's bar cares
  about (a motionless person must never be suppressed).
- **`weak_energy_candidate`** (n=42): duration ≥ 60 s and peak raw *move*
  energy ≤ 35 — candidate through-wall/ambient episodes. Several of these
  run for 30–70+ minutes at low, roughly uniform energy across 1–6 gates
  with low still-fraction (examples: 2026-09-05 23:49, 4388 s, peak 10,
  `still_frac` 0.09; 2026-09-06 01:20, 4180 s, peak 11, `still_frac` 0.12;
  2026-09-06 04:22, 3686 s, peak 12, `still_frac` 0.08) — long, faint,
  mostly-moving, never settling: the actual shape a real through-wall
  kitchen signature should have, better exemplars than the single stated
  ground-truth window turned out to be.

`D0:6E` and `99:CD` were run the same way as a cross-check (below); the main
analysis is on `FD:68` since it is the sensor the prompt anchors on.

### 3.3 Peak energy separates; distance does not

Raw *move*-channel peak energy per group, `FD:68`:

| group | n | duration_s median | peak_energy p25/median/p75 | centroid_m p25/median/p75 | still_frac median |
| --- | --- | --- | --- | --- | --- |
| `pegged` | 61 | 639 | 100 / 100 / 100 | 2.53 / 2.91 / 3.18 | 0.93 |
| `long_still_dwell` | 47 | 1236 | 97 / 100 / 100 | 2.54 / 2.91 / 3.12 | 0.96 |
| `weak_energy_candidate` | 42 | 99 | 10 / 11 / 14 | 3.34 / 4.95 / 5.70 | 0.56 |

Overlap coefficients (0.375 m centroid bins / 20-bin energy histogram, same
method V1 used for its §3.4 separation test):

| pair | peak-energy overlap | centroid-distance overlap |
| --- | --- | --- |
| `weak_energy_candidate` vs `long_still_dwell` | **0.064** | 0.326 |
| `weak_energy_candidate` vs `pegged` | **0.000** | 0.366 |

Distance overlaps at 0.33–0.37 — the same order of magnitude V1 found for
straddled-gate leading/dead-end distributions (0.43–0.70, failing V1's 0.25
bar) — confirms again that distance alone does not separate. Energy
overlaps near zero.

**The matched-distance test the prompt asks for directly:** restricting to
episodes whose centroid sits in `[2.5, 3.4] m` — squarely inside the
`long_still_dwell` group's own IQR — there are 8 `weak_energy_candidate`
episodes there (peak energy 10–33, e.g. 2026-09-04 11:33, 399 s, centroid
2.85 m, peak 19) and **zero** `long_still_dwell` episodes out at the
`weak_energy_candidate` group's typical range `[4.0, 5.5] m`. At the same
apparent distance, energy is the only thing that tells the two apart in
this data; distance carries no information at that range.

### 3.4 The trap: move-channel energy alone is not safe for still occupants

Three `long_still_dwell` episodes have *low* peak move energy (16, 16, 19 —
inside the `weak_energy_candidate` range): 2026-09-04 17:09
(637 s, `still_frac` 0.85, centroid 2.75 m), 2026-09-05 08:44 (627 s, 0.91,
5.71 m), 2026-09-04 11:33 (399 s, 0.78, 2.85 m). This is exactly the failure
mode the prompt warns about: **peak move energy is inherently low for a
genuinely motionless person**, because — as `algo/types.py`'s own
`Episode.gate_peaks` docstring says — "motion is what produces the strong
returns; the still channel barely saturates even in the same room." A rule
built on move-channel peak alone would suppress these three real,
minutes-long, still-dominant dwells.

Pulling the *still*-channel raw peak for every episode's active gates (a
direct query against `frames.still`, not something `Episode` currently
carries — `gate_peaks` is move-only by spec 21 design) fixes this. One gate
(gate 2, index 2) sits at raw still = 100 on 97.7 % of all `FD:68` frames —
a permanently-reflective fixture, not a person; it is excluded from this
computation (the shipping baseline already learns its floor at ~100 and
gives it near-zero residual, so this exclusion matches what the detector
already does in practice). With that gate excluded, combining move and
still peak (`combo = max(move_peak, still_peak)`) over each episode's own
active gates:

| group | n | combo_peak p25/median/p75 | min | max |
| --- | --- | --- | --- | --- |
| `weak_energy_candidate` | 42 | 13 / 26 / 41 | 11 | 100* |
| `long_still_dwell` | 47 | 100 / 100 / 100 | **35** | 100 |
| `pegged` | 61 | 100 / 100 / 100 | 99 | 100 |

*One `weak_energy_candidate` episode (2026-09-04 15:13, move peak 33,
`still_frac` 0.83) has `combo_peak = 100`: its move-only peak put it under
the exploratory move-only threshold, but its still-channel peak reveals it
is actually a real, quiet presence event, not kitchen bleed — a second
demonstration of why move-only is not safe, this time on the "candidate
weak episode" side.

At the low end, several nominally-weak episodes with elevated still_frac
(0.4–0.93) and combo_peak in the 35–78 range are almost certainly real,
lower-intensity in-room presence (someone off-axis, or seated further from
the sensor) rather than through-wall bleed — the `weak_energy_candidate` tag
here is a coarse, move-only heuristic, not ground truth, and the group is
not homogeneous. This 35–78 zone is a genuine grey area in this corpus: the
combo-peak feature alone cannot cleanly tell "quiet real occupant" from
"stronger bleed" inside it, and no attempt is made here to over-fit a
separator into it.

### 3.5 What a threshold would actually cost, sweeping it against real cost

Sweeping a `combo_peak` suppression threshold against `FD:68`'s 47
`long_still_dwell` and 61 `pegged` episodes (the ones a decision rule must
never lose) and 42 `weak_energy_candidate` episodes (the ones it is meant to
catch):

| threshold | weak suppressed | still-dwells wrongly suppressed | pegged wrongly suppressed |
| --- | --- | --- | --- |
| combo < 20 | 14/42 (33%) | 0/47 | 0/61 |
| combo < 25 | 19/42 (45%) | 0/47 | 0/61 |
| **combo < 30** | **24/42 (57%)** | **0/47** | **0/61** |
| combo < 35 | 27/42 (64%) | 0/47 | 0/61 |
| combo < 40 | 31/42 (74%) | **1/47** (the 35-combo episode) | 0/61 |

`combo < 35` is the exact floor observed in this corpus: it catches 64 % of
weak candidates while losing zero real dwells; `combo < 40` starts costing a
real still-dwell. **`combo < 30` is the recommended operating point** —
same zero real-dwell cost, a comfortable 5-point margin below the observed
floor, and still catches more than half the weak population; it should be
treated as a starting point to re-derive as more recordings accumulate, not
a number to trust to the last integer from 47 samples.

### 3.6 Cross-sensor check (`D0:6E`, `99:CD`)

Move-only peak energy, same three tag groups, no still-channel rework (time
did not allow the full still-channel treatment on all three; this is a
lighter secondary check):

| sensor | group | n | peak_energy median | centroid_m median |
| --- | --- | --- | --- | --- |
| `D0:6E` | weak_energy_candidate | 42 | 11 | 3.0 |
| `D0:6E` | long_still_dwell | 21 | 100 | 2.5 |
| `D0:6E` | pegged | 33 | 100 | 2.7 |
| `99:CD` | weak_energy_candidate | 19 | 21 | 3.3 |
| `99:CD` | long_still_dwell | — | (none in corpus) | — |
| `99:CD` | pegged | 7 | 100 | 2.6 |

Same shape on `D0:6E`: weak-candidate peak energy an order of magnitude
below real dwells, at overlapping centroid distance (2.7–3.8 m weak vs
2.3–2.6 m dwell/pegged — materially overlapping ranges). `99:CD` has no
`long_still_dwell` episodes at all in its shorter (13.2 h connected)
recording, so its move-vs-still trap cannot be checked there; its weak-group
separation from `pegged` (21 vs 100 median) is consistent with the other two
sensors.

---

## 4. Reproducing

Analysis scripts (not checked in; scratch only, read a private recording):

- `q1_position.py` — the seven position-estimator variants, σ and
  monotonicity per episode, per sensor.
- `q2_episodes.py` — detection-scope episode characterisation (energy,
  centroid, still fraction) for all three sensors, plus the kitchen-window
  and long-still-dwell tagging.
- `q2_still.py` — adds still-channel peak energy per episode from raw
  `frames.still` (not something `Episode.gate_peaks` carries).
- `q2_detail.py` — per-frame residual/occupancy trace through the stated
  kitchen ground-truth window, used for §3.1.

All read `frames.db.backup`/`study.db`, a `sqlite3 .backup` snapshot taken
from a read-only connection; nothing touches the live database, and no
`algo/` or spec file was modified.

## 5. Proposed decision rule (not implemented)

For a Q2-style energy-ceiling-style suppression at a gate/episode level, if
this line of work is picked back up:

1. Compute `combo_peak` per candidate episode: `max` of raw peak *move* and
   raw peak *still* energy over the episode's own active gates, excluding
   any gate whose baseline floor sits within, say, 5 of the scale's ceiling
   on either channel for ≥ 95 % of recent frames (the stuck-fixture
   exclusion `§3.4` needed for `FD:68` gate 2; this generalises the
   principle the baseline's own quantile floor already applies, made
   explicit for this feature).
2. Suppress only when `combo_peak < 30` (per-sensor, decayed like spec 21's
   `ceil_bins`, not a fixed constant across installs — `99:CD`'s
   `weak_energy_candidate` group runs to a median of 21, noticeably higher
   than `FD:68`'s 11, so a single global constant would either miss `99:CD`'s
   weak episodes or risk `FD:68`'s margin).
3. Never suppress on distance or gate index alone (confirmed again here,
   consistent with `22-v1`): overlap coefficients of 0.33–0.37 mean a
   distance-only or gate-only rule would be wrong roughly a third of the
   time at the exact ranges that matter.
4. Treat the 35–78 `combo_peak` band (§3.4) as an explicit no-decision zone:
   fall back to whatever the existing dwell classifier / energy ceiling
   (spec 20 / spec 21) would have done, the same "ambiguity → fall back"
   principle spec 22 §5 already specifies for diverging position estimates.

This is a proposal derived from one recording on three sensors (97 dwell
episodes on the busiest one) — not a spec change, and not validated the way
spec 21's `boundary_confirm_days` mechanism (decay, multi-day confirmation,
deferred retreat under an open episode) would require before shipping
anything that suppresses real presence.
