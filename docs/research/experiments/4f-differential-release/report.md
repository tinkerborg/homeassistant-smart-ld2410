# Experiment 4f: differential release → retention reset (D″)

Motivation: shipped D′ arms release on ANY near-band crossing — a cat's
exit arms while a human sits at far gates, dropped after grace (live
failure, and D′ also fails the two-person overlay). Per-room knobs
rejected; fix must be config-free. Scripts: d2*.py (window form),
d3*.py (reset form).

## Verdict

**The literal pre/post differential fails structurally; the reset variant
passes everything.** D″-reset: a qualifying near-band crossing no longer
arms anything — it clamps the peak-held signed retention to 0 (and keeps
clamping until near-band activity is absent `clamp_s` ≈ 60 s). Release is
then plain retention/attributed-evidence blocking. A room still holding
someone re-lifts retention above threshold within the clamp window; an
empty room cannot. No armed state, no per-room configuration.

## Scores (hold 30 / 60)

| | T1 MAX | T2 bath | T3 kitchen | T4 FD:68 | T5 cat-exit | T6 two-person |
|---|---|---|---|---|---|---|
| D′ (shipped) | ✓ | ✓ | ✓ | ✓ | **✗ drops 21:48:53** | **✗ releases 22:07:07** |
| D″-window (90 configs) | fails T1/T2 or reproduces D′ | | ✓ | ✓ | ✗ | ✗ |
| **D″-reset τ90 clamp60** | ✓ 22:07:13/22:07:43 | ✓ 22:06:43/22:07:13 | ✓ NEVER | ✓ 0 drops, seed 21:19:57/21:20:27 | **✓ HELD** | **✓ HELD** |

T5 baseline reproduced first: splicing the fixture's own real near-band
walk into the seated span makes D′ arm and drop the seated user — the
live failure. Long-tail cost unchanged (bathroom 3.8-4.3% occupied vs
truth 2.9%, same as D′).

## Why the literal differential fails

- Un-held retention: the far-seated user's pre-window is all zeros
  (sparse typing bursts) — ratio undefined; stretching pre to 300s
  inverts the classes.
- Peak-held retention: post/pre ≈ exp(−Δt/τ) for everyone — pure decay,
  no separating fraction.
- Structurally: pre is the crossing person's MOTION, post is the stayer's
  STILLNESS, so a genuinely present still occupant reads as collapse.
  Window placement (burst start −5s, not first queue frame) is
  load-bearing but insufficient.

## Plateau

clamp_s 58-72 (below: bath releases late; above: cat case returns);
τ_peak 90 the only value passing both holds; ret_on 12-20, cross_n 10-40,
quiet_s 5-10, grace 60-90 (hold 60) all pass.

## Caveats

- clamp_s is a new global constant with a tighter plateau (±12s) than
  4e's parameters — bounded by walk-out duration below and the seated
  re-lift latency above.
- T6 passes on thin margin (stayer's post-crossing signature nearly
  destroyed by the per-gate-MAX synthesis; 1-5% of frames re-lift it).
  The native T5 case separates widely (23% of frames).
- Spec impact: replaces the armed/disarmed language — there is no armed
  state; a crossing zeroes the retention hold rather than bypassing it.
