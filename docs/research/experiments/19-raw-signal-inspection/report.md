# 19. Raw signal inspection: spatial ordering is not a wall signature

Status: descriptive inspection complete; no classifier trained or detector changed.

## Scope

Inspect raw bathroom move/still traces in the Sept 15 loop and simultaneous
walk, then the Sept 9 close stove/island session. Labels only annotate and
select comparison periods. No model weights or detection thresholds are fitted.
The user requires near-imperceptible response and automatic operation without
labeled training or a manually supplied room boundary.

Plots:

- `loop-raw.png`: all gates, both channels, unsmoothed.
- `overlap-raw.png`: same view while wife remains in kitchen.
- `old_close-raw.png`: older high-energy stove/island versus toilet.
- `spatial-contrast.png`: raw gate-2/gate-3 scatter and normalized spatial slope.

## Observation and arithmetic

The recent bathroom visits load the nearer still gates strongly. Kitchen
activity often peaks farther out. A directly measurable contrast is

    D = still[2] - still[3]
    G = D / (still[2] + still[3])

G is a normalized spatial slope, insensitive to uniform multiplicative scaling
of both readings. It uses one frame; calculating it adds no evidence window.
Clipping at 100, additive background, and differing gate responses complicate
its interpretation. This is not a Doppler/phase measurement or proof of a wall.

In the older labeled close stove and island intervals, gate 3 exceeds gate 2
in every evaluated frame (742 stove frames, 328 island frames, using the
existing conservative label trims). This is a real visual distinction despite
high energies in both rooms. However, the long toilet interval also has this
ordering in 26.4% of its frames, including a continuous 33.28 s run. The loop's
kitchen interval has the opposite, bathroom-like ordering in 54.5% of frames.
Quiet background and departure tails can also have that ordering. A sign veto
therefore fails in both directions. Detailed values: `measurements.txt`.

The normalization is descriptive, not a fitted separator. This ordering was
already adjacent to experiment 15's near-fraction measurement; the new plots
clarify its limits rather than establish a new method.

## What this does NOT establish

Gate number measures a radial distance band, not room membership. A band may
intersect multiple rooms. These recordings and contrasts do not identify a
room boundary automatically. Even a perfect distinction at this placement
would not establish a through-wall signature that generalizes to another
placement. The user explicitly pointed this out during inspection; no fixed
near-gate rule should be promoted from this observation.

The remaining physical hypothesis would need a distinction that persists at
comparable range and signal level, rather than distance itself. This inspection
does not establish such a distinction. It also does not prove none exists.

## Reproduction

Scripts use NumPy and Matplotlib (verified with Matplotlib 3.11.2) and the
existing experiment-15 fixture loader for older conservative label spans.
Set TZ=America/New_York when using that loader. With those dependencies:

    python inspect_signals.py
    TZ=America/New_York python measure.py > measurements.txt
    TZ=America/New_York python plot_contrasts.py

No other sensor supplies plotted or measured inputs. New labels are partly
inferred from radar timing; plots cannot independently validate physical
sub-second entry times. Longest-run spans are last-minus-first timestamps,
not exact sample-duration integrals. Loop labels extend past available frames;
no measurements are fabricated for missing time. No live algorithm changed.
