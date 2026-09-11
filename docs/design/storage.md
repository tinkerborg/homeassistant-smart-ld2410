# Storage

The integration owns a SQLite database at `<config>/smart_ld2410/frames.db`
(one DB for all sensors; WAL mode; a single writer thread batching commits
~1/s, so write churn is one small sequential commit per second per HA
instance regardless of sensor count).

## Why frames are recorded at all

Recording is not development scaffolding — it is how the system keeps
adapting. Homes change (furniture, seasons, remodels, new sensors), and every
re-tune, regression check, and learned spatial pattern (doorway bleed,
through-floor ghosts) is derived by replaying recorded frames. The recorder
must therefore run indefinitely in arbitrary homes with a bounded footprint.

## Tiered retention

Two tiers, both pruned daily by the store's maintenance job:

1. **Raw frames** — full 18-channel energies at native rate (~10Hz).
   Kept for a short window: default **7 days**. This is enough to diagnose a
   problem after the fact and to re-tune against recent reality.
   ~850k rows/sensor/day.
2. **Minute summaries** — per sensor, per minute, per gate/channel:
   median, MAD, min, max energy, plus occupancy/confidence aggregates.
   Rolled up from raw frames before they are pruned; kept for a long window:
   default **365 days**. This is what baseline learning, seasonal drift
   analysis, and spatial-pattern learning actually consume. Roughly three
   orders of magnitude smaller than raw.

Ballpark footprint at 13 sensors with defaults: single-digit GB of raw
(rolling) plus tens of MB of summaries per year.

Both windows are integration options (per install, not per sensor), editable
without restart. Raw retention may be set short (1 day) on storage-poor
hosts; summaries are cheap enough to leave long everywhere.

## Non-goals

- The HA recorder is never used for frame data; high-rate diagnostic
  entities stay disabled by default so they don't leak into it.
- No cloud or external storage; the DB is local and self-contained.
- Raw frames older than the raw window are gone — the design accepts that
  deep-history debugging works from summaries only.
