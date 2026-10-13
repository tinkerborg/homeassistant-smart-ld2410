# Proposal: continuity tracker

Principle: people are continuous objects. A person cannot appear in a room
without crossing its boundary, cannot vanish while inside, and cannot
leave without crossing out. Per-frame energy is evidence about that
object, never the state.

## State

- `present` (bool) — the only output.
- `E(t)` — presence evidence: max over gates of the signed, peak-held
  retention statistic (positive part of fast−slow still EMA, tau 2 s /
  60 s, peak-hold 90 s, normalized by the clamped frame-difference
  noise), combined with the scored motion residual (either suffices).

## Events

- **Transition**: a large-motion event — moving energy reaching
  `arrival_frac × ceiling` (ceiling motion-gated, floor 60). Direction is
  never inferred.
- **Boundary check** (only where bleed pressure is learned to exist):
  the transition's suppressed leading gate must lie in the room's entry
  band (default 0–1; learned arrival-origin band where available).
  Motion that never touches the boundary is not a transition.
- Bleed pressure = orphan-episode ratio (label-free); above threshold the
  boundary check applies, below it any large motion is a transition.

## Update rule

`present` changes only at transitions, plus one fallback:

1. At a transition: reset `E` to zero and open a re-prove window
   `W` (60 s). If `E` re-lifts above `E_on` (20) within `W`, `present =
   true` (arrival, or someone remained). If it does not, `present =
   false` (departure).
2. Between transitions `present` holds. `E` refreshes nothing and
   releases nothing on its own — a still person's evidence may fade; the
   object does not.
3. Fallback (missed transition, dropout): `present` and `E < E_off` (10)
   continuously for `T_fallback` (10 min) → `present = false`.

Cold start: until the baseline is ready, passthrough per spec 10.

## What it drops from the current design

Hysteresis enter/exit scores as the state machine, the energy floor as a
separate rule, arming/disarming, grace windows, hold_s as a release
timer, retention_off as a release gate. Retained: baseline residuals
(histogram floor+spread when built), arrival ceiling, leading edge,
signed retention, reset-and-re-prove.

## Parameters

`arrival_frac`, `ceiling_motion_floor`, `E_on`, `E_off`, `W`,
`T_fallback`, entry band (default or learned), bleed-pressure threshold.
