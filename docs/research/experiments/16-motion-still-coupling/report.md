# Experiment 16: motion–still temporal coupling

**Status: done — NO RELIABLE GAIN FROM TESTED PEAK-RESPONSE FEATURES.**

## Question

After matching a motion burst by its peak gate and motion strength, does the
still-energy response over the next few seconds differ between a person in the
bathroom (`IN`) and activity beyond the wall (`TW`)? The intended use would be
an additional presence/retention clue. A motion burst is not treated as an
entry or exit event.

## Data and method

This is bathroom-sensor data only. The living-room recordings have no labeled
through-wall class and are not used to make a TW claim. The input is the real
LD2410 `move` and `still` gate vectors from the labeled fixtures already used
by experiment 15:

| Fixture | IN | TW | Notes |
|---|---:|---:|---|
| `bathroom-visit-2204-d06e` | yes | no | confirmed bathroom visit |
| `throughwall-morning-d06e` | no | yes | kitchen activity through wall |
| `stove-case-0913-d06e` | yes | yes | walk-out, then farther kitchen activity |
| `labeled-sessions-0909-d06e` | yes | yes | includes the close stove/island case |

Motion maxima were found from the maximum move gate after a 0.4 s smoothing
window, with one retained raw maximum per 2.5 s neighbourhood and a minimum
raw strength of 18. These are separated analysis windows; sustained plateaus
can therefore contribute repeated maxima at that spacing, and they should not
be read as independent isolated motion events. A 5.5 s margin was kept at
each label boundary. The still baseline is the mean from 0.7–0.1 s before the
maximum. Response features use the still value at the motion gate at 0.5, 1,
2, 3, and 5 s after the maximum, plus local-gate change. Only maxima at gate
2 or farther are used for the primary analysis: gates 0–1 have structurally
zero still output on this hardware. The complete −0.7 s through +5.35 s
window had to be covered with no timestamp gap over 0.55 s.

Peak selection is retrospective and is used only to make comparable events.
The response measurements are causal once the decision time reaches each
look-ahead (for example, the 5 s feature is available at `t+5 s`).

The baseline model includes motion strength/mass, peak gate, motion centroid,
and the pre-existing still level/mass/centroid. The temporal model adds the
still changes after the peak. This makes the comparison test incremental
temporal information instead of rewarding a generic level or profile
difference.

## Results

There were 1,382 retained analysis windows: 478 IN and 904 TW. 388 windows
(166 IN, 222 TW) had peak gate 2 or farther and formed the primary analysis.
282 windows (20.4%) had motion strength at the 95-count saturation boundary;
the nonsaturated results were reported separately.

The primary check was whole-fixture holdout, using only fixtures containing
both classes in the held-out data:

| Held-out fixture | Baseline | Baseline + temporal change | Baseline + absolute future level |
|---|---:|---:|---:|
| `labeled-sessions-0909-d06e` | 0.624 | 0.640 | 0.649 |
| `stove-case-0913-d06e` | 0.878 | 0.852 | 0.843 |

The hard close stove/island fixture is the important result. Matching IN and
TW peaks within the same peak gate and within `max(5, 20%)` motion strength
gave 24 pairs in `labeled-sessions` after restricting to still-active gates:

- median IN-minus-TW still change at 0.5 s: −0.8 counts
- at 1 s: 1.7 counts
- at 2 s: 5.5 counts
- at 3 s: 5.7 counts
- at 5 s: 1.6 counts
- the middle 80% of the 2 s differences ran from −12.6 to +18.2 counts

The late close stove/island interval (23:10:54–23:13:46) versus **both**
labeled toilet intervals (21:24:20–21:25:00 and 23:15:27–23:22:37) had 104
usable windows (80 IN, 24 TW). A model trained on the other fixtures and
evaluated with its sign frozen scored 0.624 baseline, 0.640 with temporal
changes, and 0.649 with the closely related future-level variant. This is
effectively the whole-fixture result: the explicit late stove/island test
does not produce a stronger independent result. In the `stove-case` fixture,
which has more mixed data, the matched temporal changes were broad and the
medians were negative (−3.3 counts at 2 s, −10.5 at 3 s).

The pooled temporal-change features were near chance after excluding
saturated motion peaks (AUC 0.51–0.53; the 2–5 s deltas were 0.51–0.53).
The level variant is closely related to the delta variant plus the pre-peak
still state, so its small numeric difference does not establish a separate
absolute-level mechanism.

## Verdict

This does not show a reliable gain from the tested peak-response features.
The move and still streams do contain short-term relationships, but the
post-motion changes are mostly zero or broad-overlapping in the close-wall
examples. The small held-out differences are unstable across fixtures, and
the hard close-wall sample is too small and serially sampled to support a
claim either way.

The experiment therefore does not justify adding a rule such as “motion must
be followed by one of these sampled still responses,” and it gives no basis
for using motion as a proxy for a person leaving. A controlled recording with
matched in-room and through-wall bursts could test other temporal features
more cleanly, but these tested peak-response features are not the next
algorithmic direction.

Reproduction:

```sh
TZ=America/New_York ../../../../.venv/bin/python analyze.py
```
