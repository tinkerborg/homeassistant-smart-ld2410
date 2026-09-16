# 10 — Interfaces & Contracts

Everything downstream of the sensor integration codes against this document, not
against its internals.

## 1. Sensor integration → consumers

### 1.1 Entities (per sensor)

- `binary_sensor.<name>_occupancy` — derived occupancy. Attributes:
  `confidence` (0–1), `active_gate_min`, `active_gate_max`, `mode`
  (`passthrough` | `learned`), `boundary_gate` (int | null, Phase 2),
  `leading_gate` (int | null, Phase 2), `ownership`
  (`armed` | `disarmed` | null, Phase 2.5), `retention_max` (float,
  Phase 2.5).
- `sensor.<name>_confidence` — 0–1 float, updated with occupancy.
- `sensor.<name>_target_distance` — meters, from active-band centroid.
- Diagnostics (default-disabled): per-gate residuals, baseline age, bucket
  counts, freeze/hold state, gate classes (Phase 2).

### 1.2 Feature stream

Dispatcher signal `smart_ld2410_features_v1`, per sensor, emitted at frame rate
downsampled to ≤ 2 Hz. Payload:

```json
{
  "schema": 1,
  "sensor_id": "str",
  "ts": "float unix",
  "occ": true,
  "confidence": 0.87,
  "centroid_gate": 3.4,
  "gate_span": 1.9,
  "residual_mass_move": 12.1,
  "residual_mass_still": 30.5,
  "edge_band": "near|far|none",
  "mode": "learned"
}
```

- `centroid_gate`: residual-weighted mean gate index over active gates.
- `gate_span`: residual-weighted std of gate index.
- `edge_band`: whether the active band touches gate 0–1 (`near`) or the last
  in-room gate (`far`); used for handoff detection.
- Additive changes bump minor semantics only; removals/renames bump `schema`
  and the signal name. Consumers must ignore unknown keys.

### 1.3 Events

On the HA bus:

- `smart_ld2410_episode` — fired at episode close (see §3 episodes table for
  fields; payload = row minus raw arrays).

## 2. Storage (SQLite, integration-owned)

One DB per config entry directory; WAL mode; all writes off the event loop.

```sql
frames(sensor_id TEXT, ts REAL, ts_mono REAL,
       move BLOB, still BLOB,            -- 9 bytes each, gate order 0..8
       distance_cm INT, device_occ INT,
       PRIMARY KEY(sensor_id, ts));
minute_summary(sensor_id TEXT, minute INT, gate INT, chan INT,
       q50 REAL, q90 REAL, qmax REAL, n INT,
       PRIMARY KEY(sensor_id, minute, gate, chan));
buckets(sensor_id TEXT, bucket INT, gate INT, chan INT,
       med REAL, spread REAL, n INT);     -- 60 s baseline inputs, schema v3
episodes(id INTEGER PRIMARY KEY, sensor_id TEXT, t0 REAL, t1 REAL,
       peak_residual REAL, gate_lo INT, gate_hi INT,
       centroid_mean REAL, centroid_vel REAL,
       still_frac REAL,                   -- fraction of episode still-dominant
       result TEXT,                       -- entered|rejected_coherence|rejected_hysteresis
                                          --   |rejected_energy_floor|rejected_arrival
                                          --   |rejected_leading_edge
       gate_peaks BLOB,                   -- peak raw move energy per gate, 9 bytes
       leading_gate INT,                  -- nearest gate above its learned quiet level
       label TEXT, label_source TEXT, label_conf REAL);  -- Phase 3+ writes labels
```

Retention job (daily): frames > `raw_retention_days` (default 7) deleted;
minute_summary > `summary_retention_days` (default 365) deleted; episodes kept
indefinitely.

## 3. Replay harness

Command line, per-frame decisions to stdout:

`python -m smart_ld2410.replay --db PATH --sensor ID --from TS --to TS
[--params overrides.json] [--emit episodes|states|frames]`

Library (`algo.harness`, pure Python), shared by the regression suite and the
experiments under `docs/research/experiments`:

- `sensor_ids(db)`, `frames(db, sensor_id)` — a recording may hold several
  sensors.
- `run(db, sensor_id, *, config=None, stages=None)` — every frame with the
  `DetectorOutput` it produced.
- `replay(db, sensor_id, *, config=None, stages=None)` — the occupancy timeline
  that configuration produces, as `OccupancyEvent(ts, occupied, confidence,
  score, active_gates)`. `stages` overrides `config.stages` (00 §4.3).
- `label_spans(db, room=…, person=…)` — ground-truth spans from a recording's
  `labels(person, room, ts_start, ts_end, note)` table, where it has one.
- `score_timeline(timeline, spans)` — entries, false entries, spans detected
  and missed, entry latency, and overlapping/false/missed seconds.

- Consumes `frames`; runs the identical algorithm core; emits decisions.
- Determinism requirement: identical DB + params ⇒ byte-identical output.
- Regression suite = the corpus timelines under `tests/fixtures/golden` (one
  file per recording, keyed by sensor) plus the recorded episode set, run in
  CI; any stage list is measured against them.

## 4. House layer → consumers (Phase 3)

- `binary_sensor.room_<room>_occupancy`, attributes `probability`,
  `count_estimate`, `vacancy_confidence`, `suppressed_sources` (list).
- `sensor.house_person_count` — attributes `accounted` (map person→room,
  Phase 5).
- Events: `occupancy_room_entered`, `occupancy_room_exited`,
  `occupancy_house_empty`, `occupancy_house_occupied` — payload
  `{room, ts, confidence}`.
- House layer owns its own SQLite (adjacency, evidence, labels; see 30/32).
  It reads the sensor DBs read-only for training/label writes via `episodes`.

## 5. Versioning

- Algorithm core: semver; version string logged into every episode row and
  replay output.
- Baseline schema: integer (`v3` current); migration on load, never in-place
  reinterpretation.
- Model artifacts (Phase 4): `{version, algo_semver, data_range, metrics}`
  metadata JSON beside the model file; integration refuses artifacts whose
  `algo_semver` major differs from its own.
