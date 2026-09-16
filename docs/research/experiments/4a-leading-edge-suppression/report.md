# Experiment 4a: leading edge over suppressed residuals

Data: `throughwall-morning-d06e.db` (bathroom empty, wife in kitchen;
shipped false entries 05:11:49 and 05:36:24, one recorded with
leading_gate=0 — poisoned by this unit's bursty gate-0 move chatter) and
the dev DB's labeled toilet sessions of 2026-09-09 (now fixture
`labeled-sessions-0909-d06e.db`). Scripts: lead.py (library), lead_run.py.

## Verdict

**Yes — clean separation.** With isolated-gate suppression applied, the
through-wall hour never produces a leading edge ≤1 on any activity block
that matters, while both labeled genuine toilet entries lead at gate 0
within their entry window. A `leading_gate ≤ 1` entry rule refuses both
shipped false entries and admits both genuine ones.

## 1. False entries — D0:6E, 05:00-06:00 (bathroom empty)

| block | dur | lead_raw | lead_supp | suppressed-lead histogram |
|---|---|---|---|---|
| 05:11:49-05:16:20 | 271s | **0** | **2** | g2:1432 g3:465 g4:7 |
| 05:35:36-05:36:54 | 78s | 2 | **2** | g2:53 g3:42 g4:36 g5:21 g7:44 … |
| 05:38:10-05:39:51 | 101s | 0 | 2 | g2:16 g3:11 g4:5 g5:16 … |
| 05:51:02-05:54:41 | 220s | 2 | 2 | g2:50 g3:114 |
| 05:03:42-05:04:26 | 45s | 0 | **0** | g0:1 g2:2 g3:3 (1 frame, no entry) |

Whole hour (36,001 frames): suppressed leading gate ≤1 in **1 frame**
(0.003%), in a 45s block far from either false entry. Raw leading gate ≤1
in 19 frames — which is how the shipped leading_gate got poisoned to 0 at
05:11:49: `_track_candidate` is sticky, so a single g0 frame anywhere in
the candidate pins the recorded value.

## 2. Genuine entries — labeled toilet sessions, 2026-09-09

| session | entry window (−30s..+15s) lead_supp | histogram |
|---|---|---|
| 21:24:23 | **0** | g0:9 g1:19 g2:147 g3:26 g4:6 g5:7 g6:9 |
| 23:15:27 | **0** | g0:61 g1:73 g2:277 g3:32 g4:3 |

Both entries carry sustained g0/g1 move residual that survives suppression
(9 and 61 frames at g0; 19 and 73 at g1) — not a lone spike.

## 3. Gate-0 stats, 05:00-06:00

| metric | frames | % |
|---|---|---|
| raw move residual g0 ≥ k (4.5) | 18 | 0.05% |
| g0 survives isolated-gate suppression | 1 | 0.003% |
| suppression kills | 17 | 94.4% of g0-hot frames |
| raw leading gate = 0 | 18 | 0.05% |
| suppressed leading gate = 0 | 1 | 0.003% |

(g1: 2 raw-hot frames → 1 surviving.)

## Method / shortcuts

lead.py replicates `baseline.residuals` with the real bucket estimator
(60s buckets, floor = p25 of bucket q50s, spread = max(p25 of bucket
q90−q50, min_mad=1.0), 12h window, 6h warm-up before each scan window,
defaults k=4.5, support_tau_s=1.0). Support EMA over
`peaks = max(0, res_move, res_still)` exactly as the detector; isolated-run
rescue tests neighbor support ≥ k/2. Shortcuts: (a) no classifier exclusion
mask — suppression-only is strictly weaker, so anything rejected here is
also rejected with the mask on; (b) leading gate scanned per frame with
block minimums, not the detector's sticky candidate value.
