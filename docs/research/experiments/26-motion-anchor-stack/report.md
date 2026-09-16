# 26. Motion anchor with the simplified stack

## Implementation and scope

Added the reusable `algo/presence/motion_anchor.py` primitive. It accepts
current motion/still readings and external floor/spread values; it owns only
the template, score, and timestamp continuity. Defaults reproduce the tested
motion threshold 40 and retained footprint fraction .4 over gates 2–8.
It has no occupancy timer and is not registered or enabled in production.

`replay.py` wires the following together only for this experiment:

1. Histogram floor / mode-local spread: incremental raw-sample histogram
   adapter from experiment 25, for both channels and all nine gates.
2. Actual `RunScorer` and `LoneGateSuppression` classes, using the existing
   k=4.5, support EMA tau=1 s, enter/exit scores 3/1.5.
3. Actual `EnergyFloor` class, raw combined-energy minimum 30.
4. Optional `MotionAnchor`: entry must pass the score and energy filters AND
   have anchor support. Once occupied, anchor support alone refreshes hold.
5. Experiment-local state machine with fixed hold durations 0 and 20 s.
   Without anchor, ordinary score >=1.5 refreshes the same timer.

The histogram adapter estimates every 5 s after 60 s elapsed history; before
that it uses the first readings/unit spread. It learns during occupancy.
Each entire recording prefix is processed without labels. The fixtures are
shorter than the default 12 h window (asserted), so no samples expire.
This is raw-sample estimator arithmetic, not production baseline bucket or
persistence behavior. Cold-start device passthrough is not simulated. All
labeled evaluation visits occur after histogram warmup.

This adapter directly composes existing stage classes, not the production
Detector. Candidate activity is a current scored run; episode-based candidate
continuation is not simulated. The new module and this adapter do not modify
registries, defaults, or the other agent's work. These distinctions must be
preserved when interpreting this as a proposed integration rather than a
production end-to-end validation.

## Trusted validation set

Only `labeled-walk-0915.db` and `labeled-loop-0915.db`. Bathroom sensor only;
labels used after replay for scoring. No fitting or label-selected parameters.
The 20 s hold was selected before replay to leave margin under the user's
roughly 30 s total release allowance, not selected by searching results.

## Results

| Visit | Anchor entry offset | Anchor clear, no timer | Anchor clear, 20 s timer |
|---|---:|---:|---:|
| Walk first | 1.693 s | 1.078 s | 21.143 s |
| Walk second | .016 s | 1.185 s | 21.252 s |
| Solo loop | .385 s | 6.859 s | 26.928 s |

Both anchor variants have **zero post-detection bathroom dropouts**, zero
positive frames in the second before each entry label, and **zero kitchen
re-triggers after clearing** within the bounded labeled evaluation spans.
The added scoring/energy filters do not delay entry further in these fixtures.
No-timer anchor occupancy exactly matches experiment 25's histogram+spread
tracker on both complete recordings.

The score-only control fares poorly: without a timer it has 229 later-kitchen
positive frames after first clearing in the walk, and 378 in the loop. It also
has three brief dropouts in the loop. With a 20 s timer it does not clear
between the two walk visits, and the loop clears about 84.89 s after exit.
Its apparently immediate first walk detection is not a valid latency success:
it was already occupied before that entry label.

The anchor's 20 s timer increases TW-positive frame fractions through allowed
release tails (52.71% walk, 40.16% loop); these are not new kitchen entries.
The same values without a timer are 3.85% and 7.74%. Do not report these
fractions as classification accuracy without separating tolerated release.

## Limits and validation

Entry offsets are relative to labels correlated with kitchen motion, not an
independent subsecond physical clock. The first 1.69 s offset remains unresolved.
Only three bathroom visits have reliable validation here; this is promising
fixture evidence, not broad reliability. An unchanged template can still
confuse same-range sources in an untested setting.

- Focused module tests cover initialization, weak motion, quiet retention,
  signal loss, unusable gates, missing/backward timestamps, and invalid inputs.
- Replay asserts no-timer anchor equivalence to experiment 25.
- Prefix checks recompute histogram estimates independently and verify output,
  score, and anchor score have no future-data dependency.

Run:

```sh
.venv/bin/python -m pytest -q tests/algo/test_motion_anchor.py
.venv/bin/python docs/research/experiments/26-motion-anchor-stack/replay.py
```

Full measurements: `results.json`.
