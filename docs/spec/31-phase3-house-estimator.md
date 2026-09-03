# 31 — Phase 3: House Estimator

House layer, part 2. Explicit probabilistic bookkeeping — no learned
parameters in v1 beyond what 30 provides. Pure module, replayable from
recorded features + evidence.

## 1. State

- `rooms`: configured map sensor_id → room (multiple sensors per room
  allowed). Exterior rooms flagged (`exterior: true`) — the only rooms where
  count may change, plus explicit arrival evidence.
- Per room r: occupancy belief `p[r] ∈ [0,1]` and expected count `c[r] ≥ 0`.
- House count `N = Σ c[r] + c_unaccounted`, changed only by §3 rules.
- Per-room `last_transition_ts`, `vacancy_confidence`.

## 2. Update loop (event-driven, plus 1 Hz tick)

Per feature sample / evidence event:

1. **Sensor evidence.** For sensor s in room r with confidence q:
   detection ⇒ `p[r] ← p[r] + (1 − p[r]) · q · w_radar`; sustained
   non-detection decays `p[r]` toward 0 with time constant `tau_clear[r]`
   (default 120 s; bathroom-class rooms configurable higher).
2. **Transition coupling.** On a handoff-shaped event (30 §2) between rooms
   r1→r2: move belief mass — `p[r2] ← max(p[r2], min(p[r1], q))`, decay
   `p[r1]` fast (`tau_handoff` = 10 s). Non-adjacent (per graph) simultaneous
   rises are NOT coupled; the weaker one is a suppression candidate (§4).
3. **External evidence** (32): applied as direct sets/holds per its semantics
   table (bed occupied pins `c[room] ≥ 1` and holds `p`; door contact spikes
   transition likelihood for its configured room pair; CO2 windows adjust
   retroactive labels only, never live state).

## 3. Conservation

- `N` increments on: exterior-room entry pattern (exterior door evidence, or
  first detection in an exterior room with no interior donor), arrival events.
- `N` decrements on the reverse pattern.
- Invariant enforcement, every tick: if `Σ ceil(p[r]) > N`, suppress lowest-
  confidence rooms down to N — suppressed rooms get `p` capped at 0.4,
  `suppressed_sources` set, and a `label = auto_false(conservation)` written
  to the source sensor's episode row.
- If evidence pins all N occupants (beds + arrival ledger) and a room outside
  the pinned set detects: cap + label likewise. These labels are the training
  feed for Phase 4.

## 4. Ghost suppression

Learned pair table (house DB): for sensor pairs (S_ghost, S_source) where
detection on S_ghost within a fixed gate band co-occurs with a strong track on
S_source at rate ≥ `ghost_lift` (3.0) over `ghost_min_count` (25) episodes —
same null-model machinery as 30 §3, keyed by (sensor, gate band) instead of
edges. While S_source has an active strong track, S_ghost detections inside
the learned band are attributed: excluded from `p[room(S_ghost)]`, listed in
`suppressed_sources`, episode labeled `auto_false(attributed:S_source)`.
Covers the upstairs-through-floor and island cases at the house level.

## 5. Vacancy

`vacancy_confidence[r]` rises with: time since last detection relative to
`tau_clear`, no inbound handoff path from occupied rooms (graph reachability
weighted by p), and supporting evidence (CO2 flat, if mapped). House-empty
event requires every room's vacancy confidence ≥ `vacancy_floor` (0.9) and
`N = 0` by the ledger. Wrong high-confidence vacancy is the cardinal failure:
the replay suite must show zero across all recordings before any consumer is
documented as safe to arm on it.

## 6. Outputs

Per 10 §4. All parameters above are options with the stated defaults;
per-room `tau` overrides allowed.

## 7. Validation

1. Replay full recorded history: person-count trace matches hand-reconstructed
   truth for sampled days; zero false confident-vacancy.
2. Conservation labels: spot-check ≥ 50 auto_false labels, ≥ 95% correct
   (bad labels poison Phase 4).
3. Degradation: estimator output with any single sensor stream removed stays
   correct with reduced confidence (test by replay with streams masked).
4. Ghost pairs: island + upstairs recordings produce the pair entries and
   suppression on replay.
