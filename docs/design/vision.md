# Vision

Provision sensors and go. No gate tuning, no thresholds, no floorplan — the
only user input is which room each sensor lives in (HA area assignment).
Accuracy should feel like magic, arriving in stages:

- **Minute one**: behaves like a stock sensor (device passthrough) — never
  worse than what people already have.
- **Minutes in**: per-room noise baseline is learned; empty rooms read empty,
  still presence is retained.
- **A day in**: recorded reality has taught the system the home's quirks —
  doorway bleed, through-floor ghosts, mechanical noise sources — and the
  sensor fleet has inferred its own room-adjacency graph.

Homes change (furniture, seasons, remodels), so learning never stops; the
recorded-frame store (see storage.md) is the substrate that makes continuous
re-learning and every future improvement replayable and testable.

Tuning knobs exist as diagnostic surface for development — defaults must be
nobody's problem. Any design that requires users to keep rooms empty, tune
per-gate values, or draw maps is a regression from this vision.
