# 29. Does a new still pattern distinguish anchor creation?

Tested the proposed causal statistic at the earliest recorded motion-anchor
frames from the two September 15 fixtures and the post-deploy kitchen false
re-entry. For each frame, the reference is the median of bathroom still-energy
gates 2–8 in the preceding one second, excluding the latest 0.1 second. The
statistic is the size of the difference between current and reference vectors.
No future frames, kitchen sensor values, label fitting, or production changes.

| Trigger | Peak motion | Size of new still pattern |
|---|---:|---:|
| Simultaneous walk bathroom visit 1 | 100 | 46.1 |
| Simultaneous walk bathroom visit 2 | 67 | 20.3 |
| Solo loop genuine bathroom entry | 59 | **2.0** |
| Post-deploy kitchen false re-entry | 45 | **13.5** |

The crucial counterexample is the solo loop: its genuine initial 59-motion
pulse arrives before a measurable new still pattern. The kitchen false trigger
has a larger still-pattern change at its qualifying frame. A rule requiring
novel still energy at anchor creation would reject a genuine fast entry before
it rejects this kitchen false entry. This does not rule out a richer temporal
method, but the simple immediate "new pattern" hypothesis fails here.

`results.txt` contains the exact per-gate differences and timestamps.
Reproduce with `.venv/bin/python docs/research/experiments/29-anchor-novelty/analyze.py`.
