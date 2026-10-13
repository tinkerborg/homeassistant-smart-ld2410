# 20. Per-gate motion/still balance

## Question and method

Does relatively stronger motion distinguish bathroom presence from kitchen
bleed, including simultaneous occupancy? Use bathroom readings only, gates
2–8 because still gates 0–1 are unavailable. Each frame independently:
`share[g] = move[g] / max(move[g] + still[g], 1)`.
Compare a motion threshold alone, that threshold plus a same-gate share
threshold, and a whole-sensor share threshold. Fixed descriptive grid:
motion 20/40/60; share .20/one-third/.50. No classifier, fitting, label-driven
threshold selection, smoothing, or confirmation window. Labels evaluate results.

## Findings

At the illustrative motion=40, share=one-third setting:

| Fixture | Motion alone: IN positive | Same-gate: IN positive | Whole-sensor: IN positive | Same-gate TW positive |
|---|---:|---:|---:|---:|
| Sept 15 solo loop | 57.25% | 48.78% | 12.71% | 0% |
| Sept 15 simultaneous walk | 49.88% | 42.04% | 16.15% | 0% |

These are positive-evidence frame fractions, **not occupancy accuracy**.
Local arithmetic preserves more evidence than a whole-sensor ratio, but motion
alone also rejects all TW frames in these two recordings at this setting.
The ratio's additional value is therefore not established here. The same
local/whole difference exists in the solo case, so it cannot be attributed
solely to the additional kitchen occupant.

Older definite bathroom-empty morning data still contains **six frames** that
pass both motion=40 and the same-gate ratio. These include adjacent high-motion
gates, not just an isolated high ratio in a quiet gate. Weak motion alone is
not a universal kitchen signature. In Sept 9 frames with peak motion 20–40,
median same-gate share is .210 during the longer toilet visit, .215 at the
stove, and .228 at the island: controlling roughly for motion strength exposes
substantial overlap. Quiet bathroom presence can have the same low balance.

Motion=60 with share=one-third is mathematically redundant for energies bounded
by 100: 60/(60+100) already exceeds one-third. Agreement there is not evidence
for ratio discrimination.

## Limits and corrected scope

This examines **positive evidence**, not whether occupancy clears after a
bathroom occupant leaves while a kitchen occupant remains. Low motion cannot
by itself settle that question. Experiment 21 addresses that retention problem.

At motion=40, first positive evidence in the simultaneous walk is 1.69 s after
the first entry label, and .016 s after the second. The labels are not an
independent precise entry clock; this does not demonstrate imperceptible entry.
There is no extra waiting in the arithmetic itself.

Older stove-case times are approximate. Most of its apparent strong TW
exceptions occur in the final 28 s before the next bathroom label, so they
must not be presented as conclusive wall-only detections. The bathroom-empty
morning exceptions do not have that ambiguity.

Reproduce: `.venv/bin/python docs/research/experiments/20-channel-balance/analyze.py`.
Full per-span distributions and sensitivity grid: `results.txt`, `results.json`.
No production changes.
