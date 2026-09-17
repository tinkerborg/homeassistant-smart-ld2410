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

## Post-deploy recording with experiment 20 same-gate balance

`postdeploy_balance.py` adds the experiment 20 rule as an **optional new-anchor
condition** in this same stack adapter: any gate 2–8 must have raw motion >=40
and motion/(motion+still) >=1/3. It compares that option with the original
anchor on `post-deploy-0915.db`, using the existing scorer, lone-gate suppression,
energy floor, histogram estimator, and hold logic. Only bathroom readings enter
inference. The reconstructed labels are not independent timing ground truth.
No production integration code is changed.

| Configured hold | Original: occupied frames in 115 s false window | With balance | New kitchen anchor? |
|---|---:|---:|---|
| 0 s | 984 | **0** | No |
| 20 s | 1,150 | **108** | No; remaining frames are release tail |
| 30 s | 1,150 | **208** | No; remaining frames are release tail |

With 20/30 s hold, occupancy is still true at the reported false event because
the departure timer has not expired. The distinction is that no new occupied
transition occurs there and the balance variant subsequently clears. The
original variant reacquires kitchen evidence and stays occupied throughout the
window. The separate experiment 30 replay shows the three trusted bathroom
entries and clear times unchanged at zero extra hold.

Reproduce:
`.venv/bin/python docs/research/experiments/26-motion-anchor-stack/postdeploy_balance.py`
Output: `postdeploy-balance-results.json`.

This is the experiment adapter, not an exact replay of the deployed detector's
baseline state and configured hold value, which were not exported. The timing
of the recorded live event is authoritative; the adapter's simulated state is
a mechanism check.
