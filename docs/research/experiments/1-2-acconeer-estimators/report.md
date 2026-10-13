# Experiments 1+2: slow/fast filter difference & frame-to-frame noise floor

Data: live recording, FD:68 (living room), 2026-09-11 evening (now fixture
`livingroom-reset-seated-fd68.db`); follow-up on D0:6E (bathroom) 05:00-06:00
same day (now fixture `throughwall-morning-d06e.db`). Scripts: acc1-3.py,
bath.py.

## Verdict

1. **Slow/fast EMA difference — transfers, and it's the fix.** On the still
   channel it separates cleanly at the failure minute: 21:49 gate-3 median
   5.17 vs 0.20 in the empty reference (~25x). No sqrt-N scaling needed.
   tau=(2s, 60s) is the sweet spot; (1,30) loses margin, (3,90) starts
   leaking ambient into gates 5-8. On the **move** channel it does not work
   (present 1.37 vs empty 0.26 — same order as noise).
2. **Frame-to-frame noise floor — does NOT transfer as occupancy-immune.**
   A seated human inflates it 3-6x (gate 3: 0.34 during occupied-learning,
   0.08 truly empty, 0.45 seated). At 10 Hz on already-smoothed energies,
   human micro-motion lives in the same band the floor measures; Acconeer's
   version works because raw sweeps run orders of magnitude faster than a
   body. Double-differencing and outlier clipping barely help. It's still a
   fine *normalizer* (it errs toward desensitizing, not false drops), just
   not a learning-free baseline.
3. **Combined toy detector — 0 false drops, 0 false occupancy**, but only
   when restricted to the seat gates. The statistic cannot tell cat from
   human by magnitude; cat activity at gates 4-7 scores 20-80, well over
   any human threshold.
4. Caveat: frames only exist from 21:04:29 (power cycle); ~28s gap at
   21:46:11.

## (1) |fastEMA−slowEMA|, still channel, per-window median

```
tau=(2,60)              g2     g3     g4     g5     g6     g7     g8
learn  21:04-21:20     6.99  10.91   5.53   3.45   1.97   1.13   0.67
EMPTY  21:32-21:39     0.36   0.20   0.80   3.68   3.46   2.13   1.36   <- cat at g5-g7
present 21:40-21:55    7.51  13.91  12.63   7.31   2.78   1.44   0.91
still-min 21:49        2.60   5.17   5.22   2.39   0.86   0.60   0.31
--- move channel, same taus ---
EMPTY  21:32-21:39     0.23   0.26   0.38   0.37   0.57   0.46   0.39
still-min 21:49        0.25   0.36   0.43   0.63   0.56   0.61   0.30   <- no separation
```

Per-minute (still, g2/g3): 21:40 **55.6** → 21:44 14.3 → 21:48 11.1 →
**21:49 5.17** → 21:50 26.8. Never touches the 0.2-0.4 empty band; bridges
21:49 continuously.

## (2) noise floor, robust EMA of |Δframe|, tau=10s

```
                        g2     g3     g4     g5     g6
occupied-learning      0.229  0.335  0.233  0.208  0.146
truly EMPTY            0.111  0.079  0.076  0.096  0.131
seated 21:40-21:55     0.258  0.450  0.567  0.419  0.184
21:49 (very still)     0.115  0.149  0.127  0.141  0.112
```

Occupied-learning sits 3-4x above empty at gates 2-3 — the convergence test
fails. Only ~21% of frames change at all between samples, so the floor is
largely a quantization statistic. An asymmetric min-tracking floor is more
occupancy-immune in shape but collapses toward 0 in quiet gates; EMA10 with
a 0.10 clamp behaves better.

## (3) toy detector vs shipped, 21:05-21:52

Score = max over gates 2-3 of stat/floor; ON 20, OFF 10, on-hold 1.5s,
off-hold 20s.

```
toy                       shipped
21:05:14 occupied         21:04:35 occupied
                          21:09:30-21:16:10: 6 false flip pairs while seated
21:20:23 vacant           (user left ~21:2x — correct on both)
                          21:30:18 occupied  <- cat, false
                          21:35:41 vacant
21:39:59 occupied         21:39:55 occupied
                          21:49:56 vacant    <- THE false drop
                          21:50:01 occupied
(no flips through 21:51:43)
```

False drops while seated 21:40-21:55: toy 0, shipped 1. False occupancy in
the empty window: toy 0% of frames, shipped 100% (latched from the cat).
Score at the failure minute: min 22.1 / p50 35.0, all above ON, vs empty
p90 of 9.5.

## Follow-up: bathroom D0:6E, 05:00-06:00 (blind test)

Ground truth (withheld until after the run): bathroom EMPTY, wife in the
kitchen through the shared wall.

Hardware finding first: **gates 0-1 carry no still data at all** (still = 0
for all 39k frames; move pinned at constants 9/11). Still detection starts
at gate 2 on the LD2410.

The toy detector saw near-continuous activity for the first 46 minutes
(occupied ~68% of the hour); the shipped detector saw two short bursts
(~20%). Both were FALSE — the toy amplifies through-wall bleed exactly as
well as presence (raw still bleed excursions to 60-85 at gates 2-3 against
a 7/6 baseline). The shipped detector's two entries (05:11:49 g[2,3,4],
05:36:24 g[2,3,4,5,6]) were themselves arrival-gate leaks.

Two shapes in the hour: most minutes g2/g3-led with g5+ at noise; blocks at
05:34-05:36 and 05:39-05:40 invert (g5/g6 exceed g2/g3). Quiet tail
05:46-06:00 at stat/floor 1.5-4.7 everywhere (true noise level).

Conclusion: the slow/fast statistic is a retention/hold statistic ONLY —
it must sit behind entry gating, never drive entry.
