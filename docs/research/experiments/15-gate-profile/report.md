# Experiment 15: gate-profile shape

Question: does a per-frame (or ≤5 s) statistic of the SHAPE of the
9-gate energy profile separate in-room occupancy from through-wall
activity well enough to be a memoryless hold signal? Scripts:
`data.py` (class spans), `stats.py` (the statistics), `analyze.py`
(distributions + single-threshold separation), `runs.py` (run lengths),
`holds.py` (hold simulation, stove case, quiet minute, cat),
`spanstats.py`, `quiet.py`, `raw_peek.py`.

## Verdict

**No. The profile is a much better instantaneous discriminator than any
level rule, and it still cannot be the hold — because the failure it
does not fix is the one that matters.**

- **It is a real, large improvement at range.** On the bathroom sensor
  the longest continuous "looks occupied" run inside the
  stove-case far-kitchen span drops from **338 s** (level rule
  `max(still[2], still[3]) ≥ ambient+20`) to **38 s** (`n_gates ≥ 4`) —
  and inside the through-wall morning from 255 s to 30 s, and inside the
  post-departure decay tail from 113 s to 5 s. Frame-level, the best
  statistics reach TPR 0.84 at FPR_TW 0.09 / FPR_EMPTY 0.01.
- **It collapses completely at short range.** The labeled stove + island
  session (23:10:54–23:13:46, person on the far side of the wall, close
  in) produces **172 s of continuous, 100 %-IN-looking profile** on every
  still statistic tried, level rules included. Not a marginal pass — the
  profile is indistinguishable from the toilet profile, sustained.
- **So no gap timer works.** A hold must survive the longest not-IN
  stretch inside a genuine visit (**52.6 s**, the 09:50–10:05 hair-clip
  span; 36.9 s in the 22:04 visit) and must release inside every
  through-wall episode. The worst through-wall episode refreshes
  continuously for 172 s. Required T ≥ 53 s, permitted T < 0 s.
  **Margin is negative by the whole width of the problem.** It is the
  same overlap the project already had at single-gate level (~95 s TW vs
  ~43 s IN gaps), narrowed on the far cases and *not* fixed on the near
  one.
- **"Shape" is not what is doing the work.** Every normalised shape
  ratio (near-fraction, centroid, spread, peak falloff, shoulder/tail
  ratios) is matched or beaten by simply reading one deep gate:
  `still[5] ≥ ambient+6` scores J = 0.730 against the best shape ratio's
  0.733, and `still[4]` 0.714. The usable signal is *"is there still
  energy behind gate 3"*, not the profile's shape. Normalising by the
  peak throws away amplitude and buys nothing.
- **Template matching is dead.** The IN and TW mean templates built from
  the labeled sessions have cosine similarity **0.99** (still) and 0.978
  (move) to each other. There is no template axis to project onto;
  cos_margin peaks at J = 0.68 and does so by proxying amplitude.
- **Move channel carries nothing.** Best move statistic on the bathroom
  sensor reaches J = 0.58 (that is `mass` — "is the person moving"), and
  every shape statistic is ≤ 0.49. On the living room the move channel is
  worthless (J ≤ 0.32). Move shape is not a discriminator on this
  hardware.

What a spec would need: profile depth is a good **arming/suppression**
input (it cheaply kills the long-range false retention that dominates
the bathroom's failure log), but the near-wall case must be solved by
something that is not radar geometry — shielding, a second sensor, or a
cross-room ownership rule. Do not build a hold on it.

## Method

Classes per the brief. Ground truth from `tools/viz/export_fixtures.py`
`TRUTH` plus the label events in `labeled-sessions-0909-d06e.db`. Label
spans are trimmed by `min(27 s, half the span)` at the end (arrival
motion leads a label flip), island spans by a further 5 s, and the
contaminated stove interval at 23:08:24 is dropped. The `empty` label
span 23:27:07–23:33:18 is kept intact *including* its ~2 min
post-departure decay tail — that tail is genuine empty-room ground truth
and is the cheapest test of whether a statistic survives a departure.
The living-room IN span starts 21:05:30 (skipping the saturated minute
after the power cycle).

Ambient floor = per-gate median over that fixture's EMPTY frames; the
two stove-case fixtures have no EMPTY span, so they use the per-sensor
median over all EMPTY frames of that sensor. Results are reported with
and without floor subtraction. Statistics are computed on the raw
9-vector and on its 2 s and 5 s trailing mean.

Frame counts pooled per sensor: D0:6E — IN 15 977, TW 43 683,
EMPTY 24 699. FD:68 — IN 25 714, EMPTY 7 800, PET 3 000 (no TW span
exists for the living room).

## What the raw frames look like

Bathroom sensor, still gates 2–8, typical:

```
toilet / in-room     0  0  100 100 100  60  28  15   9
far kitchen (TW)     0  0   66  75   18   8   6   5   6
stove, close (TW)    0  0   79 100   74  29  17   8   6
empty                0  0    7   5    5   5   5   5   5
post-departure decay 0  0  100 100   36  15   8   6   5
```

The user's intuition is right about the *far* through-wall case — it
dies one gate behind its peak while the in-room profile carries to
gate 5 — and wrong about the *near* one: the stove at close range makes
a full-depth profile. It is also inverted from the stated expectation in
one respect: the in-room profile is the one that reaches far gates,
because it saturates gates 2–4 and spills; the far through-wall profile
is the narrow one.

Living room, seated occupant: a much weaker, broader profile peaking
around gate 3–5. The cat is a clean far-only profile, gates 4–6 with
gates 2–3 flat at floor.

## Distributions and single-threshold separation

### D0:6E (bathroom), still, 2 s mean, floor subtracted

Percentiles of the statistic per class:

```
stat         class        n    p5      p25      p50      p75      p95
mass         IN       15977  13.6   178.5    349.2    395.4    421.9
mass         TW       43683   0.0     1.2      4.9     82.1    197.8
mass         EMPTY    24699   0.0     0.1      0.6      2.4     86.7
near_frac    IN       15977   0.37    0.47     0.51     0.73     0.92
near_frac    TW       43683   0.00    0.51     0.86     0.95     1.00
near_frac    EMPTY    24699   0.00    0.00     0.71     0.96     1.00
centroid     IN       15977   2.74    3.09     3.62     3.81     4.26
centroid     TW       43683   2.64    2.80     3.00     3.88     7.00
centroid     EMPTY    24699   2.63    2.87     3.00     4.62     8.00
spread       IN       15977   0.82    1.10     1.40     1.51     1.70
spread       TW       43683   0.00    0.47     0.82     1.24     2.23
spread       EMPTY    24699   0.00    0.00     0.50     0.86     2.11
peak_gate    IN       15977   2       3        3        3        3
peak_gate    TW       43683   2       3        3        3        8
peak_gate    EMPTY    24699   3       3        3        4        8
fall1        IN       15977   0.11    0.57     0.98     1.00     1.00
fall1        TW       43683   0.00    0.00     0.13     0.23     0.80
fall1        EMPTY    24699   0.00    0.00     0.00     0.17     0.55
fall2        IN       15977   0.00    0.21     0.47     0.65     0.79
fall2        TW       43683   0.00    0.00     0.00     0.05     0.23
fall2        EMPTY    24699   0.00    0.00     0.00     0.00     0.07
n_gates      IN       15977   1       4        6        7        7
n_gates      TW       43683   0       0        0        3        4
n_gates      EMPTY    24699   0       0        0        0        3
deep_mass    IN       15977   0.8    16.6     77.0    112.7    138.9
deep_mass    TW       43683   0.0     0.0      0.5      4.2     23.3
deep_mass    EMPTY    24699   0.0     0.0      0.0      0.3      1.6
lead_frac    IN       15977   0.38    0.495    0.495    0.495    0.53
lead_frac    TW       43683   0.00    0.00     0.31     0.46     0.53
lead_frac    EMPTY    24699   0.00    0.00     0.00     0.35     0.53
shoulder     IN       15977   0.03    0.36     0.99     1.00     1.00
shoulder     TW       43683   0.00    0.00     0.11     0.21     1.00
shoulder     EMPTY    24699   0.00    0.00     0.00     0.20     0.58
tail         IN       15977   0.00    0.19     0.50     0.67     0.86
tail         TW       43683   0.00    0.00     0.00     0.05     0.80
tail         EMPTY    24699   0.00    0.00     0.00     0.00     0.10
g4           IN       15977   0.1    22.6     91.0     95.0     95.0
g4           TW       43683   0.0     0.0      0.2      7.3     22.4
g4           EMPTY    24699   0.0     0.0      0.0      0.2      9.9
g5           IN       15977   0.0    11.5     42.1     61.1     74.9
g5           TW       43683   0.0     0.0      0.0      2.4     12.8
g5           EMPTY    24699   0.0     0.0      0.0      0.0      1.0
cos_in       IN       11669   0.65    0.93     0.95     0.96     0.98
cos_in       TW       42402   0.05    0.65     0.77     0.94     0.96
cos_margin   IN       11669  -0.033  -0.004   -0.003   -0.001    0.029
cos_margin   TW       42402  -0.073  -0.065   -0.020    0.008    0.024
```

`lead_frac` sitting at exactly 0.495 for the entire IN interquartile
range is the saturation signature: gates 2 and 3 both pinned at 100,
residual 93/95. Through-wall reaches 100 at gate 3 but leaves gate 2 at
60–90, so the ratio falls. That is the only shape feature that is
genuinely about shape and not amplitude — and it is also the one that
costs the most recall (TPR 0.81).

Best single threshold, IN vs (TW ∪ EMPTY), by smoothing window
(floor subtracted). `J` = TPR − max(FPR_TW, FPR_EMPTY):

```
                       win=0 s                    win=2 s                    win=5 s
stat          thr   TPR  FPRtw FPRem  J    thr   TPR  FPRtw FPRem  J    thr   TPR  FPRtw FPRem  J
n_gates       ≥4   0.826 0.080 0.008 .746  ≥4   0.838 0.091 0.009 .747  ≥3.8 0.845 0.092 0.007 .753
fall2        ≥.074 0.864 0.134 0.022 .731 ≥.076 0.873 0.141 0.034 .733 ≥.078 0.885 0.141 0.031 .744
g5            ≥6   0.836 0.106 0.008 .730  ≥5.6 0.839 0.105 0.007 .734  ≥5.7 0.847 0.104 0.003 .743
tail         ≥.074 0.853 0.128 0.017 .725 ≥.074 0.861 0.143 0.038 .718 ≥.071 0.876 0.151 0.048 .724
g4           ≥18   0.789 0.082 0.019 .707 ≥18.6 0.785 0.071 0.016 .714 ≥18.9 0.795 0.068 0.015 .727
lead_frac   ≥.479  0.817 0.118 0.055 .699 ≥.481 0.814 0.105 0.064 .709 ≥.481 0.815 0.095 0.052 .720
deep_mass     ≥7   0.864 0.178 0.013 .686  ≥6.2 0.872 0.185 0.014 .687  ≥8.3 0.853 0.147 0.007 .706
g2           ≥68   0.759 0.083 0.021 .676 ≥70.2 0.753 0.071 0.020 .682 ≥71.8 0.751 0.062 0.019 .689
shoulder    ≥.253  0.801 0.131 0.055 .670 ≥.257 0.802 0.146 0.084 .656 ≥.257 0.804 0.153 0.107 .651
cos_margin  ≥.003  0.792 0.132 0.039 .660 ≥.003 0.797 0.132 0.070 .664 ≥.003 0.800 0.120 0.064 .680
mass         ≥89   0.882 0.242 0.047 .640 ≥90.5 0.882 0.241 0.044 .640 ≥87.2 0.888 0.246 0.049 .642
g3           ≥44   0.848 0.231 0.056 .618 ≥44.2 0.848 0.229 0.054 .619 ≥46.2 0.845 0.226 0.044 .619
centroid    ≥3.03  0.770 0.292 0.163 .479 ≥3.01 0.785 0.416 0.360 .369 ≥3.02 0.785 0.452 0.428 .333
near_frac   ≤.844  0.879 0.459 0.651 .228 ≤.839 0.866 0.430 0.557 .309 ≤.844 0.883 0.430 0.530 .353
peak_gate     ≤3   0.941 0.745 0.436 .197   ≤3  0.950 0.781 0.566 .170   ≤3  0.956 0.809 0.636 .147
```

Smoothing buys almost nothing — 2 s and 5 s move J by ±0.02 on the
depth statistics, and actively *hurt* the position statistics
(`centroid` .479 → .333, `peak_gate` .197 → .147) because averaging
mixes an empty frame's arbitrary argmax into the window. There is no
short-window statistic here that is not already available per frame.

Without floor subtraction all the *ratio* statistics collapse (the
~5-count floor lifts every gate, so every ratio tends to 1:
`shoulder` J .656 → .480, `tail` .718 → .069, `fall2` .733 → .480), but
the *absolute depth* statistics are essentially unchanged —
`deep_mass ≥ 26` raw scores J = .686 against .687 floored,
`g5 ≥ 10.6` raw is identical to `g5 ≥ 5.6` floored. **The usable
statistic does not need a learned floor.** That is the strongest
practical finding here.

### D0:6E, move channel

Nothing works. Floored, best is `mass ≥ 14` at J = 0.578 (win 5 s) —
i.e. "the person is moving", which is not a hold signal. Every shape
statistic is ≤ 0.49; `fall1`/`fall2`/`shoulder`/`tail` all sit at
FPR ≈ 0.35–0.55. Unfloored, `cos_margin ≥ 0.003` reaches J = 0.69 with
FPR_EMPTY 0.000, but TPR only 0.70 and it only fires while the occupant
is actually moving. Move profile shape is not a discriminator.

### FD:68 (living room), still, 2 s mean, floor subtracted

No TW span exists for this sensor; the negatives are EMPTY and PET.

```
stat         class        n    p5      p25      p50      p75      p95
mass         IN       25714   1.2    14.4     20.6     52.5    263.4
mass         EMPTY     7800   0.0     0.5      1.1      2.5     66.3
mass         PET       3000   0.0     0.9      7.8     44.7    187.4
centroid     IN       25714   3.14    3.87     4.40     4.85     5.19
centroid     EMPTY     7800   2.00    3.26     4.67     5.27     7.14
centroid     PET       3000   2.00    3.97     5.20     5.31     5.44
n_gates      IN       25714   0       0        1        4        6
n_gates      EMPTY     7800   0       0        0        0        3
n_gates      PET       3000   0       0        1        2        4
deep_frac    IN       25714   0.12    0.29     0.49     0.62     0.76
deep_frac    EMPTY     7800   0.00    0.26     0.71     1.00     1.00
deep_frac    PET       3000   0.00    0.49     0.87     0.94     1.00
shoulder     IN       25714   0.00    0.44     0.73     1.15     2.51
shoulder     EMPTY     7800   0.00    0.00     0.00     0.00     0.87
shoulder     PET       3000   0.00    0.00     0.00     5.80    70.82
g3           IN       25714   0.0     2.0      3.1     14.6     85.0
g3           EMPTY     7800   0.0     0.0      0.0      0.0      0.7
g3           PET       3000   0.0     0.0      0.0      0.0      0.6
g4           IN       25714   0.0     1.6      2.9     12.7     68.8
g4           EMPTY     7800   0.0     0.0      0.0      0.0      0.3
g4           PET       3000   0.0     0.0      0.0      4.2     27.6
```

Best thresholds (win 2 s, floored): `g3 ≥ 1` J = 0.857,
`g4 ≥ 0.67` J = 0.838, `shoulder ≥ 0.107` J = 0.817,
`fall2 ≥ 0.011` J = 0.753, `mass ≥ 6.2` J = 0.726, `deep_mass ≥ 3`
J = 0.697. Again a single gate beats every shape ratio. Unfloored these
thresholds are ~+6–7 counts and `g3 ≥ 7` still scores J = 0.857 — the
living-room floor is flat enough that raw gates work directly.

Note how small the numbers are: the living-room occupant's median
residual is 2–4 counts. Everything on this sensor rides on a per-gate
floor known to ~1 count.

## Run-length view (still, 2 s mean, floor subtracted)

Longest continuous "looks IN" run inside each negative span (a hold is
falsely refreshed for that long), and longest continuous "looks NOT IN"
run inside each IN span (a hold must survive that long).

### D0:6E — `n_gates ≥ 4`

```
fixture                   class span                len  IN%   longIN  longNOT
throughwall-morning       EMPTY 04:55:00-04:59:30    270   0.0     0.0    269.9
throughwall-morning       TW    05:00:00-05:46:00   2760   3.8    29.7    552.3
throughwall-morning       EMPTY 05:47:00-06:04:59   1079   0.0     0.0   1078.9
bathroom-visit-2204       EMPTY 21:55:00-22:03:00    480   0.0     0.0    479.8
bathroom-visit-2204       IN    22:04:01-22:06:43    162  57.0    77.4     36.9
bathroom-visit-2204       EMPTY 22:07:30-22:11:59    269   0.0     0.0    269.0
stove-case-0913           IN    09:24:00-09:25:15     75  90.7    67.8      4.2
stove-case-0913           TW    09:25:20-09:50:00   1480  11.2    37.7    292.0
stove-case-0913           IN    09:50:00-10:05:30    930  81.5   523.3     52.6
labeled-sessions          TW    21:22:20-21:22:33     13  88.2    11.1      1.4
labeled-sessions          TW    21:23:23-21:23:31      8 100.0     8.3      0.0
labeled-sessions          IN    21:24:23-21:24:52     29 100.0    28.5      0.0
labeled-sessions          TW    23:10:54-23:12:08     74 100.0    74.1      0.0
labeled-sessions          TW    23:12:41-23:13:14     33 100.0    32.7      0.0
labeled-sessions          IN    23:15:27-23:22:10    402  97.3   198.7      6.8
labeled-sessions          EMPTY 23:27:07-23:33:18    372   5.7     4.6    291.6
```

Taken as one continuous through-wall episode (the stove and island
labels are separated only by a 6 s `none`), 23:10:54–23:13:46 is
**100 % IN, one 171.9 s run, zero not-IN frames**. `deep_mass ≥ 6` and
the level baseline give the same 171.9 s; `g5 ≥ 6` gives 166.7 s.

### D0:6E — comparison across rules

```
rule                          worst IN gap   worst false run   far-kitchen   TW-morning   empty-decay
                              (need T >)     (23:10 episode)   09:25-09:50   05:00-05:46  23:27-23:33
level max(g2,g3) ≥ amb+20        45.3 s          171.9 s          338.1 s      254.7 s       112.9 s
still n_gates ≥ 4                52.6 s          171.9 s           37.7 s       29.7 s         4.6 s
still g5 ≥ amb+6                 52.0 s          166.7 s           37.1 s       55.2 s         3.8 s
still deep_mass ≥ amb+6          40.9 s          171.9 s           84.6 s       68.2 s         6.1 s
still lead_frac ≥ 0.481          33.1 s            0.0 s           27.3 s       30.8 s        17.4 s
lead_frac AND n_gates ≥ 4        52.8 s            0.0 s           27.3 s       11.2 s         4.6 s
```

Two things to read off this table:

1. Against the *far* negatives the profile is a 4–9× improvement over
   the level rule and the gap timer is comfortable: `n_gates ≥ 4` at
   T = 60 s holds every IN span and releases inside the far-kitchen span,
   the through-wall morning and the decay tail with 4–5× margin.
2. `lead_frac` is the only statistic that kills the 23:10 episode
   outright (0 % of it passes) — because the stove never saturates
   gate 2. But it costs recall elsewhere: it opens a 33.1 s hole in the
   23:15 toilet span, and ANDing it with a depth term pushes the worst IN
   gap to 52.8 s while its own worst false run on the remaining TW spans
   is 27.3 s. That ordering (52.8 > 27.3) is still infeasible, and the
   0 s on the 23:10 episode is one sensor's saturation geometry on one
   session — not something to build a spec on. It is the most
   interesting lead in this experiment and the least trustworthy.

**Plainly: there is no gap timer that holds every IN span and releases
every TW/EMPTY span.** On `n_gates ≥ 4` the requirement is T > 52.6 s
and the constraint is T < 0 s. Even excluding the labeled-sessions
fixture entirely, the requirement is T > 52.6 s against a worst false
run of 37.7 s — still infeasible, by 15 s.

### Stove case, 09:24 visit → 09:25:20 walk-out → far kitchen

Hold simulation from the walk-out (all still, 2 s mean, floored):

```
rule              hold   first release after walk-out   re-latches   held % of far-kitchen span
n_gates ≥ 4        30 s   09:25:42  (+22 s)                  5            29.3 %
n_gates ≥ 4        60 s   09:26:12  (+52 s)                  5            39.4 %
n_gates ≥ 4        90 s   09:26:42  (+82 s)                  5            49.6 %
g5 ≥ 6             30 s   09:25:42  (+22 s)                  6            28.0 %
g5 ≥ 6             60 s   09:26:12  (+52 s)                  6            40.2 %
deep_mass ≥ 6      60 s   09:26:12  (+53 s)                  5            54.6 %
level max(g2,g3)   60 s   09:26:16  (+56 s)                  5            66.1 %
```

The profile-based hold **first releases 22 s after the walk-out at
T = 30 s, 52 s at T = 60 s** — i.e. essentially T seconds after the last
in-room frame, which is what it should do; the profile stops looking
in-room within ~2 s of the person leaving. But it **does re-latch, five
or six times, and spends 29–50 % of the 24-minute far-kitchen span
held**. The re-latches are the bursts around 09:29, 09:33, 09:44 and
09:46 where the kitchen person comes close enough to the wall to light
gates 2–4. Compared to the level rule (66 % held, one continuous 338 s
block) this is a large improvement and still a failure: the room reads
occupied for minutes at a time while empty.

### FD:68 — `shoulder ≥ 0.107` vs alternatives

```
rule                  span                      len   IN%   longIN  longNOT
shoulder ≥ 0.107      IN    21:05:30-21:20:00    870  70.0   236.2     73.2
                      EMPTY 21:20:30-21:27:30    420   3.4     3.4     98.4
                      PET   21:28:00-21:33:00    300  23.1    10.0    119.9
                      EMPTY 21:33:30-21:39:30    360  10.4     5.1     83.4
                      IN    21:39:40-21:55:00    920  96.3   320.0     16.1
                      IN    09:10:00-09:23:30    810  99.3   296.6      2.5
g3 ≥ amb+1            IN    21:05:30-21:20:00    870  69.9   407.3    104.8
                      EMPTY 21:20:30-21:27:30    420   0.6     0.7    137.5
                      PET   21:28:00-21:33:00    300   1.3     1.2    100.6
                      EMPTY 21:33:30-21:39:30    360   0.7     1.7    241.3
                      IN    21:39:40-21:55:00    920  90.5   232.9     17.5
                      IN    09:10:00-09:23:30    810  99.5   623.3      1.8
level max(g2,g3)      IN    21:05:30-21:20:00    870  20.6    19.5    260.5
                      EMPTY (both)                     0.0     0.0    419.9
                      IN    21:39:40-21:55:00    920  40.4   179.2    126.9
                      IN    09:10:00-09:23:30    810   3.2    25.8    724.9
```

Here a gap timer *is* feasible — barely. `shoulder ≥ 0.107` needs
T > 73.2 s (the first seated span) and its longest EMPTY false run is
5.1 s, so any T from ~80 s up holds both seated spans and costs at most
~85 s of trailing occupancy after an empty-room blip. `g3 ≥ amb+1` needs
T > 104.8 s with a 1.7 s worst false run — an even wider window. The
level baseline is hopeless here (724.9 s hole inside a confirmed
in-room span).

But see the next section before trusting either number.

## Living room: the very-still occupant

**The profile survives full absorption — but only by about three
counts.** During the 21:49 minute the shipped detector wrongly released,
the raw still vector averages

```
21:49 quiet minute   0 0 7.6 8.8 8.5 8.8 6.6 6.3 5.9
empty 21:22          0 0 7.2 5.9 5.4 5.5 5.5 5.4 5.4
empty 21:35          0 0 7.7 5.9 5.5 5.5 6.1 6.5 6.1
```

a broad ~+3-count lift across gates 3–5, shaped exactly like a seated
body and nothing like the empty floor. `shoulder ≥ 0.107` flags **100 %
of that minute** while flagging only 3–10 % of the EMPTY spans, and the
whole 21:39:40–21:55 span has a longest not-IN gap of 16.1 s — so the
profile does *not* need bridging across the still minute the shipped
detector lost.

The caveat is size. That minute sits at the **88th percentile of the
EMPTY distribution on mass, 85th on deep_mass, 95th on shoulder** — it
is inside the empty tail, not clear of it. 30 s smoothing does not move
it (86th / 85th / 94th). What separates it from the empty tail is not
level but *persistence*: the lift is present in every frame of the
minute, whereas EMPTY frames cross the same thresholds sporadically (a
3–5 s run at most). So the living-room result is "profile + a short
persistence requirement", and it depends on a per-gate floor accurate to
about one count, learned from the one EMPTY period in the one fixture
this sensor has. Treat FD:68's J values as optimistic; there is one
empty session behind them.

Also note what this says about the bathroom: D0:6E's in-room signal is a
saturated 100/100/100 and the living room's is +3 counts. The two
sensors are not operating in the same regime, and no threshold transfers
between them.

## Pet

The cat is a **far-only profile** and is separated by the near gates,
not by depth:

```
21:30:29  0 0  6  5 35 99 57 18 10     centroid 5.30
21:30:54  0 0  7  5 18 54 35  9  6     centroid 5.30
21:31:19  0 0  6  5 13 38 26  7  6     centroid 5.25
21:32:10  0 0  6  6 10 25 20  8  5     centroid 5.36
```

Gates 2–3 sit at floor throughout; a clean unimodal peak at gate 5.
Consequences: depth-only statistics latch on it — `g5 ≥ 6` flags 48 %
of the cat span, `deep_mass ≥ 6` 53 %, with a continuous 82–159 s run —
while anything requiring near-gate energy rejects it completely
(`level max(g2,g3)` 0.0 %, `g3 ≥ amb+1` 1.3 %, 1.2 s longest run).
`shoulder ≥ 0.107` splits the difference at 23 % / 10 s runs. A
profile rule intended to hold the living room must carry a near-gate
term or it will hold on the cat for two and a half minutes.

On the bathroom sensor a depth-only rule would have the same exposure
to any far-gate mover; no pet data exists there.

## What did not work, for the record

- **Near-mass fraction** (the statistic the brief led with): inverted.
  IN p50 = 0.51, TW p50 = 0.86 — through-wall is the *narrow*
  near-concentrated profile because in-room saturates and spills. Best
  J = 0.353.
- **Centroid, peak gate, spread**: J ≤ 0.48, and they degrade under
  smoothing. Peak gate is 3 for essentially every class.
- **Template cosine**: templates are 0.99 parallel; cos_margin J = 0.66
  and behaves as an amplitude proxy.
- **All normalised shape ratios**: matched or beaten by one raw deep
  gate; and they need an accurate floor, which the raw gate does not.
- **Move channel, every statistic**: J ≤ 0.58 on the bathroom, ≤ 0.32 on
  the living room.
