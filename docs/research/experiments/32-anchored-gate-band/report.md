# Anchored gate-band hold with the full stack

This experiment changes only the hold refresher in the experiment 26 replay.
Entry still requires the full histogram-floor, mode-spread, run-score,
lone-gate-suppression, energy-floor, motion-anchor stack **plus the same-gate
motion/still balance rule** that rejected the post-deploy bathroom false entry.
The existing 0 or 30 second departure hold is unchanged.

The proposed refresher records gates carrying at least 20% of the initial
motion-weighted still template. It keeps the anchor alive while the *sum* of
baseline-corrected still energy in that band remains at least 40% of its
initial sum. `band_core` uses those gates; `band_halo` also includes each
immediate neighbor. A new band requires another balanced motion event. This
is a causal, fixed-rule experiment; labels are used only to evaluate it.

| Fixture, 30 s hold | Exact anchor | Band core | Band halo |
|---|---:|---:|---:|
| Replacement living-room sensor: occupied fraction after return | 29.0% | 28.9% | 28.9% |
| Labeled walk: clear after bathroom exit | 31.2 s, 31.2 s | 32.3 s, 32.7 s | 32.2 s, 32.7 s |
| Labeled loop: clear after bathroom exit | 36.9 s | 41.7 s | 42.1 s |
| Post-deploy: clear after bathroom exit | 36.9 s | 39.4 s | **170.2 s** |
| Post-deploy reported kitchen false-event window: occupied frames | 208 | 233 | **1,150** |

The living-room row uses the replacement fixture, with an empty interval and
a real entry at 11:40:36. At zero departure hold, the exact anchor and core band had zero occupied
frames in the post-deploy false-event window; halo had 1,150. The broad band
therefore lets kitchen still energy sustain the bathroom anchor despite the
same-gate entry filter. The narrow band avoids that severe leak but barely
improves the living-room failure. Neither is a useful replacement.

The replay estimates a fresh histogram baseline from each recording rather
than reproducing the deployed detector's persisted baseline, and the
post-deploy labels were reconstructed from the user's account. The outcome is
strong enough to reject this particular hold rule, not to measure deployed
performance precisely. No production code or fixture was changed.

Run: `.venv/bin/python docs/research/experiments/32-anchored-gate-band/analyze.py`.
Detailed output: `results.json`.
