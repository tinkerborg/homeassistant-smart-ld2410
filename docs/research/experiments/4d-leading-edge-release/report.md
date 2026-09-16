# Experiment 4d: leading-edge-conditioned release

Extends 4c. Variants: A = release countdown resets only on frames with
suppressed lead ≤1, plus a near-lead grace window; a = A plus retention
refresh vetoed by far-lead activity; c = hold refreshed by near-lead OR
retention ≥ threshold at the occupancy's gates. Data: 4b/4c overlap
streams + `livingroom-reset-seated-fd68.db`. Scripts: rel*.py here.

## Verdict

The leading-edge release neutralizes the neighbor exactly as designed —
and cannot be paired with a retention refresh. The far-lead veto meant to
reconcile them fails on both fixtures for one reason: lead ≥2 is not the
neighbor's signature once someone is IN the room — it is also the
occupant's own (bathroom occupant leads g2-g4; living-room occupant
g2-g7). The veto fires exactly where retention is needed.

## Overlap streams (hold_s=30; ! = released with user present)

| variant | bath ctrl (target 22:06:43) | MAX (target ~22:07:13) | kitchen entry |
|---|---|---|---|
| shipped | 22:06:43 | 22:08:27 | 21:58:50 |
| 4c (entry only) | 22:06:43 | 22:08:27 | NEVER |
| A grace=0 | 22:05:43 ! | 22:05:43 ! | NEVER |
| A grace=30 | 22:06:13 ! | 22:06:13 ! | NEVER |
| **A grace=60** | **22:06:43** | **22:06:43** | **NEVER** |
| A grace=90 | 22:06:43 | 22:07:13 | NEVER |
| c (near OR ret≥20) | none by 22:10 | none by 22:10 | NEVER |
| c ret≥100 | 22:08:10 | 22:09:11 | NEVER |

Under A grace=60 the MAX timeline is bit-identical to the bathroom
control: neighbor fully neutralized, entry and release (−104s vs 4c).
hold_s=60 shifts identically. SUM unchanged (known-invalid mix). Note: A's
22:06:43 hit is arithmetic off the last near-lead (22:05:13 + grace), not
departure detection.

## FD:68 seated fixture (truth: re-entry 21:39:40, seated through 21:55)

| variant | re-entry | drops 21:40-21:55 | % vacant seated | occupied while empty |
|---|---|---|---|---|
| shipped | 21:39:55 | 21:49:56 | 36.1 | 31.6 (cat) |
| 4c | 21:40:15 | 21:49:56 | 36.1 | 0.0 |
| A grace=60 | 21:40:15 | **21:42:15** | 87.5 | 0.0 |
| a (+ret, far-veto) | 21:40:15 | 21:42:15 | 87.5 | 0.0 |
| **c (near OR ret≥20)** | 21:40:15 | **none** | **0.0** | **0.0** |

Variant A is wrong here: the seated user's last near-band lead is ~21:43
and never recurs — A is a motion-recency latch, wrong for any sofa/desk
occupancy. Departure test (occupancy seeded 21:11 at the seat gates):
shipped drops her immediately (21:11:30); c ret≥20 holds to **21:19:11**,
ret≥10 to 21:20:58 — retention both carries and releases on time in a
neighbor-free room, including 21:49.

## Why they can't be combined

Median retention (stat/floor) in the windows that must be told apart:

| window | g2 | g3 | g4 |
|---|---|---|---|
| bath ctrl HOLD (occupant still) | 98 | 134 | 153 |
| MAX RELEASE (neighbor only) | **178** | **195** | 128 |
| kitchen ctrl RELEASE (neighbor only) | 155 | 176 | 52 |
| FD:68 HOLD (seated) | 25 | 44 | 37 |
| FD:68 HOLD (21:49 still minute) | 20 | 35 | 40 |
| FD:68 RELEASE (empty) | 2.4 | 1.9 | 2.8 |

Neighbor-only scores HIGHER than the genuine still occupant and an order
of magnitude above the FD:68 occupant who must be held; both rooms' quiet
floors are ~2-6, so no threshold or room-relative normalization orders
these correctly. 4b's inversion holds at per-gate resolution. The far-lead
veto suppresses retention ~100% of post-departure MAX (correct) but also
through both genuine hold windows (fatal).

## What this leaves

- Variant A (grace 60): shippable against the neighbor and only that.
- Form c (retention refresh): shippable in a neighbor-free room and only
  that — and genuinely good there.
- The missing discriminator — through-wall scatterer vs still occupant at
  the same gates, after entry — is absent from lead, score, and retention
  alike. The promising direction: entry-established OWNERSHIP (the
  occupant demonstrably reached g0/1 at entry; the neighbor never can)
  that decays slowly, with retention allowed to refresh only while
  ownership is alive — rather than a per-frame far-lead veto.
