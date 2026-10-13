# Experiment 4e: ownership release (variant D′)

Bridges 4d's split. Data: 4b/4c overlap streams + both D0:6E fixtures +
`livingroom-reset-seated-fd68.db`. Scripts: e4_*.py here.

## Verdict

**Variant D′ passes all four targets.** Two mechanics together — neither
passes alone:

1. **Signed retention.** `pos = max(0, fast−slow)/floor`, peak-held with
   ~90 s decay. The unsigned `|fast−slow|` is a change detector: a
   *departure* drives it to its maximum (bath control peaks 217 at
   22:06:50, two minutes after the occupant left) — the whole reason 4d
   saw neighbor > still-occupant. The positive part is ~0 in every release
   window (bath post-departure 0.5, MAX 0.6, kitchen 0.0) and 11-15 in
   every hold window. The sign change is the missing discriminator.
2. **Departure arming.** Ownership starts DISARMED at a qualifying entry:
   signed retention refreshes hold, stillness can never release. After
   near-lead activity has been absent `quiet_s` (walk-in settled), a fresh
   burst of ≥`cross_n` near-band frames within 20 s ARMS departure — the
   occupant re-crossed their entry gates. From then on only attributed
   evidence (score ≥ exit AND near-lead within `grace`) refreshes release;
   a neighbor can never light the near band, so it cannot hold the door.
   Retention decay stays as the no-crossing fallback.

## Scores (hold_s = 30 / 60)

| variant | T1 MAX | T2 bath | T3 kitchen | T4 FD:68 |
|---|---|---|---|---|
| shipped | ✗ 21:58:50→22:08:27 | ✓ 22:06:43 | ✗ enters | ✗ drop 21:49:56, 31.6% empty-occ |
| 4c entry-only | ✗ 22:08:27 | ✓ | ✓ | ✗ drop 21:49:56 |
| A grace 60/90 (4d) | ✓ | ✓ | ✓ | ✗ drop 21:42-21:44 |
| c unsigned ret r20 | ✗ never | ✗ never | ✓ | ✓ |
| S signed t30 r20 g90 | ✓ | ✗ 22:07:07 | ✓ | ✗ drop 21:44:34 |
| S signed t90 r12 | ✗ never | ✗ never | ✓ | ✓ |
| D guard-armed | ✓ | ✓ | ✓ | ✓ (4 s margin) |
| **D′ quiet-gap-armed** | **✓ 22:07:13/22:07:43** | **✓ 22:06:43/22:07:13** | **✓ NEVER** | **✓ 0 drops, 0.0% empty, seeded release 21:19:57/21:20:27** |

D′ passes across ret_on 12-20, quiet_s 5-15, cross_n 10-40, grace 60-90,
tau_peak 90 — a plateau, not a point fit. Bath and MAX arm at 22:04:52
(the walk back toward the door) and release identically; FD:68 never arms
across the seated span (one near frame at 21:42:20).

## What failed

- Near-band support on far-lead frames: 0.0% of the seated FD:68
  occupant's far-lead frames carry sup(g0,g1) ≥ 1.0 — identical to the
  neighbor. Rear-mounted sensor; the seated occupant never lights the
  near band.
- Level statistics (still residual, 30s EMA, raw): seeded occupant reads
  BELOW the empty room (0.00/0.28 vs 1.00/0.35) — absorption, exactly what
  retention exists for.
- Gates ≤ entry band for retention: non-starter on D0:6E (entry band is
  g0-1, still-channel hardware zero).
- Unsigned retention as release gate can never hit T2: the departure
  transient holds |fast−slow| at 197 for 30s, 82 for a further minute,
  room empty.
- Un-held signed retention fails T4 (97s sub-threshold gap mid-seated);
  the 90s peak-hold is load-bearing.
- Fixed-guard variant D passes but with a fragile 46-95s window; D′'s
  quiet-gap reset removes the parameter and the fragility.

## Spec impact

Contradicts spec 24 §2 as written ("release requires retention decay"):
under D′ retention BLOCKS release while disarmed, arming PERMITS release
on attributed evidence, decay is only the no-departure fallback. Spec
updated accordingly. MAX/SUM caveat stands: energies don't superpose;
rule behavior only.
