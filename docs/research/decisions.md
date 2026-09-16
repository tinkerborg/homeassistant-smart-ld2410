# Technique decision list

Validated techniques, how each works in one sentence, and what it helps
with. Details: [experiments.md](experiments.md) and
[experiments/](experiments/).

## Deployed

- **Leading-edge entry** — entry is allowed only when motion first
  appears at the room's entry gates, judged on residuals that ignore
  lone-gate noise spikes. Kills through-wall false entries; band is
  hand-set and wrong for deep rooms.
- **Signed retention hold** — two running averages of still energy
  (seconds vs a minute); the gap between them stays positive while a
  person breathes or shifts, and that gap refreshes the hold. Keeps a
  still person occupied through the chip's static-target absorption.
- **Crossing-armed release** — a burst of motion back through the entry
  gates marks a walk-out; afterward only near-gate evidence keeps the
  room on. Lets the bathroom release while the kitchen is busy; drops a
  far-seated person when a pet exits (known bug).

## Validated, not built

- **Histogram floor + spread** (spec 25) — floor = the most common low
  energy value (histogram peak), spread = variation among only the
  samples near that peak; occupancy adds a tail that never moves the
  peak. Correct baselines learned while people are in the room.
- **Motion-gated ceiling** (spec 22) — the loudest-arrival reference
  advances only through minutes containing real motion, so empty weeks
  cannot dilute it. Vacation-proof arrival bar.
- **Retention-reset release (D″)** — a walk-out crossing zeroes the held
  presence signal for about a minute; anyone still present rebuilds it
  by existing, an empty room cannot. Replaces crossing-arming; fixes the
  pet-exit and two-person cases with no per-room settings.
- **Learned arrival band** — record which gate the first motion after
  silence starts at; days of those origins pile up into the doorway
  location, and entry requires starting there. Replaces the hand-set
  gate number in rooms with depth (needs ~20 arrivals; default band
  covers boundary-mounted rooms like the bathroom).

## Dead (falsified on this hardware or data)

Unsupervised HMM; fade-character statistics; frame-to-frame noise floor;
separation learning from dwell outcomes; per-room exit policy.

## By room

**Downstairs bathroom** (shallow, door at sensor, kitchen through the
facing wall)
- Kitchen false entries → Leading-edge entry (deployed) + the arrival
  gate; position learning is degenerate here, so this stays the answer.
- Stuck occupied while kitchen is busy after a real exit →
  Crossing-armed release (deployed) or Retention-reset release
  (its replacement).
- Two people, one leaves → Retention-reset release.

**Living room** (deep, door far from sensor, rear-mounted)
- Walk-ins rejected as entries → Learned arrival band (interim:
  hand-set lead_gate_max 2).
- Dropping a still occupant → Signed retention hold (deployed) +
  Histogram floor + spread (stronger scores).
- Pet exit turning lights off on a seated person → Retention-reset
  release.
- Reset/learning while seated → Histogram floor + spread.

**Every room**
- Vacation decaying the arrival bar → Motion-gated ceiling.
- Baselines learned during occupancy → Histogram floor + spread.
- Far-seated person + someone exits past the sensor → unsolved on one
  sensor; Phase 3 cross-sensor attribution.

