# Entry-change hold on the replacement living-room fixture

Experiment-only replay of the full histogram-floor, mode-spread, run-score,
lone-gate-suppression, energy-floor, motion-anchor stack, including the
same-gate motion/still balance entry rule. Entry decisions are unchanged. The
only alternate hold refresher compares raw still gates with their median
0.5–2.5 seconds before a balanced motion anchor. It tracks the added signal
on gates contributing at least 20% of the initial peak. The departure hold is
still the existing 30 seconds. No labels or other sensors inform decisions.

| 30 s departure hold | Exact anchor | Entry change, retain 40% | Entry change, retain 20% |
|---|---:|---:|---:|
| New living-room sensor: occupied after 11:40:36 entry | 29.0% | 50.9% | 81.1% |
| Longest false vacancy while user stayed | 529 s | 295 s | 195 s |
| Living-room entry delay | 1.03 s | 1.03 s | 1.03 s |
| New bathroom sensor: walk-by occupied frames | 0 | 0 | 0 |
| Post-deploy kitchen false-event window: occupied frames | 208 | 211 | 215 |
| Labeled loop: bathroom clear after exit | 36.9 s | 42.3 s | 43.1 s |
| Labeled walk: bathroom clears after exits | 31.2/31.2 s | 32.0/34.1 s | 32.5/39.9 s |

The corrected fixture genuinely includes a preceding empty living room and
an entry; the prior old-unit fixture did not establish this. Entry-change
tracking therefore helps substantially, but even the looser 20% criterion
leaves a >3-minute false vacancy while seated. It also stretches bathroom
departure beyond the preferred roughly 30 seconds. This is useful evidence
for the mechanism, not a viable hold rule yet.

The full-stack *replay* rejects the new bathroom walk-by due to the
same-gate balance rule. The recorded deployed integration falsely occupied
11:40:18–11:40:34, so this replay result is a prediction of the proposed
stack, not a claim about what ran live. Baselines are re-estimated from each
recording; persisted deployed baseline state was not exported.

Run `.venv/bin/python docs/research/experiments/33-entry-change-hold/analyze.py`.
Frame-level summary metrics are in `results.json`.
