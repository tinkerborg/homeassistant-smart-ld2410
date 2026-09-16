# Experiment 4c: composite entry (arrival + suppressed leading edge)

Same four streams as 4b (script mix.py in ../4b-synthetic-overlap/, driver
extended in the scratchpad session); entry = shipped score/hysteresis AND
arrival gate (0.55×ceiling, min_frames 1, already shipped) AND suppressed
leading gate ≤ lead_gate_max. Hold/exit = shipped, unchanged; retention
NOT wired (failed under overlap, 4b).

## Verdict

**Clean win on the realistic mixes.** Kitchen-only never enters, the
genuine walk-in enters at exactly 22:04:01 with zero latency cost, and MAX
goes from a 5-minute false pre-latch to a correct single visit. SUM is the
exception and is an artifact of the mixing, not a detector failure.
lead_gate_max=1 is the right default.

## 1. Kitchen-only control — never enters

Shipped falsely latched 21:58:50→22:07:51 (541s). Composite: flat off the
whole 12 min. 2968 frames clear score≥3; **zero** have suppressed lead ≤1.
Pre-arrival lead histogram: g2:1562 g3:492 g4:22 — through-wall energy
always leads at g2+.

## 2. Bathroom control — no latency cost

Entry 22:04:01 identical to shipped; release 22:06:43 identical; 162s
occupied both ways. The lead condition goes true at 22:04:01, the same
frame the arrival gate clears — never the binding constraint on a genuine
walk-in (score alone would have fired at 22:03:39).

## 3. Mixes

| stream | shipped | composite |
|---|---|---|
| MAX | ON 21:58:50 → off 22:08:27 (578s) | ON **22:04:01** → off 22:08:27 (266s) |
| SUM | ON 21:58:50 → held past 22:10 (670s) | ON 21:58:50 → held (670s) — unchanged |

MAX behaves as the real world should: kitchen can't enter (lead g2/g3),
the genuine walk-in enters on time, one clean occupancy block.

SUM is not a detector result: additive clipping fabricates g0/g1 energy
existing in neither source stream — 709 pre-arrival frames with lead
g0/g1, 706 also score-hot. Even lead_max=0 doesn't help (enters 21:58:51).
Energies don't sum across scatterers; MAX is the meaningful mix, SUM a
known-invalid worst case.

## Departure hole — persists as expected, ~104s

Control releases 22:06:43 (on the label). MAX releases 22:08:27 (+104s).
Cause is the untouched hold path: post-departure MAX has 1610/1970 frames
under exit_score=1.5, but the longest continuous sub-exit run is 122s
against hold_s=30 — the kitchen person keeps poking the score back over
1.5 and cancelling the countdown. Kitchen-control alone shows the
identical 122s pattern (it's the through-wall signal holding the door
open, not residue of the genuine visit). SUM never releases (median
post-departure score 6.5, zero sub-exit frames).

## 4. lead_gate_max sweep

| lead_max | kitchen ctrl | MAX | bath ctrl |
|---|---|---|---|
| 0 | never | 22:04:01 (266s) | 22:04:01 (162s) |
| 1 | never | 22:04:01 (266s) | 22:04:01 (162s) |
| 2 | **21:58:50 (541s)** | **21:58:50 (578s)** | 22:04:01 (162s) |

0 and 1 behaviorally identical on every stream; 1 costs nothing and keeps
headroom for a genuine entry leading at g1 (sensor mounted farther from
the door). 2 collapses to shipped behavior — g2 is exactly where the
through-wall lead sits.
