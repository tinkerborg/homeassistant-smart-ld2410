# 30 — Phase 3: Local Tracks, Handoffs, Learned Adjacency

House layer, part 1. Consumes the feature stream (10 §1.2). No coordinates,
no floor plans: adjacency is a learned graph over sensors.

## 1. Local tracks

Per sensor, from feature-stream samples with `occ = true`:

- A **local track** is a maximal sample sequence with inter-sample gap
  ≤ `track_gap_s` (default 3).
- Track record: `t0, t1, sensor_id, centroid path (downsampled), entry_edge,
  exit_edge` where entry/exit edge = `edge_band` at the first/last samples
  (`near`, `far`, `none`).
- Tracks shorter than `track_min_s` (default 2) are discarded for adjacency
  purposes (kept for attribution in 31).

## 2. Handoff detection

Candidate handoff = ordered pair (A ends on sensor S1, B starts on sensor S2,
S1 ≠ S2) with `0 ≤ B.t0 − A.t1 ≤ handoff_window_s` (default 12).

Weighting: `w = f_edge(A.exit_edge) · f_edge(B.entry_edge)` with
`f_edge(near|far) = 1.0`, `f_edge(none) = 0.3` — leaving/arriving through an
edge band is stronger evidence of a physical transition.

## 3. Adjacency learning

- Accumulate `H[S1][S2] += w` per candidate handoff (directed), with decay
  half-life `adj_half_life_days` (default 60).
- Null model: expected co-incidence rate if S1 endings and S2 startings were
  independent Poisson streams — `E[S1,S2] = rate_end(S1) · rate_start(S2) ·
  handoff_window_s · T_window`. Maintain per-sensor rates with the same decay.
- Edge exists when `H ≥ adj_min_count` (default 25) AND `H ≥ adj_lift ·
  E` (default lift 3.0). Edge removed when either condition fails after decay.
- Symmetrize for the graph used by the estimator (max of the two directions);
  keep directed counts for diagnostics.
- Manual adjacency list in options: entries are unioned in and never removed
  by learning; a manual `!forbid` entry removes a learned edge.

## 4. Outputs

- `adjacency(s1 TEXT, s2 TEXT, h REAL, e REAL, edge INT, updated REAL)` in the
  house DB.
- Diagnostic sensor `house_adjacency`: attribute = current edge list with
  lift values.
- Tracks table:
  `tracks(id, sensor_id, t0, t1, entry_edge, exit_edge, centroid_json)`.
  Retention `track_retention_days` (default 90).

## 5. Hidden-room inference (deferred within phase)

Blocked until adjacency is stable in production for ≥ 2 weeks. Design sketch
to be validated then: sensors adjacent via an uncovered space show handoffs
with systematically longer `B.t0 − A.t1` than direct neighbors; a latency
histogram per edge separates direct (< 4 s typical walking) from mediated
(4–20 s) edges; mediated edges get a synthetic room node, and an occupant
whose track ends into a mediated edge without a matching start is assigned
`last_known = synthetic node` with decaying confidence. Do not implement
ahead of that data.

## 6. Validation

1. Two weeks of live features on the installed fleet: learned graph matches
   the true house adjacency (hand-checked) with zero false edges at defaults;
   missing edges acceptable and listed.
2. Replay determinism: adjacency learning runs in replay from recorded
   features and reproduces the live graph.
3. Sensitivity report: edges' lift values, so threshold headroom is known
   before the estimator depends on the graph.
