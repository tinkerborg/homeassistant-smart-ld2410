# Experiment 6: motion-gated ceiling window

Data: full dev history (D0:6E ~12 days, FD:68 ~7.5 days) + 30-day
synthetic vacation simulations. Current semantics reconstructed faithfully
from algo/baseline.py MoveCeiling (60s buckets, q90, 720-bucket/12h
window).

## Verdict

The time-window ceiling is genuinely vacation-fragile, but the failure has
never occurred in recorded data (real occupancy never leaves a 12h gap:
ceiling sat at 100 continuously post-warmup on both sensors, bar<42 only
during cold start). Simulated vacation: ceiling collapses to bleed level
(~47) within ~24h and the bar (~26) re-admits bleed for the remainder.

Motion-gating fixes it: same bucket machinery, but the window advances
only through buckets whose raw max move clears an admission floor.

| floor | 30-day vacation+bleed (42-58) | regime-change relearn (capped 60) |
|---|---|---|
| 15/30 | decays like current | relearns |
| 50 | leaks (decays to ~48 by day 15) | relearns |
| **60** | **stable at 100** | **relearns by day 4** |
| 65 | stable | never relearns (capped motion can't clear it) |

Cold start unaffected (ready/age come from GateBaseline buckets, not
MoveCeiling; real logs clear any tested floor in the first bucket).

## Recommendation

Admission floor 60 (only value passing both tests); margin over worst
observed bleed peak (58) is 2 units — if bleed is ever underestimated,
prefer 65 and accept relearning then requires arrivals >65 (real arrivals
saturate ~100, so safe). The window length parameter is unchanged (720
buckets); only which buckets count changes.
