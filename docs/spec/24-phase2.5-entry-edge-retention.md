# 24 — Phase 2.5: Entry Leading Edge & Still-Presence Retention

Goal: close the two failure modes that survive arrival gating — through-wall
activity that clears the arrival bar (entry side), and a genuinely still
occupant whose signal the device's internal background absorbs (hold side).
A real entry must approach the sensor; a real occupant cannot leave without
motion. Acceptance criteria are §5.

## 1. Leading-edge entry condition

The leading gate of a candidate is the nearest gate whose moving-channel
residual — after the same isolated-gate neighbor-support suppression the
score path applies — reaches `k`, taken as the minimum over the candidate's
frames (never sticky: a single-frame spike at a near gate must not pin the
value; suppression is what disqualifies it).

- Entry is admitted only when the candidate's leading gate ≤ `lead_gate_max`
  (default 1). An in-room person walks through the near gates on the way
  in; activity originating beyond an intervening wall physically cannot
  light them.
- Applies at entry evaluation only, after gate-class exclusion, the energy
  floor (23), and arrival gating (22). Suppressed candidates record
  episodes (result `rejected_leading_edge`) and feed classification and the
  feature stream.
- The moving channel carries data at every gate; the still channel carries
  none at gates 0–1 (device limitation) and plays no part in the leading
  edge.
- Inactive while the baseline is unlearned (passthrough behavior per 10).
- `lead_gate_max` is this-room geometry, not physics: the default suits a
  sensor mounted at the room boundary. The rule is sound only where the
  room's genuine entries and its through-wall activity lead at different
  gates; a per-sensor learned test for that separation is required before
  the rule can default on for arbitrary installs, and no valid label-free
  test is yet known (outcome-conditioned proxies fail: sustained dwells
  are dominated by through-wall activity). Until one is validated, the
  rule is enabled by the `lead_gate_max` option alone.

## 1a. Ownership

A qualifying entry — one admitted with the leading-edge condition
satisfied — establishes room ownership: the fact that a person demonstrably
approached through the room's entry gates, which activity beyond a wall can
never do. Ownership is what separates "evidence from the occupant" from
"evidence from a neighbor" after entry, when their per-frame signatures
are indistinguishable.

- Ownership begins at a qualifying entry and ends at release. It begins
  DISARMED: while disarmed, retention (§2) refreshes hold, so a still
  occupant can never be released — there is no way out of the room that
  does not produce motion.
- Departure arming: once near-band activity has been absent for
  `quiet_s` (default 10, the entry walk-in has settled), a fresh burst of
  at least `cross_n` (default 20) near-band frames within 20 s arms
  release — the occupant has demonstrably re-crossed the room's entry
  gates. While armed, only attributed evidence (score above exit AND a
  near-band lead within `grace_s`, default 60) refreshes the release
  countdown; evidence leading beyond the entry band never does. A
  neighbor cannot light the near band, so it can neither arm nor block.
- Retention decay (§2) remains the release path when no re-crossing ever
  occurs.
- Without ownership (entry admitted by fallback in a no-separation room),
  retention and arming play no part; hold behaves per 20 §4.

## 2. Still-presence retention

Per gate, over the still channel: a fast EMA (`tau_fast`, default 2 s) and a
slow EMA (`tau_slow`, default 60 s); the retention statistic is
`max(0, fast − slow)`, normalized by a per-gate noise normalizer (robust
EMA of absolute frame-to-frame differences, ~10 s time constant, clamped
to a minimum of 0.1) and peak-held with a `tau_peak` (default 90 s) decay.
The positive part is essential: the absolute difference is a change
detector that a departure drives to its maximum, indistinguishable from
presence; the signed form reads ~0 through every vacancy and stays
elevated through occupant stillness. The peak-hold bridges sub-threshold
gaps inside a genuine sit.

- While ownership (§1a) is alive, a normalized retention statistic ≥
  `retention_on` (default 20) at any gate that carried the occupancy
  refreshes hold exactly as scored evidence does. The device absorbing a
  motionless person no longer ends the visit: the statistic remains
  separated from ambient through full stillness.
- Retention never initiates occupancy, never refreshes hold for gates the
  current occupancy never included, and never operates without ownership:
  a neighbor's through-wall activity elevates the statistic MORE than a
  genuine still occupant does, so on its own it answers neither "is
  someone here" nor "is the room now empty" — it is trusted only inside
  an owned visit.
- Release of an owned room requires the retention statistic below
  `retention_off` (default 10) at the occupancy's gates for the whole hold
  window, in addition to the score conditions of 20 §4 — with far-leading
  evidence excluded from both, per §1a.

## 3. Channel information limits

Hardware facts the statistics honor:

- Still energies exist only at gates 2–8; gates 0–1 report zero always.
- A channel latched at a constant (observed: still pegged 100 at a gate for
  hours in an empty room after a corrupted internal calibration) carries no
  information; its statistics are meaningless until the device is
  power-cycled. Detection of that state is diagnostic-tier future work; no
  rule in this spec depends on a latched channel behaving.

## 4. Options

`lead_gate_max` (−1 disables the leading-edge rule), `retention_on`,
`retention_off` (0 disables retention release-gating), `tau_fast`,
`tau_slow`, `tau_peak`, `quiet_s`, `cross_n`, `grace_s`; all
diagnostic-tier, one global default each, tuned only by validation
evidence.

## 5. Acceptance

1. Corpus sweep: zero genuine dwell entries lost and zero genuine dwells
   released early across all recorded sensors (still-presence asymmetry
   rule — any loss is a failure).
2. Through-wall morning hour (recorded, ground truth empty with adjacent
   kitchen activity): zero entries. The two labeled genuine toilet entries:
   admitted at unchanged latency.
3. Still-occupant recording (recorded living-room evening, occupant seated
   through device absorption): no occupancy drop across the seated span;
   the empty reference windows in the same recording produce no occupancy.
4. Entry latency on genuine entries not worse than pre-24 replay.
5. Retention statistic separation (occupied vs empty, per sensor) reported
   with margins in the validation report.
6. Overlap: on the synthesized occupant+neighbor stream, the occupancy
   timeline matches the pure-occupant control — entry on the genuine
   walk-in, release at the genuine departure plus hold, the neighbor
   neither entering, blocking, nor extending. The neighbor-only control
   never enters.
7. Ownership interplay: the seated still-occupant recording releases only
   at the occupant's true exit (retention decay), never mid-visit; the
   neighbor's evidence never refreshes an owned room's release countdown.
8. Separation learning: per sensor, the confirmed-vs-fizzled leading-gate
   histograms and the resulting enable/disable decision are reported; a
   sensor without proven separation runs fallback behavior and shows no
   regression against pre-24 replay.

Measured against the recorded corpus and label events in
`validation/24-v1-entry-edge-retention.md`.
