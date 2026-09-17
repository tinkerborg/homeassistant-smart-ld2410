# 46. How the gate shape evolves within a window

Question: Can temporal coherence of the normalized still-gate pattern distinguish occupancy without requiring a fixed position or a saved entry shape?

Diagnostic 10-second windows show the mean frame-to-frame distance of z-scored still-gate profiles is much lower during labeled bathroom occupancy than kitchen through-wall presence: about 0.03 versus 0.14 in both trusted bathroom recordings. It is also lower in the labeled living-room occupancy than the known empty interval: about 0.06 versus 0.16. These are dimensionless shape changes, not energy levels.

Method: Balanced anchor qualifies entry only. Every 30 seconds, compare the window's mean adjacent-frame z-profile distance with a single cutoff. Labels evaluate only.

| Cutoff | Replacement LR occupied | Longest LR false vacancy | `labeled-loop` bathroom clear | Post-deploy bathroom clear |
| --- | ---: | ---: | ---: | ---: |
| 0.08 | 51% | 297 s | 43 s | 174 s |
| 0.10 | 51% | 297 s | 43 s | 174 s |
| 0.12 | 98.7% | 12 s | 43 s | 174 s |

**Result:** Temporal evolution is an independent signal, but this stand-alone rule fails the post-deploy bathroom case: stable kitchen through-wall presence can also produce a coherent pattern, holding the bathroom almost three minutes after exit. The 0.12 variant also holds the known empty living-room minute for 11% of frames. No production algo code changed. [Data](results.json) and [script](analyze.py).
