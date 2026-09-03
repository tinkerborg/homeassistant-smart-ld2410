# 21 — Phase 2: Energy-Ceiling Boundary Learning

Goal: locate the room boundary per sensor from the physics that walls
attenuate returns — in-room gates occasionally see near-saturated energy,
through-wall gates never do. Candidate fix for through-wall sustained dwell.
Status: must be validated against recordings before it gates anything.

## 1. Statistic

Per gate, move channel (motion produces the strong returns; still saturates
rarely even in-room):

- `ceil_q`: decayed upper quantile (q99) of episode peak raw energy (raw, not
  residual — the ceiling is absolute physics, baseline-independent).
- `n_epi`: decayed episode count. Same half-life as 20 (`stats_half_life_days`).

Update at episode close from `episodes.peak` per gate (extend episode capture
to store per-gate peak raw energy: `gate_peaks BLOB`, 9 bytes).

## 2. Boundary inference

Run daily per sensor, only when every gate ≤ candidate boundary has
`n_epi ≥ n_ceil_min` (default 10):

1. Normalize: `c[g] = ceil_q[g] / max_g(ceil_q)`.
2. Find the smallest gate index k ≥ 2 such that `c[g] < ceil_drop` (default
   0.45) for **all** g ≥ k. If none, boundary = null (whole range in-room).
3. Require persistence: k must be stable for `boundary_confirm_days` (default
   3) consecutive evaluations before taking effect.
4. Publish `boundary_gate = k − 1` (last in-room gate).

Rationale for the shape: attenuation through a wall applies to every gate
beyond it, so the signature is a sustained drop, not a dip. A single
low-ceiling gate inside the room (empty corridor of space no one crosses
laterally) does not create a boundary because step 2 requires all further
gates low — but a genuinely never-saturating far *in-room* gate past it would
block detection of a true wall; this is the main validation risk (§5.3).

## 3. Effect

- Gates > `boundary_gate` are forced OUT_OF_ROOM regardless of dwell class
  (this overrides 20 §3 and is the island fix).
- Precedence: manual `max_gate` (if set) > learned boundary > dwell class.
- Boundary changes are logged events; a boundary retreat (k decreasing) that
  would suppress a gate currently in an active episode defers until the
  episode closes.

## 4. Storage & entities

- `gate_stats` gains `ceil_q REAL, n_epi REAL`.
- `sensor.<name>_boundary_gate` (diagnostic): learned value, attributes
  `ceil_profile` (9 normalized values), `confirmed_days`.
- Options: `ceil_drop`, `n_ceil_min`, `boundary_confirm_days`.

## 5. Validation (gating — this feature ships disabled until these pass)

1. Island recordings: bathroom sensor learns a boundary at/below the wall
   gate; sustained island dwell suppressed on replay; real bathroom
   still-presence retained.
2. Every currently-healthy sensor: learned boundary is null or provably at a
   real wall (compare against known room dimensions); zero cases of an
   in-room gate suppressed.
3. Far-couch scenario: a real far-gate in-room dwell zone does not get
   truncated (if it does, raise `ceil_drop` or mark feature per-sensor
   opt-out; record the failure in the suite either way).
4. Ship path: implement → replay across all recorded sensors → report → enable
   by default only on pass; otherwise remains per-sensor opt-in with
   `max_gate` as the documented fallback.
