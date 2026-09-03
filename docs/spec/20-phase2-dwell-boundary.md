# 20 — Phase 2: Dwell-Character Gate Classification

Goal: per sensor, learn which gates are in-room from the character of their
activation episodes, with zero configuration.

## 1. Definitions

- **Gate episode**: for gate g, a maximal interval where the smoothed residual
  score of g exceeds `s_gate_on` (same smoothing constant as the detector's
  neighbor-support test), closed after `gap_close_s` (default 2 s) below
  `s_gate_off`.
- **Sustained episode**: duration ≥ `t_dwell_s` (default 60) AND
  still-channel residual dominant (`still_frac` ≥ 0.5 over the episode).
- **Brief episode**: duration ≤ `t_brief_s` (default 10).
- Episodes between brief and sustained are recorded but count toward neither
  class.

## 2. Per-gate statistics

Maintained per gate in the integration's DB (`gate_stats` table), decayed:

- `n_sustained`, `n_brief`: exponentially decayed counts, half-life
  `stats_half_life_days` (default 30).
- `last_sustained_ts`.

Update at episode close, from the same episode segmentation the detector
already computes (no second pipeline).

## 3. Classification rule

Evaluated at episode close and daily:

- **IN_ROOM**: `n_sustained` ≥ 1 (a single genuine sustained event
  classifies; rare-use zones must work from their first session).
- **BLEED**: `n_brief` ≥ `n_bleed_min` (default 20) AND `n_sustained` < 0.5
  AND `last_sustained_ts` older than `stats_half_life_days`.
- **UNKNOWN**: neither. Treated as IN_ROOM by the detector (permissive
  default).

Transitions:

- UNKNOWN→IN_ROOM, BLEED→IN_ROOM: immediately on a sustained episode.
- IN_ROOM→BLEED: only via decay (rule above) — demotion is slow by design;
  furniture moves self-correct over `stats_half_life_days`.
- All transitions logged to `events`.

## 4. Effect on detection

- BLEED gates are excluded from entry scoring: their residuals do not count
  toward crossing the entry threshold and do not provide neighbor support.
- BLEED gates still stream in features and still record episodes (so
  reclassification and Phase 3 attribution keep their data).
- Exit/hold logic unchanged: once entered, all gates contribute to holding.
- Known limit (carried from overview): a through-wall *sustained* dwell
  (kitchen-island case) produces sustained episodes and classifies IN_ROOM.
  Dwell statistics cannot reject it. See 21 (energy ceiling); fallback is the
  manual `max_gate` option, which hard-caps classification at OUT beyond the
  configured gate.

## 5. Storage

```sql
gate_stats(sensor_id TEXT, gate INT,
           n_sustained REAL, n_brief REAL,
           last_sustained REAL, class TEXT, updated REAL,
           PRIMARY KEY(sensor_id, gate));
```

## 6. Entities

- Diagnostic sensor per sensor: `gate_classes` — string like `IIIIUBB??`
  (I/B/U per gate), plus attributes with per-gate counts.
- Options: `t_dwell_s`, `t_brief_s`, `n_bleed_min`, `stats_half_life_days`,
  `max_gate` (manual override, null default). All diagnostic-tier; defaults
  must not require touching.

## 7. Validation

Replay against recordings, added to the standing suite:

1. Hallway pass-by recordings: bleed gates reach BLEED; pass-bys rejected at
   entry scoring even before hysteresis.
2. Rare-zone scenario (recorded or staged): one sustained visit to a
   previously-unvisited far gate ⇒ IN_ROOM immediately; subsequent brief
   events there count toward occupancy.
3. Kitchen-island through-wall recordings: documented as NOT fixed by this
   spec alone (expected IN_ROOM); fixed in combination with 21 or `max_gate`.
4. No regression: still-presence retention and false-entry metrics unchanged
   or better on the full suite.
