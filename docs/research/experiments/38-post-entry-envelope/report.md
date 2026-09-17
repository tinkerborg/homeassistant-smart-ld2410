# 38. Post-entry still-gate shape

Question: Can the raw still-gate shape learned just after activation recognize continued occupancy without labels or a new motion event?

Method: Full balanced stack determines activation. Compare bathroom and living-room still gates 2–8 with a per-gate envelope and cosine similarity learned from the first 3–12 seconds. Separately inspect a settled template from seconds 30–60. Labels are used only for evaluation.

Result: A fixed early envelope does not track someone settling into a seat: it accepts only 4.2% of later living-room frames and has a 585-second rejection run. A settled 30–60-second residual-shape template matches 98.9% of later living-room frames and 100% of later genuine bathroom frames in the longer `labeled-loop` visit. But it also matches 22.7% of the first 30 seconds after bathroom exit into the kitchen. These are per-frame diagnostic rates, not occupancy decisions.

The settled shape is promising for continuity, but similarity alone does not prove occupancy. See experiment 39 for causal full-stack replay. [Data](results.json) and [script](analyze.py).
