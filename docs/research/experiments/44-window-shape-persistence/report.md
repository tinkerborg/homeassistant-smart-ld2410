# 44. Whole-window shape persistence without fixed position

People can move around the room, so a fixed distance or gate center learned at entry is inappropriate. This experiment keeps the anchor for entry only and evaluates a complete 30-second window of scale/offset-invariant still-gate kurtosis. It asks how much of the window must retain an occupied-looking gate shape: the 25th, 50th, or 75th percentile of frame kurtosis must be <=2.15. Labels evaluate only; no fixed gate position or entry template is used.

| Window statistic | Replacement LR occupied | Longest LR false vacancy | `labeled-loop` bathroom clear | Post-deploy bathroom clear |
| --- | ---: | ---: | ---: | ---: |
| 25th percentile | 99.9% | 0.9 s | 103 s after exit | 84 s after exit |
| Median | 95.6% | 42 s | 43 s after exit | 54 s after exit |
| 75th percentile | 33.5% | 475 s | 43 s after exit | 24 s after exit |

The permissive statistic recognizes living-room occupancy through movement and brief shape changes, but also accepts too many kitchen through-wall windows. The strict statistic releases the bathroom faster but rejects too much genuine living-room occupancy. The same tradeoff persists without any fixed gate location. The next window-level test would need to combine independent shape and temporal information, not merely change how many frames must have low kurtosis. No production code changed. [Data](results.json) and [script](analyze.py).
