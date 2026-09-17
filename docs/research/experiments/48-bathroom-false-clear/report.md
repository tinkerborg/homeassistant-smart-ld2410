# 48. New confirmed bathroom false clear

Fixture: `bathroom-false-clear-2026-09-16.db`, bathroom sensor only. User-confirmed occupancy is about 20:08:45–20:13:10. The **live integration** was off from 20:10:38–20:11:31 while occupied, and again from 20:12:31 before the user left. At the 20:10:38 vacancy event, active gates were 2–5, score was 14.67, and confidence was approximately 1.0. This is an anchor/hold decision failure, not absence of raw presence evidence. Motion during the false-clear interval was weak (about 12–23) despite still energy at gates 2–4.

The fixture replay is **not an exact reproduction of deployed state**: the balanced stack's longest false vacancy is 33 seconds (versus the 53-second live outage). The short fixture also has much less history than the live 12-hour floor estimator. Use comparisons directionally.

| Experiment replay | Occupied fraction during labeled visit | Longest false vacancy | On during live 20:10:38–20:11:31 gap |
| --- | ---: | ---: | ---: |
| Balanced anchor, 30 s hold | 74.8% | 33 s | 39% |
| Recent-four shape, 20 s review, corr 0.80 | 83.3% | 29 s | 100% |
| Shape evolution, 30 s review | 94.3% | 15 s | 100% |

The recent-four rule fixes the specific live mid-visit gap in replay but still clears around 20:12:40, about 29 seconds before the confirmed visit ends. The evolution rule stays on after the initial 15-second entry delay, but experiment 46 showed that it badly prolongs another bathroom through-wall event. Experiment 49's recent-four rule at correlation 0.78 also stays on after the initial 15-second delay; it is a narrow threshold adjustment on the same fixture, not independent validation. None of these is yet a general fix. [Data](results.json) and [script](analyze.py).
