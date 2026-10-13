# 39. Settled-shape hold in the full stack

Question: Can a still-gate shape learned after entry hold genuine occupancy while releasing bathroom through-wall presence? No labels are used to learn the shape.

Method: Keep the deployed stack in experiment replay, including same-gate balance. At 60 seconds after anchored entry, replace the anchor hold decision with cosine similarity >=0.9 and relative amplitude >=20% against median still gates 2–8 above the pre-entry baseline, learned during seconds 30–60. Keep the existing 30-second departure hold. Before 60 seconds, use the original motion anchor. This changes experiment code only.

| Fixture | Exact anchor | Settled shape |
| --- | ---: | ---: |
| Living-room true occupancy | 29.0% | 81.5% |
| Living-room longest false vacancy | 529 s | 195 s |
| `labeled-loop` bathroom clear after exit | 36.9 s | 81.6 s |
| `labeled-walk` bathroom clear after exits | 31.2 / 31.2 s | 31.2 / 31.2 s |
| Post-deploy false-window positive frames | 208 | 208 |
| New bathroom walk-by positive frames | 0 | 0 |

Conclusion: The shape improves seated continuity but is not a viable hold rule. It retains bathroom occupancy far too long after a long visit, and still permits a 195-second false vacancy in the living room. Short visits never reach the settled-template phase, explaining unchanged `labeled-walk` and post-deploy behavior. Entry timing is unchanged by construction. [Data](results.json) and [script](analyze.py).
