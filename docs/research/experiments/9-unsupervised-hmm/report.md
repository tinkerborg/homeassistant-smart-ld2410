# Experiment 9: unsupervised two-state HMM

Data: livingroom-reset-seated, throughwall-morning, bathroom-visit
fixtures. Scripts: h9_base.py (streams + grader + baselines), h9_hmm.py
(features, Baum-Welch, Viterbi), h9_hmm2.py (sweeps, AUC).

## Verdict

**Not viable — not even as a confidence layer.** An unsupervised two-state
HMM finds the *energy-present / energy-absent* latent, not
*occupied / vacant*. On the one fixture where those differ (through-wall
bleed) it fails hardest, and its posterior is worse than the single
feature it consumes.

## Comparison

| detector | seated occ% | drops | empty occ% | bleed-hour occ% | bath entry/release |
|---|---|---|---|---|---|
| shipped | 62.6 | 1 | 31.6 | 17.2 | +0s / +0s |
| 4c entry-only | 38.6 | 1 | 0.0 | 0.0 | +0s / −2s |
| **4e D′** | **100** | **0** | **0.0** | **0.0** | **+0s / +0s** |
| HMM all-4 feat 10Hz | 24.9 | 705 | 5.4 | 14.8 | −58s false pre-latch |
| HMM all-4, 5s frames | 40.2 | 12 | 11.8 | 24.5 | −41s |
| HMM score+ret 10s | 100 | 0 | 29.4 | 55.5 | never releases |
| HMM κ=1e5 sticky | 39.9 | 19 | 12.2 | 25.4 | −58s |

Sweeps over feature sets, aggregation (0.1-10s), self-transition priors
(κ to 1e5), cross-fixture fits: **no configuration is simultaneously good
on seated-hold and through-wall rejection**. The axis that buys stillness
retention (signed retention) is the one bleed maximizes — 4b/4d's wall.
4e escaped it only via two independent mechanics (near-band attribution +
departure arming) that a one-dimensional latent cannot represent.

## Secondary findings

- Hysteresis rediscovery: on level features EM does learn sticky states
  unprompted (A_ii 0.9967-0.9998, dwells 20-460s) — but the stickiness is
  smoothing over the energy envelope, not enter/exit semantics; adding
  motion/lead features collapses dwells to 0.3-2s.
- Posterior as confidence: pooled AUC 0.650, BELOW its own raw retention
  input (0.768); P(occupied | posterior>0.9) = 0.30 (bleed saturates it).
  Per-fixture it looks fine (0.77/0.99) — exactly where it isn't needed.
  Reference: shipped balanced-accuracy 0.701, 4e D′ 0.835 with TNR 1.000.
- Structural blocker: unsupervised per-room fitting cannot express
  "nothing happened here" — a two-state model is forced to split a
  100%-empty hour, labeling 15-55% of it occupied regardless of features.
  Any latent-state approach needs a physics-anchored prior (near-band
  reachability) or a cross-room vacancy anchor; on-device per-room EM has
  neither.
