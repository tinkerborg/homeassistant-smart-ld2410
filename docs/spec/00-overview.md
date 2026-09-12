# Smart LD2410 — Specification

## 1. Purpose

A Home Assistant custom integration that reads raw engineering-mode frames from
LD2410 sensors (via ESPHome BLE proxy), learns each room's noise floor
continuously, and publishes occupancy decisions that outperform the device's own
threshold logic. Later phases add cross-sensor reasoning and target
classification.

## 2. Principles

- **Zero-config.** Provision and go: device-bit passthrough from minute one,
  learned baseline within minutes, sharp within a day. Fresh install after wiping
  all data must reach full quality unattended — this is the acceptance test.
  Options exist as diagnostic surface, never as required tuning.
- **Replay-driven development.** All frames are recorded. Every algorithm change
  is diagnosed from recordings and proven by replay before shipping. Replay must
  match live behavior exactly (validated to the second). Algorithm code is
  HA-free and takes time from frames, never the clock.
- **Recording is permanent.** Homes change; learning never stops. Retention is
  tiered, not disabled after development.
- **Decisions degrade, never break, on partial data.** Unknown/low-confidence is
  a legitimate output at every layer.

## 3. Architecture

- **Integration** (`custom_components/`): config entry per sensor, coordinator,
  entities. BLE via ESPHome proxy; Bluetooth password supported (config field,
  reconfigure flow, ACK status checking).
- **Algorithm core**: pure Python module, no HA imports, shared verbatim by live
  path and replay harness.
- **Storage**: SQLite owned by the integration (not the recorder). Tiered
  retention — raw frames ~7 days, per-minute per-gate summaries ~365 days; both
  configurable.
- **Replay harness**: standalone, runs the algorithm core over any recorded
  range, produces identical output to live.

## 4. Detection pipeline

### 4.1 Baseline

Per gate, per channel (move/still):

- 60 s buckets storing sample median and upper-tail spread (q90 − q50). MAD is
  unsuitable: measured tails are non-Gaussian and MAD underestimates them.
- Window floor = p25 of bucket medians; spread = p25 of bucket spreads.
- **Learning is unconditional.** No occupancy-gated freeze: the low-quantile
  floor means occupants cannot raise it under normal use, and gating learning
  on detection creates a lock-in loop — a false detection would freeze the
  very learning that corrects it.
- Documented limit: a room occupied more than ~75% of the learning window begins
  absorbing the occupant into the floor.
- Baselines persist across restarts.

### 4.2 Decision

- Per-gate residual score against floor + spread.
- Spatial coherence: isolated single-gate exceedance is suppressed; the
  neighbor-support test is time-smoothed (`support_tau_s`) to survive real
  noise.
- Entry/exit hysteresis with hold time. Transient pass-bys do not accumulate
  enough sustained score to enter (validated: adjacent-hallway pass-bys
  rejected with no per-room configuration).
- Confidence published alongside the binary.

### 4.3 Bootstrap

Until the baseline is ready, the published occupancy mirrors the device's own
occupancy bit (passthrough). Handover is per-sensor on baseline readiness.

### 4.4 Device thresholds

A button entity writes permissive thresholds to the device. Device thresholds
have no effect on the pipeline; the native bit is retained only for passthrough
and logged comparison.

### 4.5 Entities

Per sensor: derived occupancy (binary, device class occupancy), confidence,
active gate range, target distance; diagnostics — baseline age/readiness,
freeze/hold state, per-gate residuals (disabled by default). Options: quantile
parameters, `support_tau_s`, hysteresis/hold, retention.

## 5. Validation (standing)

- Replay regression suite over recorded episodes, including: empty-room false
  latching (zero false entries, all real events retained), pass-by rejection,
  still-presence retention.
- New recordings that expose failures are added to the suite.
- Metrics asymmetry: losing still-presence to reduce false positives is a
  regression, not a trade.

## 6. Implementation plan

### Phase 2 — Single-sensor room boundaries

Goal: each sensor learns which gates are in-room without configuration.

- **Dwell-character classification.** Gates whose activations regularly settle
  into sustained still-presence are in-room; gates that only ever see brief
  sweeps are bleed/out-of-room. Rare-but-long-dwell zones classify correctly
  from their first sustained event; once a gate is in-room, brief events there
  count. Reclassification is continuous, so furniture moves self-correct.
  Brief episodes are outcome-conditioned — sweeps that reliably precede
  sustained occupancy mark PORTAL (doorway) gates, which keep entry fast;
  sweeps that lead nowhere mark BLEED (20 §3a).
- **Arrival-gated entry (22).** A person entering the room produces
  moving-channel energy near the sensor's observed ceiling; through-wall
  activity never does. Entry requires arrival-scale motion against a
  learned sensor-global ceiling; exit and hold are untouched, so still
  presence is never at risk.
- **Energy-ceiling boundary learning.** Walls impose attenuation beyond what
  range alone explains. Learned per-gate max-energy distributions, measured
  against the sensor's own range falloff, locate the boundary. Candidate fix
  for through-wall sustained dwell; requires validation against recordings.
- **Episode energy floor (23).** Attenuated through-wall activity is
  uniformly weak across both channels; genuine in-room presence, however
  still, keeps a channel strong. Entries whose combined move+still peak sits
  under the floor are suppressed; the surviving weak tail is Phase 3
  attribution's input.
- Fallback: manual per-sensor max-range option.
- Exit criteria: kitchen-through-wall recordings suppressed by learned
  boundaries (or explicitly documented as requiring Phase 3); no regression in
  the standing suite.

### Phase 3 — Multi-sensor house layer

Separate integration consuming per-sensor outputs (occupancy, confidence, gate
band, residual features). No floor plans, no coordinates.

- **Learned adjacency.** Track handoffs between sensors observed over weeks
  build the adjacency graph. Manual adjacency list as fallback.
- **Cross-room attribution.** Through-wall/through-floor ghosts occupy a fixed
  gate band determined by fixed geometry; the house layer learns them as
  correlates of another sensor's strong track and suppresses the ghost.
- **Hidden-room inference.** Uncovered rooms inferred from joint doorway-band
  signatures on adjacent sensors plus track continuity; occupants out of all
  coverage carry a last-known room.
- **House state.** Per-room occupancy beliefs, person-count conservation via
  entry/exit rooms, confident-vacancy output, transition events on the bus.
- **External evidence.** Configurable entity mapping (bed sensors, door
  contacts, CO2, power, camera arrival events) feeding the same estimator and
  generating labeled episodes (known-vacant windows, contradiction labels) into
  the recording store.

### Phase 4 — Target classification

Trained from labeled episodes in the recordings (user-labeled plus
evidence-generated labels). Batch training offline; versioned model artifacts;
manual promotion; inference in-process.

- **Pet filtering.** Cadence, gate span, energy profile, dwell locations.
  Possible, not promised: separability from a crouched human is an open question
  the data must answer. Uncertain windows report uncertain; decision policy is
  context-dependent (default trigger by day, suppress by night).
- **Appliance impostors.** Constant sources are absorbed by the floor; cycling
  sources (compressors) imitate dwell. Boundary mask covers beyond-wall
  appliances; in-room cycling sources require micro-motion/breathing-band
  classification — same phase, same caveat: validate on recordings before
  promising.

### Phase 5 — Prediction and identity (directional)

Only after Phases 2–4 are proven. Track velocity + learned transition priors
for short-horizon room-entry prediction (anticipatory lighting, device wake).
Identity as an estimate carried by external evidence (beds, phones, arrivals)
with radar features narrowing ambiguity; per-person automation only above a
confidence floor, household default below it. Activity states and
preference-from-correction learning follow the same rule: proposals require
user approval; behavior never changes without an approved, visible rule.

## 7. Known limits

- Single-sensor through-wall sustained dwell (kitchen-island case) has no
  reliable statistical fix today. Energy ceiling is the best candidate;
  otherwise range cap or a second sensor.
- Gates at equal range are indistinguishable within one sensor (no angular
  resolution). Zone-level output exists only where range or sensor overlap
  separates zones.
- Fine gate mode (0.2 m × 9 gates ≈ 1.8 m coverage) is a per-sensor option for
  small spaces, not a general answer.
- Breathing-band detection is unproven on this hardware; nothing may depend on
  it.

## 8. Bundle index

Detailed implementation specs; each is authoritative for its piece.

- 10-interfaces.md — contracts between sensor integration, house layer, storage, replay
- 20-phase2-dwell-boundary.md — dwell-character gate classification
- 21-phase2-energy-ceiling.md — energy-ceiling boundary learning
- 22-phase2-arrival-entry.md — arrival-gated entry (through-wall suppression)
- 23-phase2-energy-floor.md — episode energy floor (through-wall suppression)
- 24-phase2.5-entry-edge-retention.md — leading-edge entry, still-presence retention
- 30-phase3-tracks-adjacency.md — local tracks, handoffs, learned adjacency
- 31-phase3-house-estimator.md — house state, conservation, vacancy, suppression
- 32-phase3-evidence-labeling.md — external evidence, known-vacant windows, label store
- 40-phase4-classification.md — episode features, training, promotion, serving
- 50-phase5-prediction-identity.md — directional
