# Shipped technique inventory

Every mechanism in the shipped detector, what it exists to fix, and how
strongly it has been proven. Evidence grades: **clean** (corpus-wide
report, zero failures), **partial** (experiment-level evidence with
named failure modes), **untested** (no experiment or validation report).
Stage names match `docs/spec/00-overview.md` §4.3; files live under
`custom_components/smart_ld2410/algo/`.

| Stage (file) | Fixes | Evidence |
|---|---|---|
| `quantile_floor` (baseline/floor.py) | per-gate ambient drift | untested; exp 3 measured it as the loser (11 min to converge at g2, never at g3) |
| `tail_spread` (baseline/spread.py) | idle noise scoring z≈15 | untested; exp 3 found spread the worse contaminant (1.0 → 4.75/7.0 occupied) |
| `move_ceiling` (baseline/ceiling.py) | per-gate arrival reference normalizing bleed into itself | partial; exp 6 (1 simulated vacation): collapses to bleed level in ~24 h, motion-gated fix validated but unbuilt |
| `run_score` (scoring/runs.py) | stuck gate 0 pinning occupancy | partial; only inside exp 4a (1 bathroom hour) |
| `lone_gate_suppression` (scoring/suppression.py) | single samples rescuing a stuck gate | partial; exp 4a: kills 94 % of gate-0 hot frames |
| `dwell_class` (gates/dwell.py) | hand-typed geometry; a moved sofa never unlearning | untested; decayed classes appear only as context in 21-v1 |
| `portal_class` (gates/portal.py) | doorway gates demoted to bleed | untested; exp 11 falsified the related outcome-conditioned proxy |
| `energy_ceiling` (gates/boundary.py) | still person behind a wall vs in front of one | partial; 21-v1 (3 sensors / 118 h): safe but inert, 2 of 3 sensors clip at 100; ships disabled |
| `gate_exclusion` (gates/exclusion.py) | hallway pass-by entering through a wall | untested; spec 20 §7 validation plan has no report |
| `energy_floor` (entry/energy_floor.py) | faint through-wall candidates | **clean**; 23-v1 (3 sensors / 14.9 days) zero genuine-dwell loss |
| `arrival` (entry/arrival.py) | weak through-wall activity entering | partial; 22-v3 (3 sensors / ~20 days) clean at 0.55/1, but spec defaults 0.6/3 lost 17 dwells and exp 4b calls 0.55/1 a coin flip against bleed |
| `leading_edge` (entry/leading_edge.py) | kitchen activity entering the bathroom | partial; exp 4a (1 real hour) + 4c (synthetic overlap) clean; rejects genuine deep-room walk-ins (exp 14); label-free enablement test falsified (exp 11) |
| `retention` (presence/retention.py) | chip absorbing a still occupant | partial; exp 1 + 4e show signedness and 90 s peak hold load-bearing; reads higher on an empty room under a neighbour (exp 4b), so hold-only |
| `ownership` (presence/ownership.py) | neighbour vs occupant indistinguishable after entry | partial; exp 4e only, 5 streams (2 synthetic) |
| `crossing_arming` (presence/arming.py) | room latched by a busy neighbour after a real exit | partial; exp 4e on 4 streams; drops a far-seated person when a pet or second person exits (exp 12); failed live on stove-case-0913 |
| `score_hold` (hold/score_hold.py) | flapping on threshold-grazing noise | untested; present only as the control path in 21-v1 / 22-v3 / 23-v1 |
| `attributed_hold` (hold/attributed_hold.py) | neighbour evidence refreshing an owned room | partial; exp 4e only |
| `retention_hold` (hold/retention_hold.py) | still occupant released mid-visit | partial; exp 4e; the 21:49 seated minute held |

Not stages but shipped alongside: score hysteresis (`enter_score` 3.0 /
`exit_score` 1.5 / `hold_s` 30), cold-start device passthrough, and the
backwards-`ts_mono` deadline rebase — all untested beyond serving as the
control path in the validation replays.

## Standing caveats

- Only `energy_floor` has a corpus-wide clean result. Everything in
  phase 2.5 rests on ≤5 fixtures, two of them synthetic mixes whose
  amplitudes are fiction; `docs/spec/validation/24-v1-entry-edge-retention.md`
  does not exist.
- Code and spec 24 disagree on release: code ships crossing-arming (D′,
  exp 4e); spec 24 §1a describes retention-reset (D″, exp 4f), whose
  `clamp_s` option does not exist in `DetectorConfig`.
- Two techniques marked validated in `decisions.md` are not shipped:
  histogram floor + spread (spec 25) and the motion-gated ceiling. The
  baseline stages run the forms their own experiments beat.
