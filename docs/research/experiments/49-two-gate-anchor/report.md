# 49. Overnight false-anchor contrast and entry guard

The two overnight no-human bathroom entries were brief, weak motion events: peaks 46 and 40, respectively, with balanced motion at **one gate** for only two and one frames. The trusted genuine bathroom entries had motion peaks at least 59 at replay activation and ultimately balanced motion at two or more gates. The new false-clear fixture's initial genuine entry had peak 100; its re-entry during the false gap began at peak 60. These are observations on few events, not a proven boundary.

Experiment-only entry variants, using the full balanced stack:

| Entry variant | Overnight bathroom episodes | `labeled-loop` genuine entry offset | Replacement LR with recent-four hold |
| --- | ---: | ---: | ---: |
| Current motion 40, one balanced gate | 2 | 0.39 s | 99.7% occupied |
| Two balanced gates within 0.3 s | 0 | 1.91 s | 17% occupied |
| Motion 55, one balanced gate | 0 | 0.39 s | 23% occupied |

Thus the two-gate condition rejects the overnight artifacts but violates the user's subsecond entry requirement on `labeled-loop` and destroys living-room performance. A motion-55 threshold rejects these particular overnight events without delaying the known bathroom entries, but fails badly in the living room and is selected from a small sample; it cannot be treated as a general rule.

For **bathroom only**, motion 55 plus recent-four 20-second shape review at correlation 0.78 gives no overnight bathroom episode in this fixture, covers the known 20:10:38–20:11:31 false-clear interval, and remains on after the initial 15-second entry delay through the end of the new labeled visit. In the older trusted bathroom fixtures, it clears `labeled-walk` 23/17 seconds after exits, `labeled-loop` 43 seconds after exit, and post-deploy about 34 seconds after exit. This is a promising *feasibility check*, not a deployable result: the motion bar and similarity were chosen after viewing these cases, the overnight negative set has only two events, and the new short-fixture replay does not exactly match the live state history.

No production algo code changed. [Data](results.json) and [script](analyze.py).
