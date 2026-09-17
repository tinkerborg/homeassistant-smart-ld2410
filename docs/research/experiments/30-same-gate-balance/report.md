# 30. Same-gate motion/still balance for new anchors

Revisited experiment 20's **pre-existing** one-third per-gate motion share on
the newly observed post-deploy failure. A new anchor can form when any gate 2–8
has motion >=40 and motion/(motion+still) >=1/3. Once formed, the original
tracker's template update, retention, and release are unchanged. This is a
relative channel balance, not a fitted house-specific amplitude cutoff. The
one-third threshold is nevertheless a parameter that needs broader validation.

At the three trusted September 15 entry frames, qualifying motion shares were
.621, .698, .808. At the false kitchen re-entry gate4, motion45 and still100
give **.310**, just below one-third. The kitchen false burst had two raw
motion>=40 frames, and zero frames qualifying the combined rule in the
reconstructed kitchen span; the brief post-deploy bathroom span had55/70
qualifying frames.

Experiment-only full-stream replay on the two trusted fixtures and post-deploy
recording preserves every observed bathroom entry and clear time. For the
post-deploy false-entry window, replay occupied frames fall from984 to **zero**.
No additional entry delay is measured on these three visits. The post-deploy
room labels were reconstructed from the user's account and raw streams, so
their boundaries are approximate. This replay uses experiment 26's baseline
adapter, not the deployed baseline snapshot.

This is promising evidence for filtering **this** kitchen re-entry, not a
universal wall discriminator. The false case (.310) is close to .333; other
kitchen motion can have a higher share (experiment 20 found older empty-room
bursts that pass this rule). No production code or configuration changed.

The replacement-sensor fixture adds a separate bathroom walk-by at 11:40:18.
In the full-stack replay, the unbalanced anchor enters at the same timestamp
as the recorded integration and occupies 57 frames with zero departure hold
(214 frames with 30 s hold). Turning on same-gate balance yields **zero**
occupied frames in that walk-by window for either hold setting. Thus balance,
rather than another stack stage, is responsible for rejecting this case in
the replay.

Reproduce: `.venv/bin/python docs/research/experiments/30-same-gate-balance/analyze.py`.
