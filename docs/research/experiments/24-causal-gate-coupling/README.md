# Experiment 24: causal per-gate temporal coupling

Run from this directory:

```sh
TZ=America/New_York ../../../../.venv/bin/python analyze.py > results.txt 2>&1
```

The statistic is fixed arithmetic: exponentially weighted Pearson correlation
of per-gate first differences over a causal 5 s history, with a 2 s decay and
0/0.5 s motion-to-still lags. Labels are evaluation only.
