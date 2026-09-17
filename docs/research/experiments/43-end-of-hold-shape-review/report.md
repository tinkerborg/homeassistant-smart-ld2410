# 43. Shape review at the end of each hold window

This tests the user's corrected decision sequence: the balanced motion anchor qualifies **entry only**. After entry, the experimental detector reviews the scale/offset-invariant still-gate kurtosis over a complete 10-, 20-, or 30-second window. It continues occupancy if the window looks occupied, otherwise clears. One variant requires two or three consecutive clear-looking 10-second windows. The anchor does not refresh occupancy after entry. The entry stack and same-gate balance are unchanged. Labels evaluate results only.

| Variant | Replacement LR occupied | Longest LR false vacancy | `labeled-loop` bathroom clear after exit | Post-deploy bathroom clear after exit |
| --- | ---: | ---: | ---: | ---: |
| Current anchor hold, 30 s | 29% | 529 s | 37 s | 37 s |
| Shape review every 10 s, cutoff 2.15 | 34% | 475 s | 13 s | 24 s |
| Every 10 s, require 2 clear windows | 35% | 467 s | 43 s | 54 s |
| Every 10 s, require 3 clear windows | 96% | 37 s | 53 s | 64 s |
| Shape review every 30 s, cutoff 2.15 | 96% | 42 s | 43 s | 54 s |

The 30-second review also holds the known empty living-room minute for 17% of its frames and the mixed-day known occupied interval for 96%, versus 10%/26% under the current anchor hold. The 10-second single-window review holds that known occupied interval for only 31%. The three-window variant holds the known empty minute for 14% and the mixed-day known occupied interval for 96%. The first `labeled-walk` visit does not clear before the next visit with the 30-second review; it clears 33 seconds after exit with the three-window variant. The new bathroom walk-by remains rejected in every variant. The mixed-day 14:00–16:00 unverified quiet-looking period stays off.

**Result:** Delaying the decision to the end of a whole window is materially better than allowing each stray frame to reset the timer. It still exposes a time tradeoff with this single shape feature: short windows lose living-room occupancy; enough smoothing to retain it makes bathroom release 43–64 seconds on these fixtures, and the living room still has a 37–42-second false vacancy. The shape-review architecture deserves further work, but these variants are not a complete fix. No production algo code changed. [Data](results.json) and [script](analyze.py).
