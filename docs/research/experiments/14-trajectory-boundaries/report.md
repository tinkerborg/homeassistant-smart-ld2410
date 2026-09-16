# Experiment 14: trajectory boundary learning

Question: do movement trajectories over gates recover room structure
(door, interior, wall) label-free? Scripts: traj2/3.py (centroid
extraction + march segmentation), t14long/entry/ab.py.

## Verdict

**Partially — split per sensor, not per algorithm.**

- **Living room (FD:68): learns the structure.** Arrival-conditioned
  histograms independently recover door ≈ gate 5-6, seat ≈ gate 2-3 on
  two databases. Fixes the live entry regression config-free: the fixed
  lead≤1 rule rejects 3/3 strong prod arrivals (all lead gate 2,
  including the known-genuine 21:39 walk-in); the learned
  arrival-origin band admits all of them.
- **Bathroom (D0:6E): degenerate.** The room is ~2 gates deep — genuine
  entries have no room to travel, while the kitchen person beyond the
  wall travels freely; in-room and through-wall occupy the same gate
  band (toilet centroid 2.4-3.0 vs stove 2.6-4.0). 290 h yields no door,
  no wall. Trajectories cannot serve that sensor; it stays on the
  suppressed-lead near-band rule (which its entries do satisfy) plus
  hardware shielding as the other lever.

Key methodological findings:
- **Marginal origin/terminus histograms carry NO structure** (origin ≈
  terminus ≈ presence — you exit as often as you enter). The signal
  appears only when origins are conditioned on *first travel after ≥60 s
  of silence* (arrivals). That conditioning is the whole result.
- **Argmax-gate tracking is unusable** (teleports 4+ gates between 0.5 s
  cells; produced "travel" during demonstrable sitting). Residual-
  weighted centroid + density/monotonicity gating made trajectories
  legible.
- Event-level rule (dense run, ≥4 s, monotonicity ≥0.8, net ≥2 gates)
  recovers both genuine entries and kills 4 of 5 through-wall episodes,
  but adds one bathroom FP — not dominant over the fixed rule there.

## Data requirements

Arrival-origin peak visible after ~10 arrivals (1-2 days, living room);
confident band at 20-30 arrivals (3-7 days). Bathroom: 13 arrivals in
290 h — never converges. Arrival rate is the binding constraint.

## Deliverable

Replace `lead_gate_max` with a learned arrival-origin band on sensors
that accumulate ≥20 arrivals; fall back to the default near band until
then. Strictly better than hand-set gates where it applies; does nothing
for the bathroom through-wall problem (position there is provably
degenerate — amplitude and shielding own that case). IP note: adjacent
to the intent-mapping patent family; review before public shipping.
