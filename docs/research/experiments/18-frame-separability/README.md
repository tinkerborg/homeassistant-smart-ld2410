# Experiment 18: per-frame bathroom separability

This evaluates raw per-frame `move[0:9]` plus `still[2:9]` vectors. Training
uses only the older bathroom fixtures. The loop and walk recordings are held
out. The optional confirmation rule requires three consecutive positive
frames (about 0.3 s at this recorder's sampling rate); it is a diagnostic,
not a production state machine.

Run:

```sh
TZ=America/New_York ../../../../.venv/bin/python analyze.py > results.txt 2>&1
```
