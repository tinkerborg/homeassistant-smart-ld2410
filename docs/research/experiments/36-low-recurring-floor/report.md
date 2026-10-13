# Lowest recurring quiet mode in the full balanced stack

Experiment-only floor change. The full histogram-floor, mode-spread, run-score,
lone-gate-suppression, energy-floor, motion-anchor stack and 30 s departure
hold are retained. **Same-gate motion/still balance is enabled for new
anchors in every replay.** Only the histogram's selected peak changes: each
gate uses the *lowest* local 2-unit peak with at least 60 seconds' worth of
observations at that fixture's sampling rate, falling back to the dominant
peak until such a lower peak exists. Spread is measured around the selected
peak. Counts use the prefix available at each frame; labels play no role in
estimation. Prefix-causality checks pass.

| Full-stack replay | Dominant mode | Lowest recurring mode |
|---|---:|---:|
| Replacement living room: still floor gates 3/4 before entry | 100 / 100 | **7 / 6** |
| Replacement living room: occupied while user stayed | 29.0% | **35.8%** |
| First living-room false clear after labeled entry | 99.3 s | 126.5 s |
| Longest living-room false vacancy | 529 s | 502 s |
| Labeled walk: bathroom clears after exits | 31.2 / 31.2 s | 31.2 / 31.2 s |
| Labeled loop: bathroom clears after exit | 36.9 s | 36.9 s |
| Post-deploy: bathroom clears after exit | 36.9 s | 36.9 s |
| Post-deploy kitchen false-event window: occupied frames | 208 | 208 |
| New bathroom walk-by: occupied frames | 0 | 0 |
| Cat-only kitchen: occupied fraction in replay | 2.86% | 2.86% |

The floor change recovers a quiet mode matching the recording's empty-room
interval without being told when that interval occurs. It postpones the first
living-room false clear by about 27 seconds, but does not solve seated hold.
The bathroom outcomes in these fixtures are unchanged; this is useful
evidence for the floor estimator, not a general guarantee about all homes or
longer baselines. The cat-only replay's existing positive frames are unchanged,
not eliminated.

The replay rebuilds histogram state from each fixture and does not reproduce
HA's persisted baseline snapshot. No production code, configuration, or
fixture changed. Run `.venv/bin/python docs/research/experiments/36-low-recurring-floor/analyze.py`.
Full measurements are in `results.json`.
