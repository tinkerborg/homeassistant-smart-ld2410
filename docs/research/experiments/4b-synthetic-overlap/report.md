# Experiment 4b: synthetic overlap (bathroom visit + kitchen bleed)

Data: confirmed genuine bathroom visit 22:04:01-22:06:43 (fixture
`bathroom-visit-2204-d06e.db`) superimposed frame-by-frame on the 05:11
kitchen-bleed block from `throughwall-morning-d06e.db`, two mixes:
max(bath, kitchen) and min(100, bath+kitchen). Both windows exactly 7200
frames, 1:1 index alignment, shared real 6h warm-up (15:58-21:58) so
baselines and move_ceiling (100.0 → bar 55.0) are identical and genuine.
Script: mix.py (runs the real shipped Detector on the synthetic frames,
plus lead.py and the acc3 retention statistic).

Method caveat: max() and clipped-sum are logic-path approximations; LD2410
per-gate energies are not additive across scatterers, so amplitudes are
fiction — only rule behavior is informative.

## Verdict

**One rule survives cleanly: the leading edge. Arrival gating and the
retention statistic do not, and the wife-at-stove departure hole
reproduces — hard on the additive mix, partially on the max mix.**

Most important result came before the mix: **the kitchen-only control
latches shipped occupancy on its own at 21:58:50 for 541s** with the
bathroom empty — the same false-entry mode as the shipped 05:11:49 event.
In both synthetic streams the genuine 22:04 arrival isn't an entry at all;
occupancy was already on six minutes early.

## Per question

**1. Arrival gating — survives but is worthless here.** The genuine
walk-in clears easily (max move 100, 134/160 frames over the bar). But the
kitchen control also clears it — one frame at 58 ≥ 55 in the same 90s
window. With min_frames=1 the rule is a coin flip against through-wall
bleed at this bar.

**2. Leading edge — survives.** Kitchen contributes nothing at gates 0-1
move; the bathroom occupant's near-gate approach punches through the
overlay intact.

| stream | min suppressed lead, 22:03:00-22:04:30 | histogram |
|---|---|---|
| bath (control) | **0** | g0:41 g1:29 g2:227 g3:23 g4:5 g5:1 |
| kitchen (control) | **2** | g2:331 g3:103 g4:10 |
| MAX (synth) | **0** | g0:41 g1:29 g2:385 g3:73 g4:5 g5:1 |
| SUM (synth) | **0** | g0:100 g1:186 g2:546 g3:59 g4:2 g5:1 g6:3 g8:3 |

Gate-0/1 frame counts in MAX are identical to the bath control (41/29) —
the kitchen overlay adds nothing there and removes nothing.

**3. Retention through the visit — holds, but for the wrong reason.**
Elevated at gates 1-4 across 22:04-22:06 in both synthetics (300 → 105).
Also elevated in the kitchen-only control, so "elevated" is not evidence
of a bathroom occupant.

**4. The departure hole — reproduces.** Per-minute at the occupancy's own
gates 1-4 (`retain` = median max stat/floor, `occ%` = frames occupied):

| min | bath ctrl | kitchen ctrl | MAX | SUM |
|---|---|---|---|---|
| 22:04 | 522 / 98% | 18 / 100% | 302 / 100% | 301 / 100% |
| 22:05 | 188 / 100% | 8 / 100% | 142 / 100% | 114 / 100% |
| 22:06 ← depart | 189 / 72% | 73 / 100% | 159 / 100% | 106 / 100% |
| 22:07 | 112 / **0%** | 176 / 85% | 196 / **100%** | 136 / **100%** |
| 22:08 | 43 / 0% | 105 / 0% | 116 / 46% | 81 / **100%** |
| 22:09 | 18 / 0% | 34 / 0% | 46 / 0% | 26 / **100%** |

Release: bath control 22:06:43 (exact), MAX 22:08:27 (**104s late**), SUM
never through 22:10. Retention at 22:07 reads **176** on
kitchen-only-with-empty-bathroom vs 112 on the genuine control — as a
vacancy discriminator under overlap it is inverted.

## Pointer

The leading gate is the only signal clean through the overlay in both
directions. If release is to survive a neighbor's activity, it has to be
conditioned on the leading edge retreating past the near gates, not on
score or retention decaying — both of which the neighbor holds up
indefinitely.
