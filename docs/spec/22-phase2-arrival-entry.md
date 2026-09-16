# 22 — Phase 2: Arrival-Gated Entry

Goal: occupancy begins only on arrival motion. A person entering the room
produces moving-channel energy near the sensor's observed ceiling; activity
attenuated by an intervening wall never does. Gating entry on arrival-scale
motion suppresses through-wall bleed without gate caps, floorplans, or
per-gate tuning. Acceptance criteria are §6.

## 1. Learned arrival reference

Per sensor:

- `move_ceiling`: a decayed high quantile of moving-channel energy across
  all gates and frames, tracked with the same bucketed, contamination-robust
  machinery as the baseline and persisted with it. It converges toward the
  strongest motion the sensor ever sees (saturation at 100 for any sensor a
  person walks in front of) and decays so a relocated sensor relearns.
- The ceiling's window advances only through buckets whose raw maximum
  moving energy reaches `ceiling_motion_floor` (default 60): empty time
  carries no arrival evidence, so it must not age the ceiling out. An
  unoccupied stretch of any length — a vacation — leaves the ceiling
  where the last real motion put it, while a genuine regime change
  (remount, different room) still replaces it over accumulated lived
  motion. The floor sits above the strongest observed through-wall bleed
  and below what any genuine arrival produces.

The reference is sensor-global, not per-gate: attenuation is absolute
physics on a 0–100 scale, and a per-gate reference would self-normalize
bleed-only gates into passing their own bleed.

## 2. Entry rule

At entry evaluation only (exit and hold per 20 §4):

- Arrival threshold: `arrival_frac × move_ceiling` (default 0.6).
- Entry is admitted only when, within the candidate window (frames since
  the triggering activity began, the same window as 23 §1), the moving
  energy of at least one admitted gate reaches the arrival threshold in at
  least `arrival_min_frames` frames (default 3).
- Until then the hysteresis state machine treats the frame as below
  `enter_score`. Suppressed candidates record episodes (result value
  `rejected_arrival`) and feed classification and the feature stream.
- Precedence: after gate-class exclusion and the energy floor (23). A
  candidate must pass all three.
- Once entered, arrival gating plays no role: exit remains score/hold
  driven, so a person decaying to faint stillness is never dropped by this
  rule.
- Cold start: while `move_ceiling` is unlearned, arrival gating is inactive
  and entry behaves per 10 (device-bit passthrough phase included). The
  rule only ever tightens a learned system, never blocks a fresh one.

## 3. Leading edge (diagnostic)

`leading_gate`: the nearest gate whose moving energy exceeds its learned
quiet level during the candidate window. Recorded on every episode and
exposed as an occupancy attribute. In-room arrivals lead at the nearest
gates; through-wall activity physically cannot. Not an entry condition:
recorded so accumulating evidence can qualify it as one.

## 4. Departure release

While occupied, hold refresh is unchanged. A separate release path exists
for the case where an occupant leaves while an out-of-room source keeps
weak evidence alive: when the only evidence across a full hold window is
arrival-failing (no admitted gate reaching the arrival threshold) and the
leading gate sits beyond every gate that carried the occupancy, occupancy
releases at the end of that window. This path is gated on its own
acceptance (§6.5) — until labeled departure recordings validate it, it is
inactive; the still-presence asymmetry rule outranks it permanently: any
evidence pattern a genuinely still occupant can produce must never release.

## 5. Options

`arrival_frac` (0 disables the rule), `arrival_min_frames`, and
`ceiling_motion_floor` (0 restores an ungated window); diagnostic-tier.
One global default each, tuned only by validation evidence.

## 6. Acceptance

1. Corpus sweep: zero genuine dwell entries lost across all recorded
   sensors (still-presence asymmetry rule — any loss is a failure, not a
   trade).
2. Labeled sessions: every toilet entry admitted at normal latency; every
   stove, island, hall-walk-by, and empty window produces no entry.
3. Entry latency on genuine entries not worse than pre-22 replay (an
   arrival's first frames already carry arrival-scale motion).
4. 24-hour replay: entries occur only in clusters consistent with genuine
   visits; none inside labeled out-of-room intervals.
5. Departure release (§4): enabled only on labeled departure recordings
   showing release without a single still-occupant false release.

Measured against the recorded corpus and label events in
`validation/22-v3-arrival-entry.md`.
