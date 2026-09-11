# 50 — Phase 5: Prediction & Identity (Directional)

Not implementable until Phases 2–4 are proven live. This document fixes scope,
contracts, and first steps only; algorithms get their own design doc against
real data when the phase opens.

## 1. Short-horizon prediction

- Input: live tracks (30), adjacency graph, transition history.
- Model v1: counts. `T[from_room, edge, hour_bucket] → next_room`
  frequencies, Laplace-smoothed, decayed. Combined with current approach
  signal (centroid velocity toward an edge band) to emit:
  `occupancy_room_predicted {room, confidence, horizon_s, ts}` on the bus.
- Latency budget: prediction path in-process, < 100 ms from feature sample to
  event.
- Every prediction logged with outcome (arrival within horizon+2 s) —
  precision is measured continuously in production; consumers get the running
  precision as an attribute.
- Reference consumers (implementation examples, not platform): one
  hallway→room light, one display-wake with measured wake latency.

## 2. Identity

- Estimate per active track: distribution over residents + `guest` +
  `unknown`. Carried by evidence: bed state, phone BLE where available,
  arrival ledger (32). Radar features (span, centroid height proxy, cadence)
  refine only between candidates already plausible from evidence.
- Free labels: single-resident-home windows label all tracks.
- Policy: per-person automation requires `identity_conf ≥ 0.8`; otherwise
  household default. Wrong-person actions are treated as suite failures.
- `unknown` is mandatory in every output schema.

## 3. Downstream (kept out of scope until the above ship)

Activity states, preference learning from manual corrections, rule proposals.
Standing constraints already fixed by the overview: proposals require explicit
approval; learned behavior never changes silently; guest windows excluded
from preference data.
