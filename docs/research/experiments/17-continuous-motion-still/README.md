# Experiment 17: continuous motion–still relationships

This is the broader follow-up to experiment 16. It does not detect motion
events. It computes rolling move/still correlations in fixed causal windows,
including both streams leading, and compares them with a same-window level,
location, variability, and autocorrelation baseline.

Run from this directory:

```sh
TZ=America/New_York ../../../../.venv/bin/python analyze.py > results.txt 2>&1
```

The 10 s and 30 s windows are evaluated by whole-fixture holdout. One-second
anchors overlap, so window counts are descriptive and are not independent
trials.
