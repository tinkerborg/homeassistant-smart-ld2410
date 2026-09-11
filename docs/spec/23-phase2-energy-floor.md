# 23 — Phase 2: Episode Energy Floor

Goal: suppress through-wall entries by the evidence in the candidate episode
itself — attenuated activity is uniformly weak in *both* channels, while
genuine in-room presence, however still, keeps at least one channel strong.
Acceptance criteria are §4.

## 1. Statistic

Per candidate entry, over the frames since the triggering activity began:

- `combo_peak`: max over frames and active gates of
  `move_energy + still_energy` (raw values, not residuals — attenuation is
  absolute physics).

The still channel is mandatory: a motionless in-room person can show
move-channel peaks in the teens, indistinguishable from through-wall motion
on that channel alone; their still channel is what stays strong.

## 2. Effect on detection

At entry evaluation only (exit/hold per 20 §4):

- Entry is suppressed while `combo_peak < energy_floor` (default 30, raw
  units). The hysteresis state machine treats the frame as below
  `enter_score`.
- Suppressed activity still records episodes (result value
  `rejected_energy_floor`), still feeds classification and the feature
  stream — Phase 3 attribution consumes exactly these weak episodes.
- Once entered, the floor plays no role: exit remains score/hold-driven, so
  a person decaying to faint stillness is never dropped by this rule.
- Precedence: the floor applies after gate-class exclusion (a BLEED-only
  candidate never reaches it).

## 3. Options

`energy_floor` (0 disables the rule; diagnostic-tier). Per-sensor learned
floors are out of scope; one conservative global default, tuned only by
validation evidence.

## 4. Acceptance

1. Corpus sweep: at the default floor, zero genuine dwell entries lost
   across all recorded sensors — including every long still-dominant
   bathroom episode (move-peaks in the teens) — while a majority of
   long-faint through-wall episodes are suppressed.
2. Entry latency: no measurable delay on genuine entries (a real walk-in's
   first frames already exceed the floor).
3. The floor's miss tail (weak episodes above it) is documented with counts,
   as the input Phase 3 attribution is expected to close.
4. Still-presence asymmetry rule applies: any genuine dwell lost is a
   failure, not a trade.

Measured against the recorded corpus in
`validation/23-v1-energy-floor.md`, which is what the default of 30 rests on.
