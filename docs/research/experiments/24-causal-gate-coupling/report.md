# Experiment 24: causal per-gate temporal coupling

## Question and scope

Can a bathroom-only, per-gate temporal relationship between motion and still
separate in-room activity from through-wall activity? This is a bounded
descriptive replay. Labels are evaluation only; there is no fitting, template
selection, label-selected threshold, kitchen input, release timer, or
intentional wait.

## Fixed arithmetic

At each 100 ms grid time, gates 2–8 are resampled from the recorded bathroom
sensor. For each gate, the score is an exponentially weighted Pearson
correlation of first differences over the preceding 5 s, with a 2 s decay.
The second fixed variant compares motion 0.5 s earlier with still now. A gate
is included only when motion-difference SD is at least 0.5 and still-difference
SD is at least 0.05. The reported coupling is the median of included gates.
The amplitude control is the same weighted mean still level. A score is
undefined during startup until the full 5 s history exists or across a raw
timestamp gap. The causal prefix check passed.

## Results

The strongest requested simultaneous fixture is `labeled-walk-0915`: coupling
median was 0.068 in-room and 0.068 through-wall, with p10–p90 ranges −0.040…0.181
and −0.024…0.157. Its descriptive pooled AUC was 0.504 at lag 0 and 0.537 at
the 0.5 s lag. The fixed amplitude control was 0.978, so temporal coupling
added no separation while amplitude was already strong in this recording.

On `labeled-loop-0915`, coupling AUC was 0.486 at lag 0 and 0.356 at 0.5 s,
versus 0.972 for amplitude. In-room and through-wall medians were 0.050/0.045
at lag 0. The older labeled sessions were directionally adverse: coupling
medians were 0.049 in-room and 0.082 through-wall, while amplitude medians were
40.1 and 34.9. The empty through-wall morning was also near zero coupling
(median 0.027 during TW, 0.014 during EMPTY), showing that a low coupling value
does not establish vacancy or a wall signature. The separate confirmed toilet
visit had coupling median 0.040 versus 0.009 in adjacent EMPTY, but this was a
small descriptive shift with broad overlap.

## Conclusion and limits

This fixed per-gate first-difference relationship does not separate in-room
from wall activity in the critical wife-in-kitchen / two-bathroom-entry walk,
and it is weaker than the amplitude control on both new recordings. It does
not support an occupancy prototype or a new release rule. The negative result
is consistent with experiment 17, but the statistic differs: experiment 17
used rolling whole-window level/variability baselines and many same/adjacent
gate correlations at 10/30 s, while this run uses one fixed per-gate EW
first-difference median and one causal 0.5 s lag.

The 5 s history is an explicit information horizon, so this replay cannot
claim near-imperceptible or sub-second response. Shortening it would change
the statistic and require a separate bounded experiment; no latency claim is
made here. Results are saved in `results.txt`; rerun with the command in
`README.md`.
