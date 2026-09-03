# 32 — Phase 3: External Evidence & Labeling

House layer, part 3. Evidence enters through HA entity state only; adding a
source is configuration. Evidence does two jobs: live input to 31, and label
generation into the sensor DBs' `episodes` table.

## 1. Mapping config

List of entries:

```yaml
- entity: binary_sensor.bed_rob
  type: bed
  room: bedroom
- entity: binary_sensor.front_door
  type: door
  rooms: [mudroom, exterior]
- entity: sensor.kitchen_co2
  type: co2
  room: kitchen
- entity: sensor.circuit_kitchen_power
  type: power
  room: kitchen
  on_watts: 80
- entity: event.driveway_arrival     # Frigate or equivalent
  type: arrival
  room: exterior
```

Unknown types rejected at config validation with the supported list.

## 2. Semantics table

| type | live effect (31) | label effect |
|---|---|---|
| bed | occupied ⇒ pin `c[room] ≥ 1`, hold `p[room]`; release on clear | occupied span ⇒ positive label for that room's sensors; contributes to known-vacant elsewhere |
| door | state change ⇒ transition likelihood spike between `rooms` for `door_window_s` (10 s); exterior doors feed conservation (31 §3) | transition timestamps anchor track/handoff labels |
| co2 | none live (lag 10–20 min) | flat within `co2_flat_ppm` (default 25) of its rolling floor for ≥ `co2_flat_min` (30 min) ⇒ vacant window for `room`; monotonic rise ≥ `co2_rise_ppm` (40) ⇒ occupied window covering the rise |
| power | above `on_watts` ⇒ weak occupancy evidence `w_power` (0.2) for `room` | appliance-cycle spans available as features, not labels |
| arrival | increment expected-count prior; open `guest_window` if unmatched to residents | guest windows excluded from Phase 5+ preference learning |
| humidity | delta vs house reference > `rh_delta` (12) ⇒ weak occupancy evidence for `room` | shower spans as features |

## 3. Known-vacant windows

Computed continuously per room: intersection of (31 vacancy_confidence ≥ 0.9
sustained) with any available hard evidence (all residents pinned elsewhere;
CO2 flat where mapped). Written to house DB:

```sql
vacant_windows(room TEXT, t0 REAL, t1 REAL, basis TEXT, conf REAL);
```

Consumers: negative labels (any sensor episode inside a window ⇒
`auto_false(vacant_window)`), and baseline-health checks (a gate whose floor
rises during vacant windows only is flagged drifting — diagnostic event).

Labeling precision rule: a window is only written when `conf ≥ 0.95`; false
vacant labels poison training and are treated as suite failures, missed
windows are free.

## 4. Label store

Labels are written into each sensor DB's `episodes` rows (10 §2):
`label ∈ {true_presence, auto_false(reason), user_true, user_false, unknown}`,
`label_source`, `label_conf`. Append-only semantics: relabeling writes a new
revision row in `label_history(episode_id, label, source, conf, ts)`; the
episode row carries the latest.

User labeling surface: a service
`smart_ld2410.label_episode(episode_id, label)` plus a diagnostics view
listing recent unlabeled high-interest episodes (entered but contradicted, or
suppressed). No UI beyond that in this phase.

## 5. Validation

1. Two weeks live: vacant-window spot check — zero windows overlapping any
   demonstrably-occupied period.
2. Label audit: ≥ 95% precision on a 100-label random sample across
   auto_false reasons.
3. Replay: evidence stream recorded (house DB `evidence(ts, entity, type,
   room, value)`) and the full labeler reproduces identical windows/labels
   from recordings.
