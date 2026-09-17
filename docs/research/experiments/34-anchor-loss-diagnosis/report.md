# Why the replacement living-room anchor drops

Experiment-only replay of the full stack with the same-gate balance entry
rule. This is a diagnosis of the new sensor's 11:40:36 entry and seated
period, not a production change. The replay's histogram state is rebuilt
from the fixture; the live persisted baseline and anchor score were not
exported.

At the first loss of anchor support in replay (11:41:08.838, 32.84 s after
the entry label), the normalized match is **0.390**, just below the anchor's
0.400 retention threshold. The current/template cosine is 0.701 and the
amplitude ratio is 0.557; their product is 0.390. Thus both a changing
cross-gate pattern and weaker amplitude contribute.

The replay's still floor was already **100 at gates 3 and 4 before entry**.
At the loss frame, raw still was 100/88 on these gates, but their positive
residuals were 0/0. An actual empty-room interval before entry had medians
of 7/6 at gates 3/4. This suggests the histogram had learned earlier
occupied activity as background. Freezing either the floor or spread at
entry makes no difference: the problem predates that entry.

| Replay condition, 30 s hold | Occupied fraction while seated | Longest false vacancy |
|---|---:|---:|
| Normal histogram | 29.0% | 529 s |
| Freeze floor at entry | 29.0% | 529 s |
| Freeze spread at entry | 29.0% | 529 s |
| Replace still floor at entry with empty-interval median | 35.8% | 502 s |

Correcting the floor helps only modestly. The exact anchored pattern still
changes enough to lose hold, so the floor alone is not the solution. In live
state history, the integration turned vacant at 11:42:15 while score was
3.89, above default exit score 1.5. This directly supports the separate
finding that the exclusive motion-anchor hold path, not low ordinary score,
allowed the false clear. We cannot attribute the live anchor loss precisely
without exporting its template, match score, and floor.

Run `.venv/bin/python docs/research/experiments/34-anchor-loss-diagnosis/analyze.py`.
Detailed values are in `results.json`.
