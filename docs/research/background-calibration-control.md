# LD2410 background calibration: host control?

Question (2026-09-12): can the module's internal adaptive background
subtraction — which absorbs a motionless person within minutes — be
frozen, disabled, triggered, or rate-adjusted from the host?

## Verdict: not controllable

The complete LD2410/B/C command set (protocol V1.02-V1.07, cross-checked
against aio-ld2410 and ESPHome) contains nothing touching the clutter
model. `0x0B` (firmware ≥2.44, "background noise detection") is a
one-shot auto-THRESHOLD routine (sets per-gate sensitivities, then ends);
`0x1B` queries its progress. "Unmanned duration" is an output hold timer
after detection has already dropped. No undocumented opcode has been
surfaced by any community project. The absorption predates V2.44 (only
the user-triggerable threshold routine is new), so downgrading gains
nothing and loses `0x0B`.

Re-firing `0x0B` periodically is actively wrong: it re-baselines onto the
occupied room.

## Sibling modules

- **LD2412**: same opcode family; `0x0B/0x1B` renamed "Dynamic Background
  Correction" but still one-shot. 14 gates, separate motion/static gate
  sensitivity commands, better antenna, drop-in UART, ESPHome support.
  Comparison testing reports it holds presence=1 continuously where the
  LD2410 drops repeatedly on a completely still person.
- **LD2410S**: different protocol; its auto-threshold takes a retention
  factor governing how easily a detected target stays detected — the only
  HLK part that parameterizes retention over the wire.
- **LD2450**: tracking-only, no still-energy concept; strictly worse.

## Options

1. Swap to LD2412 (cheapest real hardware fix for still absorption).
2. Host-side retention over engineering-mode energies (what this project
   already does).
3. LD2410S (driver rewrite).
4. Firmware downgrade: no.

Sources: esphome/feature-requests#3161; morian/aio-ld2410; ESPHome ld2412
component/source; HLK-LD2412 protocol V1.05; HLK-LD2410 protocol V1.02;
HLK-LD2410S protocol V1.00; Screek LD2412/LD2410C comparison; ESP Easy
P159.
