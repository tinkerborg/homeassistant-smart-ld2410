# Experiment 12: per-room exit policy

Question: choose exit policy per room — arming (4e D′) where bleed
pressure exists, retention-only (4d form c) where it doesn't — to resolve
the multi-occupant trade. Scripts: bp3.py, pol.py, mo*.py (runs pinned to
HEAD 8da2b93; the working tree was being edited concurrently).

## Verdict

**Does not resolve the trade — dissolves into a no-op where it would help
and picks the wrong side where it hurts.** But two by-products are
valuable:

1. **The bleed-pressure statistic works, label-free.** Episode-level
   orphan ratio (episodes with no near-band frame within ±120s, ≥60s,
   per near-band-episode second): D0:6E 0.10-0.40 vs FD:68 0.037-0.054 —
   4-7x separation, threshold 0.07, needs ≥12h of data. Per-frame and
   per-second variants FAIL (a far-seated occupant is per-frame
   indistinguishable from bleed; episode-level ownership is load-bearing).
2. **Uniform D′ equals the matched policy on every fixture.** Matched
   assignment reproduces 4e exactly on the bathroom streams and form-c
   exactly on the living room — but so does uniform arming, because on
   FD:68 arming can NEVER fire (zero near-band frames in the whole
   synthetic stream, walk-outs included): retention-only and arming are
   behaviorally identical there.

## Multi-occupant synthesis

| case | arming | retention-only |
|---|---|---|
| FD:68 stayer + leaver walks out | holds | holds |
| FD:68 both leave | releases +107s | releases +141s |
| D0:6E near-band stayer + leaver | armed, holds | holds |
| D0:6E FAR-GATE stayer + leaver | **drops stayer +24s** | holds |

The hazard needs both: arming can fire (real near band) AND the stayer
sits beyond it. Pressure does not predict that combination — the policy
selects arming exactly where the hazard lives. Mitigating: a realistic
two-person bathroom is safe (the real still occupant keeps re-lighting
the near band; armed yet held throughout).

## Misclassification cost (asymmetric)

- Retention in the bathroom: +202s late release, 8.9% vs 2.9% occupied.
- Arming in the living room: zero measurable (never arms; identical
  outcomes). Also: DISARMED arming under bleed with no crossing is worse
  than retention-only (seeded throughwall latch 742s vs 30s) — arming
  only protects after it arms.

## Conclusion

Ship uniform D′ (arming semantics everywhere); the far-gate-stayer drop
in near-band-capable rooms remains the one open multi-occupant hazard,
unpredictable by pressure, deferred to Phase 3 attribution. The
bleed-pressure statistic survives as a useful diagnostic.
