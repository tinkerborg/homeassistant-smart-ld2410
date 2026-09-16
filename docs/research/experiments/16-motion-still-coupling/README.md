# Experiment 16: motion–still temporal coupling

This experiment tests whether the relationship between a motion burst and the
following still-energy response differs between a person in the room (`IN`)
and activity beyond the wall (`TW`). It does not interpret a burst as entry or
exit evidence.

Run from this directory with the repository virtualenv:

```sh
TZ=America/New_York ../../../../.venv/bin/python analyze.py
```

The script detects separated motion maxima, extracts the peak gate and peak
motion strength, then measures the still response after the maximum. Results
are reported per analysis window and per labeled span; frames are never
random-split. The `baseline` comparison uses peak gate, motion strength, and
the pre-existing still state. The temporal comparison adds sampled future
response features at 0.5–5 seconds after the motion maximum. Peak selection
and response curves are descriptive only.
