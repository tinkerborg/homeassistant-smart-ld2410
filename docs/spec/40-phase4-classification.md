# 40 — Phase 4: Target Classification

Classify detection episodes: `human | animal | artifact`. Trained on the label
store; inference in-process; nothing here changes detection sensitivity —
classification modulates the published class and the policy layer only.

## 1. Features (per episode, computed in the algorithm core)

From frames within the episode (all replayable):

- duration_s; still_frac; peak_residual (move, still)
- gate_span_mean, gate_span_max; centroid_mean, centroid_min
- centroid_speed: mean |d centroid/dt| (gates/s); centroid_reversals per 10 s
- residual_mass ratio move/still; burstiness: var/mean of 1 s residual sums
- entry_transient_s: first exceedance → max span
- low_profile: fraction of residual mass in gates ≤ 2 while span ≤ 1.5
- context (joined at training time, optional at inference): hour-of-day bucket,
  room

Feature extraction versioned with the core semver; vectors logged to
`episode_features(episode_id, fvec JSON, feat_ver)`.

## 2. Labels

From 32: `true_presence`/`user_true` ⇒ human (unless user labeled animal),
`user_false` + animal tag ⇒ animal, `auto_false(*)` ⇒ artifact. Night
movement during all-residents-in-bed windows ⇒ candidate animal, queued for
one-tap user confirmation before entering the training set (do not auto-trust:
it may be an intruder or a resident the beds missed).

## 3. Training pipeline

Standalone package (`smart_ld2410_train`), runnable anywhere (k8s job or
laptop):

1. Pull episodes + features + labels from sensor DBs (read-only).
2. Split by episode with room+week stratification; no episode overlap between
   train/eval.
3. Model: gradient-boosted trees (lightgbm), max ~200 trees, monotonic
   constraints none, class weights from §4 costs.
4. Emit artifact dir: `model.txt`, `meta.json` (version, algo_semver,
   feat_ver, data range, per-class PR, confusion, calibration), `report.md`.

Nightly schedule optional; **promotion is manual**: setting the artifact path
in options is the promotion act. Integration validates meta compatibility
(10 §5) and logs the loaded version into every classified episode.

## 4. Cost asymmetry (encoded in eval + class weights)

Ranked failures, worst first:

1. human classified artifact/animal while present (lost presence) — weight 10
2. artifact classified human (false occupancy) — weight 3
3. animal classified human (lights for the cat) — weight 1
4. human classified animal at night (dark hallway for a person) — weight 5

Eval report must show metric per failure class; a promotion that improves
aggregate but regresses class 1 is rejected by policy.

## 5. Serving & policy

- Inference at episode entry and every 5 s while active, on the
  latest-window features; output class + calibrated probability, published as
  attributes on the sensor's occupancy entity and in the episode event.
- Policy layer (options): `animal_suppression: day|night|always|never`
  (default `night`), threshold `animal_conf_min` (0.8). Suppression means the
  binary stays off for that episode while the class attribute reports animal;
  house layer receives the class and may still count it as non-human presence.
- Below thresholds: class `uncertain`, no suppression (default-trigger).

## 6. Validation

1. Held-out eval meets §4 policy; report reviewed before first promotion.
2. Replay week with model active: false-occupancy episodes strictly reduced
   vs Phase 3 output; zero lost-presence regressions on the standing suite.
3. Cat nights (residents pinned in beds, movement episodes): suppression rate
   reported; target is "3 a.m. lights problem gone in practice," measured over
   ≥ 14 nights.
4. Open question stays open until data answers it: crouched-human vs cat
   separability — maintain a labeled crouched-human eval set before enabling
   `always` suppression anywhere.
