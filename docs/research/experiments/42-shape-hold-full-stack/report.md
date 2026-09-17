# 42. Shape-only hold rule in the full stack

Question: Can Fable's scale-free gate-shape idea become a working hold rule under the existing entry stack?

Method: Keep full entry stack and same-gate balance. Once occupied, permit either the original motion anchor or low **per-frame z-scored still-gate kurtosis** (gates 2–8) to refresh occupancy; keep 30-second departure hold. Kurtosis is invariant to positive scale and uniform offset. Compare cutoffs 1.8, 2.0, 2.2 and a short 2- or 5-second median. This is a feasibility sweep, not a calibrated production rule. Labels score results only; the mixed-day fixture is unlabeled outside the earlier narrated interval.

| Case | Original anchor | Shape cutoff 2.0, instant | Shape cutoff 2.0, 2 s median |
| --- | ---: | ---: | ---: |
| Known living-room occupied interval | 26% on | 100% on | 100% on |
| 12:00–12:20 isolated LR flapping | 32% on | 100% on | 100% on |
| Known 11:39–11:40 living-room empty | 10% falsely on | 100% falsely on | 36% falsely on |
| `labeled-loop` bathroom clear after exit | 37 s | 137 s | 129 s |
| Post-deploy bathroom clear after exit | 37 s | 65 s | 66 s |

A stricter 1.8 cutoff with a 5-second median brings `labeled-loop` bathroom clearing down to 57 seconds but only raises living-room occupancy from 29% to 33% in the replacement fixture. The new bathroom walk-by stays rejected in all variants. The 14:00–16:00 unverified quiet-looking mixed-day period stays off for cutoff 2.0, but this does not rescue the known empty minute or bathroom departure.

**Result: rejected as a stand-alone hold supplement.** Shape features separate distributions well, but occasional through-wall frames also have the “occupied” shape. Each such frame resets the 30-second departure timer. A loose rule fixes the living room at the cost of bathroom retention and false occupancy; a strict rule does too little for the living room. Short smoothing does not resolve the tradeoff. AUC from experiment 40 was not sufficient evidence that a temporal occupancy rule would work. No production algo code changed. [Data](results.json) and [script](analyze.py).
