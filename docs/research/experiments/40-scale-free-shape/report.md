# 40. Scale-free gate-shape descriptors

Question: Do the bathroom sensor's gate profiles distinguish real bathroom presence from kitchen through-wall presence without using total energy, a learned entry template, or labels in the calculation?

Method: On each frame, compute still and motion profile entropy, centroid, kurtosis, local-peak count, and correlation of gate-normalized profiles across 0.1/0.5/1 seconds. Use gates 2–8 from the bathroom sensor alone. Labels score each descriptor afterward. AUC below 0.5 means the descriptor is lower during genuine occupancy; separation strength is `max(AUC, 1−AUC)`. No classifier or threshold was fitted.

| Descriptor | `labeled-walk` separation | `labeled-loop` separation | Direction during real bathroom occupancy |
| --- | ---: | ---: | --- |
| Still-profile kurtosis | 0.957 | 0.961 | lower, broader single lobe |
| Motion-profile entropy | 0.869 | 0.961 | lower |
| Motion-profile centroid | 0.884 | 0.962 | nearer gates |
| Still-profile centroid | 0.909 | 0.873 | nearer gates |
| Motion-profile correlation, 0.5 s lag | 0.822 | 0.885 | higher |

The same broad pattern remains in the first 30 seconds after a genuine bathroom exit into kitchen activity: still kurtosis separation is 0.943/0.947 and motion entropy separation is 0.880/0.967 across the two recordings. Thus, the exit confusion in experiment 39 may be addressable using profile *concentration* or *location* instead of similarity to an entry template.

Living-room failure check: During 7,561 frames labeled occupied but cleared by the balanced full-stack replay, the still-profile centroid median is 4.18; when correctly detected it is 4.08; in the labeled empty interval it is 5.20. Missed occupied versus empty centroid has 99.9% pairwise separation. Still entropy is 1.729 missed, 1.738 detected, 1.876 empty. This means the living-room shape remains occupancy-like while the current hold fails. The empty comparison interval is short, so this is evidence of a signal, not proof of general reliability.

Limitations: These are frame-level, retrospective separations, not a validated causal occupancy rule. AUC uses labels only for evaluation, but selecting among descriptors based on these same fixtures risks overfitting. Sum-normalized entropy and centroid are scale invariant, **not offset invariant**; per-frame z-score kurtosis, peak count, and normalized temporal correlation are invariant to a positive affine transform. The LD2410's 0–100 clipping can change even normalized shape. A `lone window with no calibration` claim is therefore unproven. No production code was changed. [Data](results.json) and [script](analyze.py).
