# 21 — Phase 2: Energy-Ceiling Boundary Learning

Goal: locate the room boundary per sensor from the physics that walls
attenuate returns — in-room gates occasionally see near-saturated energy,
through-wall gates never do. Candidate fix for through-wall sustained dwell.
Acceptance criteria are §5.

## 1. Statistic

Per gate, move channel (motion produces the strong returns; still saturates
rarely even in-room):

- `ceil_q`: decayed upper quantile (q99) of episode peak raw energy (raw, not
  residual — the ceiling is absolute physics, baseline-independent).
- `n_epi`: decayed episode count. Same half-life as 20 (`stats_half_life_days`).

Update at episode close from `episodes.peak` per gate (extend episode capture
to store per-gate peak raw energy: `gate_peaks BLOB`, 9 bytes).

## 2. Boundary inference

Raw ceilings cannot be compared directly across gates: return energy falls
with range regardless of walls (near fourth-power in free space), so an
uncompensated drop threshold is a distance threshold wearing a wall's
clothes. The wall signature is *excess* attenuation relative to the sensor's
own falloff trend.

Run daily per sensor:

1. Fit the sensor's falloff: robust log-linear fit of `log(ceil_q[g])`
   against `log(range_g)` over gates with `n_epi ≥ n_ceil_min` (default 10)
   and `ceil_q` below saturation (`< ceil_sat`, default 95 — clipped gates
   carry no slope information). Slope is the median of the pairwise slopes;
   the intercept places the line at the top of the cloud, because what the
   fit must predict is the energy an *unobstructed* gate at that range
   reaches, and the gates a wall has pushed below the trend are the signal
   rather than a pull on it. Under three such gates, no inference runs: two
   points fit any line.
2. Compensated profile: `e[g] = ceil_q[g] / fit[g]` for gates with
   sufficient `n_epi`; gates without evidence are skipped, not treated as
   low.
3. Find the smallest k ≥ 2 such that `e[g] < ceil_drop` (default 0.45) for
   **all** evaluated g ≥ k, with at least one evaluated gate ≥ k. If none,
   boundary = null (whole range in-room).
4. Require persistence: k stable for `boundary_confirm_days` (default 3)
   consecutive evaluations before taking effect.
5. Publish `boundary_gate = k − 1` (last in-room gate).

Attenuation through a wall applies to every gate beyond it, so the signature
is a sustained deficit, not a dip: a single low-ceiling in-room gate (a
corridor of space no one crosses laterally) does not create a boundary
because step 3 requires all further evaluated gates low. A genuinely
never-saturating far in-room gate that also sits below the falloff fit
remains the main validation risk (§5.3).

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
  `ceil_profile` (the 9 compensated values `e`, null where a gate has no
  evidence), `n_epi`, `confirmed_days`.
- Options: `ceil_drop`, `n_ceil_min`, `boundary_confirm_days`, `ceil_sat`.

## 5. Acceptance

0. Falloff immunity: a synthetic pure free-space profile with no wall yields
   boundary = null (`test_free_space_falloff_alone_is_not_a_boundary`), and no
   healthy recorded sensor confirms a boundary below its observed dwell gates.
1. Island recordings: bathroom sensor learns a boundary at/below the wall
   gate; sustained island dwell suppressed on replay; real bathroom
   still-presence retained.
2. Every healthy sensor: learned boundary is null or provably at a
   real wall (compare against known room dimensions); zero cases of an
   in-room gate suppressed.
3. Far-couch scenario: a real far-gate in-room dwell zone does not get
   truncated (if it does, raise `ceil_drop` or mark feature per-sensor
   opt-out; record the failure in the suite either way).
4. Ship path: implement → replay across all recorded sensors → report → enable
   by default only on pass; otherwise remains per-sensor opt-in with
   `max_gate` as the documented fallback.
5. The replay pass must also produce spec 22's V1 position-stability report
   (same recordings, one pass) so distance-first filtering can be evaluated
   without a second data-collection round.
