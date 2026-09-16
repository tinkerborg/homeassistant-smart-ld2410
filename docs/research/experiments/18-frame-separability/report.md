# Experiment 18: per-frame bathroom separability

**Status: complete — neither tested model meets sub-second entry plus reliable through-wall rejection.**

## Method

Two supervised linear ridge models, trained only on older bathroom fixtures:
59,660 labeled frames (15,977 IN, 43,683 TW). `amp` uses four energy maxima;
`full` uses all nine move gates and still gates 2–8. Both use training-only
median/MAD scaling and fixed per-sample regularization. Thresholds maximize
training true-positive rate minus false-positive rate, breaking ties toward
the higher threshold: amp 0.3951, full 0.2999. No new-data tuning.

Only bathroom sensor D0:6E:81:D2:5D:A6 supplies features. Kitchen and other
sensor readings are not inputs. New loop/walk recordings are held out.
A fixed three-consecutive-frame confirmation is computed over the entire
stream before evaluating labeled intervals, with no ground-truth resets.
Triples must span at most 0.38 s; at 10 Hz they normally add about 0.2 s after
the first positive. This is a classifier diagnostic, not an occupancy latch.

Room-transition labels were inferred using radar traces, so apparent delays
relative to them cannot independently establish sub-second detection latency.
AUC measures ranking (0.5 is chance, 1 perfect), not classification accuracy
at the frozen threshold. Correlated frames are not independent trials.

## New bathroom-then-kitchen loop

`labeled-loop-0915.db`: 6,152 bathroom frames, median spacing 0.102 s,
no gaps over 0.55 s. Frames end at 19:30:15 despite labels extending to 19:32;
missing time is not graded. User occupies bathroom for 78 s, kitchen for 62 s,
with hall and living-room periods around them; wife remains in living room.

| Model | IN/TW AUC | Missed IN frames | False TW frames | Apparent entry raw / confirmed |
|---|---:|---:|---:|---:|
| Amplitude | 0.979 | 17/779 (2.2%) | 44/620 (7.1%) | 1.81 / 1.91 s |
| Full vector | 0.976 | 26/779 (3.3%) | 33/620 (5.3%) | 2.63 / 2.84 s |

Neither meets the entry target relative to the labels. The kitchen false
positives include post-departure persistence, not necessarily independent new
entries: amplitude has one 4.3 s false run; full has four false runs, longest
2.6 s (two remain after confirmation). Both models have zero positive frames
in the labeled hall and living-room segments. That is useful separation on
this recording, but not the requested overall solution.

## Simultaneous-occupancy walk

`labeled-walk-0915.db`: 14,958 bathroom frames, median spacing 0.102 s,
four gaps over 0.55 s. Primary evaluation uses only periods when the wife's
kitchen location and the user's location are both explicit; unknown gaps are
excluded. IN means user in bathroom while wife is in kitchen. TW means
bathroom empty while kitchen is active. The long earlier living-room period
is a secondary diagnostic, not primary vacancy truth.

| Model | IN/TW AUC | Missed IN frames | Total false TW frames |
|---|---:|---:|---:|
| Amplitude | 0.982 | 21/421 (5.0%) | 6/571 (1.1%) |
| Full vector | 0.983 | 1/421 (0.2%) | 310/571 (54.3%) |

The three TW intervals last 12, 36, and 9 seconds:

| Model | First interval | Middle interval | Final interval |
|---|---:|---:|---:|
| Amplitude | 0/120 | 6/361 (1.7%) | 0/90 |
| Full vector | 86/120 (71.7%) | 208/361 (57.6%) | 16/90 (17.8%) |

The full model's longest middle-interval false run lasts 20.7 s; confirmation
still leaves a 14.1 s false run. Its apparent entry delays of 0.00 and 0.02 s
are not successful fast entries: it was already positive within the preceding
second for both visits. Amplitude's entry delays are 1.69 and 0.02 s raw,
1.85 and 0.22 s confirmed. It rejects much more kitchen activity but is late
on one entry. High ranking AUC does not erase frozen-threshold failures.

## Older mixed-fixture holdouts

Each model is retrained excluding the entire evaluated old fixture; threshold
selection also excludes that fixture.

| Held-out fixture | Model | AUC | IN missed |
|---|---|---:|---:|
| stove-case-0913-d06e | Amplitude | 0.898 | 14.6% |
| stove-case-0913-d06e | Full vector | 0.843 | 22.4% |
| labeled-sessions-0909-d06e | Amplitude | 0.580 | 64.6% |
| labeled-sessions-0909-d06e | Full vector | 0.479 | 37.5% |

The older near-wall problem remains. This only tests two linear probes and
old-data-selected thresholds; it does not prove that every nonlinear model
or other single-sensor technique must fail. No production code changed.

## Verification and reproduction

The parent independently reran the script. Review corrected a fraction-as-
percent formatting error in the first draft; saved results and tables above
use percentages and explicit counts. `run_span_min` sums last-minus-first
run timestamps, excluding each run's final sampling interval: it is a lower
bound, not exact occupied time. Isolated positive frames still count in the
frame metrics, even though their run span is zero.

Run from this directory:

```sh
TZ=America/New_York ../../../../.venv/bin/python analyze.py > results.txt 2>&1
```
