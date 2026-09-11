# 20 — Phase 2: Dwell-Character Gate Classification

Goal: per sensor, learn which gates are in-room from the character of their
activation episodes, with zero configuration.

## 1. Definitions

- **Gate episode**: for gate g, a maximal interval where the smoothed residual
  score of g exceeds `s_gate_on` (same smoothing constant as the detector's
  neighbor-support test), closed after `gap_close_s` below `s_gate_off`.
  `gap_close_s` defaults to the detector's `hold_s`: if occupancy tolerates
  N seconds of low signal as continued presence, the dwell clock must too.
- **Active fraction**: the share of an episode's span during which its signal
  was above `s_gate_off`. Since the close window is as wide as `hold_s`, span
  alone does not establish that the signal was there throughout.
- **Sustained episode**: duration ≥ `t_dwell_s` (default 60) and
  `active_frac` ≥ `active_frac_min` (default 0.6). Duration is the criterion:
  a spatially-coherent episode holding one gate for a minute is direct
  evidence of a body; a sweep cannot do it. The active-fraction guard is what
  keeps chained pass-by sweeps, bridged by sub-`gap_close_s` gaps, from
  stacking into one fake dwell. Channel dominance is not a usable criterion —
  breathing keeps the quiet move channel elevated during genuine stillness —
  so `still_frac` is recorded as a diagnostic and gates nothing.
- **Brief episode**: duration ≤ `t_brief_s` (default 10). The active-fraction
  guard does not apply: a gappy short episode is still bleed evidence.
- Episodes between brief and sustained, and long ones under
  `active_frac_min`, are recorded but count toward neither class.
- **Detection-scope episode closing**: an *entered* detection episode closes
  when occupancy releases (hold expiry) — the all-quiet-gates condition is
  rarely met in a lived-in room. Never-entered activity closes on all gates
  quiet.
- **Stall close**: any open episode closes when the frame stream gaps by more
  than `episode_stall_s` (default 10 s). The close is evaluated as of the last
  frame *before* the gap: `t1` stays at the last frame whose signal was
  observed above `s_gate_off`, exactly as in an ordinary close, and the
  unobserved tail — bounded by `episode_stall_s` — is discarded rather than
  credited. A gate that is hot when the link drops therefore yields an episode
  of the length actually observed, not one spanning the outage.

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
- **PORTAL**: not IN_ROOM, AND `n_lead` ≥ `n_portal_min` (default 5) AND
  `n_lead / (n_lead + n_dead)` ≥ `portal_lead_frac` (default 0.3). See §3a
  for `n_lead`/`n_dead`.
- **BLEED**: `n_brief` ≥ `n_bleed_min` (default 20) AND `n_sustained` < 0.5
  AND `last_sustained_ts` older than `stats_half_life_days` AND not PORTAL.
- **UNKNOWN**: none of the above. Treated as IN_ROOM by the detector
  (permissive default).

Precedence: IN_ROOM > PORTAL > BLEED > UNKNOWN.

## 3a. Outcome-conditioned counts

A brief episode viewed alone cannot distinguish a doorway transit (someone
entering the room) from a pass-by (someone crossing outside). The
discriminator is what follows on the same sensor:

- A brief episode at gate g is **leading** if a sustained episode as defined
  in §1, at any gate, *opens* within `lead_window_s` (default 5 s) of its
  close, on either side of it — a person walking through a doorway lights the
  gate they are heading for before the doorway gate falls quiet. It is
  **dead-end** otherwise.
- `n_lead`, `n_dead`: exponentially decayed counts of leading/dead-end brief
  episodes, same half-life as §2.
- The outcome signal is raw episode segmentation only — never the detector's
  occupancy output. The detector's decisions depend on these classes;
  feeding them back as training signal would let the classifier eat its own
  tail (a wrongly-BLEED gate suppresses detection, which erases the evidence
  that would fix it).
- Leading/dead-end resolution happens `lead_window_s` after episode close;
  counts update then, not at close. A brief episode whose window contains an
  episode that is still open waits for that episode to end, since whether it
  was a dwell is not yet knowable.

Doorway zones — every entry transits them, few people dwell in them — thus
classify PORTAL rather than BLEED, and detection at the door stays fast.

Transitions:

- UNKNOWN→IN_ROOM, BLEED→IN_ROOM: immediately on a sustained episode.
- IN_ROOM→BLEED: only via decay (rule above) — demotion is slow by design;
  furniture moves self-correct over `stats_half_life_days`.
- All transitions logged to `events`.

## 4. Effect on detection

- BLEED gates are excluded from entry scoring: their residuals do not count
  toward crossing the entry threshold and do not provide neighbor support.
- PORTAL gates participate in entry scoring and neighbor support exactly like
  IN_ROOM gates.
- BLEED gates still stream in features and still record episodes (so
  reclassification and Phase 3 attribution keep their data).
- Exit/hold: once entered, all gates contribute to holding.
- Known limit: a through-wall *sustained* dwell
  (kitchen-island case) produces sustained episodes and classifies IN_ROOM.
  Dwell statistics cannot reject it. See 21 (energy ceiling); fallback is the
  manual `max_gate` option, which hard-caps classification at OUT beyond the
  configured gate.

## 5. Storage

```sql
gate_stats(sensor_id TEXT, gate INT,
           n_sustained REAL, n_brief REAL,
           n_lead REAL, n_dead REAL,
           last_sustained REAL, class TEXT, updated REAL,
           PRIMARY KEY(sensor_id, gate));
```

## 6. Entities

- Diagnostic sensor per sensor: `gate_classes` — string like `IIIPUBB??`
  (I/P/B/U per gate, O for max_gate-capped), plus attributes with per-gate
  counts.
- Options: `t_dwell_s`, `t_brief_s`, `n_bleed_min`, `n_portal_min`,
  `portal_lead_frac`, `lead_window_s`, `stats_half_life_days`, `max_gate`
  (manual override, null default). All diagnostic-tier; defaults must not
  require touching.

## 7a. Reset

Button entity per sensor (`EntityCategory.CONFIG`): "Reset learning" — wipes
the persisted baseline, gate statistics, and learned boundaries (20/21/22)
for that sensor and restarts warmup (passthrough until ready). For sensors
that get physically moved; learned state is location state. Frames/episodes
already recorded are kept (history, not model).

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
