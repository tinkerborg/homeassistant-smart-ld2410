# 22 V3 — Arrival-gated entry: adjudicated corpus sweep

Read-only replay of a `sqlite3 .backup` snapshot of `config/smart_ld2410/frames.db`
through the shipping `Detector`, over every sensor with recorded frames:

| sensor | frames | span | `move_ceiling` | threshold at `arrival_frac` 0.6 |
| --- | --- | --- | --- | --- |
| `99:CD:E0:3E:66:15` | 177 651 | 2.9 d | 29.2 | 17.5 |
| `D0:6E:81:D2:5D:A6` | 2 790 030 | 11.1 d | 100.0 | 60.0 |
| `FD:68:3B:41:6E:FF` | 2 613 002 | 6.6 d | 100.0 | 60.0 |

Runs are full `Detector.process()` passes at otherwise-default `DetectorConfig`
— `energy_floor` 30 included — varying only `arrival_frac` and
`arrival_min_frames`. `arrival_frac` 0 is the pre-22 control. Closed
detection-scope `Episode` rows and the per-frame occupancy bit are read straight
off the detector.

Episodes are never matched by identity across runs, because suppressing an entry
re-segments what follows: the control run is the reference, and the question
asked of a gated run is "was occupancy ever true inside this control episode's
own span?", with a 60 s pre-window tolerance so a visit merely segmented
differently is not scored as a loss.

**The control is not ground truth.** The pre-22 detector's own false positives
are what this rule exists to remove, so every apparent loss is adjudicated
against physical evidence (§2) rather than counted because the control called it
occupancy.

`D0:6E` is the downstairs bathroom, boresight through the kitchen wall; its
`sensors` row carries a stale name and room, and the label events fix its
geometry. §6.5 (departure release) is out of scope: unimplemented and inactive.

**Verdict: do not enable at the shipping defaults — `arrival_min_frames` = 3 is
the defect, not `arrival_frac`. At `arrival_frac` 0.55 with `arrival_min_frames`
= 1 the rule loses no adjudicated-genuine dwell on any sensor, admits both
labeled toilet visits, and leaves every labeled out-of-room window at zero
entries and zero occupancy. Ship that pair, or re-measure it against fresh
labels before enabling — `FD:68` carries no labels at all.**

## 1. Corpus sweep at the defaults (§6.1)

| sensor | entries control | entries at 0.6/3 | occupied control | occupied at 0.6/3 | change |
| --- | --- | --- | --- | --- | --- |
| `99:CD` | 20 | 20 | 1 369 s | 1 253 s | −8.5 % |
| `D0:6E` | 152 | 44 | 459 834 s | 406 548 s | −11.6 % |
| `FD:68` | 303 | 117 | 349 713 s | 289 348 s | −17.3 % |

Entries are occupancy rising edges. `99:CD` is untouched: its ceiling learned to
29.2, so its threshold is 17.5 and nothing it records fails it.

Tagging the control run as `23-v1 §1` did (`long_still_dwell`: `entered`,
≥ 300 s, `still_frac ≥ 0.6`; `pegged`: peak raw move ≥ 95) gives 17 tagged
losses at the defaults — 12 on `D0:6E`, 5 on `FD:68`, all `long_still_dwell`.
`FD:68`'s three apparent `pegged` losses dissolve under a 30 s pre-window
tolerance; they are re-segmentation, not loss. One of them is `23-v1 §1`'s known
zero-duration `pegged` episode, still unscoreable.

Those 17 are the population §2 adjudicates.

## 2. Adjudication (§6.1)

### 2.1 What the labels calibrate

Instantaneous peak still energy is worthless as an occupancy signal on `D0:6E`,
and the labels prove it: the 399 s `empty` window — nobody in the room — reaches
a still peak of 100, with a median of 10. Sustained still is not much better:
the labeled through-wall `stove` and `island` windows hold still at a median of
79–94 for their whole span. A still channel that is high, even for minutes, does
not mean a person is in the room.

What does separate the labeled in-room visits from everything else is moving
energy at onset:

| labeled window | duration | onset move | peak move | still ≥ 50 | longest still ≥ 50 | move gates ≥ 25 |
| --- | --- | --- | --- | --- | --- | --- |
| `toilet` 01:24:23 | 55.7 s | 100 | 100 | 1.00 | 55.7 s | 1,2,3,4 |
| `toilet` 03:15:27 | 429.2 s | 100 | 100 | 0.97 | 315.6 s | 0,1,2,3,4 |
| `stove` 03:10:54 | 101.2 s | 45 | 37 | 1.00 | 101.2 s | 0,2,3,4 |
| `island` 03:12:41 | 59.9 s | 42 | 42 | 1.00 | 59.9 s | 0,2,3 |
| `stove` 01:22:20 | 25.4 s | 35 | 35 | 0.28 | 6.3 s | 0,4 |
| `empty` 03:27:07 | 398.6 s | 26 | 38 | 0.24 | 64.7 s | 0,2,3 |

`onset move` is the strongest whole-frame moving energy in [t0 − 10 s, t0 + 20 s].
In-room: 100. Everything out-of-room: ≤ 45. That is the discriminant used below,
alongside frame rate (a stalled BLE link fabricates dwells), move gate span, and
sustained still where the sensor's still channel carries information.

`device_occupancy` is useless as evidence: it reads 1 through the entire `empty`
window and, on `D0:6E`, through every window examined.

### 2.2 The 17, adjudicated

| sensor | start (UTC) | duration | onset move | peak move | still ≥ 50 | run ≥ 50 | move gates | verdict |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `D0:6E` | 2026-09-04 01:39:07 | 388 s | 57 | 70 | 0.17 | 8.6 s | 0,2,3,4,5,6 | **GENUINE** |
| `D0:6E` | 2026-09-05 05:45:10 | 348 s | 56 | 56 | 0.56 | 182 s | 0,2,3 | **GENUINE** |
| `D0:6E` | 2026-09-05 14:45:18 | 926 s | 98 | 98 | 0.54 | 202 s | 0–6 | **GENUINE** |
| `D0:6E` | 2026-09-05 17:01:13 | 330 s | 63 | 63 | 0.46 | 101 s | 0,2,3 | **GENUINE** |
| `D0:6E` | 2026-09-06 13:31:02 | 473 s | 69 | 69 | 0.47 | 200 s | 0,2,3 | **GENUINE** |
| `D0:6E` | 2026-09-08 02:01:04 | 1604 s | 94 | 94 | 0.73 | 709 s | 0,1,2,3 | **GENUINE** |
| `D0:6E` | 2026-09-09 01:04:06 | 433 s | 71 | 71 | 0.26 | 31.7 s | 0,1,2,3 | **GENUINE** |
| `D0:6E` | 2026-09-10 03:34:23 | 370 s | 73 | 73 | 0.51 | 132 s | 0,2,3 | **GENUINE** |
| `FD:68` | 2026-09-05 13:49:42 | 721 s | 39 | 70 | latched | — | 1–6 | **GENUINE** |
| `D0:6E` | 2026-09-03 02:57:16 | 1261 s | 23 | 49 | 0.63 | 264 s | 0,1,2,3 | ARTIFACT |
| `D0:6E` | 2026-09-05 01:55:14 | 318 s | 24 | 50 | 0.59 | 109 s | 0,1,2,3 | ARTIFACT |
| `D0:6E` | 2026-09-05 16:35:37 | 1069 s | 38 | 41 | 0.55 | 141 s | 0,2,3 | ARTIFACT |
| `D0:6E` | 2026-09-10 01:58:12 | 2550 s | 28 | 35 | 0.17 | 24.7 s | 0,1,5,6 | ARTIFACT |
| `FD:68` | 2026-09-04 15:33:00 | 399 s | 19 | 26 | latched | — | 1 | ARTIFACT |
| `FD:68` | 2026-09-05 12:44:05 | 625 s | 26 | 26 | latched | — | 1 | ARTIFACT |
| `FD:68` | 2026-09-05 01:56:19 | 326 s | 43 | 52 | latched | — | 1,2,3,4,5 | UNCLEAR |
| `FD:68` | 2026-09-09 01:08:29 | 386 s | 23 | 46 | 0.49 | 86.9 s | 1,2,3,4 | UNCLEAR |

**9 genuine, 6 artifact, 2 unclear.** The nine genuine all carry an onset burst
of 56–98 — above every out-of-room reference — and most span four or more gates.
The four `D0:6E` artifacts have onset 23–38 and peak move 35–50, squarely inside
the labeled `stove`/`island`/`empty` range, with no arrival burst anywhere.

The headline 2550 s "dwell" of 2026-09-10 01:58:12 is one of them: peak move 35,
below the `empty` window's own 38, no onset burst, still above 50 for only 25 s
of 2550, and its still energy centred on gate 6 rather than the near band. It is
not a person.

`FD:68`'s still channel sits at a median of 100 in **94.3 %** of the recording's
5-minute windows (against 2.6 % for `D0:6E`). It is latched, so `still_frac ≥ 0.6`
is satisfied there by default and its `long_still_dwell` population of 78 is not
a meaningful group. Its five losses are adjudicated on the move channel alone,
and with no labeled reference for that sensor two of them stay unclear.

### 2.3 The 2026-09-10 03:34:23 case

The labelling session's last two events are `empty` at 03:27:07 and `none` at
03:33:45; nothing is recorded after. The lost dwell begins 37.7 s after that
final press, at 23:34 local.

The frames tell the story without ambiguity. Through the whole `empty` window and
up to 03:34:20 the moving channel sits at 14–28 and the still channel at 6–16 —
an empty room. At 03:34:22 move jumps to 72, at 03:34:24 to 73 with still going
to 100, and the still channel then holds 43–100 for the next six minutes with
intermittent move bursts of 27–50. A person walked in and stayed.

The user pressed `none` to close the `empty` label, then walked back into the
bathroom half a minute later. **GENUINE**, and the clearest single loss in the
corpus.

It fails the shipping rule by exactly one frame: its onset burst reaches the 60.0
threshold in 2 frames, and `arrival_min_frames` is 3.

### 2.4 What the defaults suppress correctly

Beyond the 17, the defaults run removes 119 further control entries on `D0:6E`
and 169 on `FD:68`. Adjudicated by the same evidence, these are the rule working:

- **BLE dropouts.** The control's largest "dwells" are stalled links. The 5175 s
  interval of 2026-09-09 11:34 holds 303 frames — 0.06 Hz — around a
  `disconnect` at 11:42:15 and a `connect` at 12:59:46: occupancy latched across
  a 77-minute outage. The 2335 s interval of 15:43 likewise spans a `disconnect`
  at 0.33 Hz; the 2605 s interval of 00:33 runs at 3.80 Hz.
- **A dead still channel.** Nine long `D0:6E` losses run 978–14 368 s with a
  still median of 6–7 — *below* the labeled empty room's 10 — peak move 27–71,
  no onset burst, and the global move maximum arriving late in the span. The
  4-hour "occupancy" of 2026-09-05 15:25 is one of these.

An earlier reading of this corpus counted those as probable occupancy on peak
still energy alone. Peak still is the wrong statistic, per §2.1; on the sustained
measure they are indistinguishable from an empty room.

## 3. Labeled sessions (§6.2)

Two sessions on `D0:6E`, twelve intervals, each running from its label event to
the following `none`. Island intervals are trimmed 5 s at the tail. The `stove`
interval beginning 03:08:24 is excluded: 80 frames over 75 s is a BLE dropout,
and the label was on while the user was absent.

Occupied fraction of each window, with entries in brackets where non-zero:

| label | start | duration | control | 0.6/3 | 0.45/1 | 0.55/1 |
| --- | --- | --- | --- | --- | --- | --- |
| hall-walk-by | 01:21:58 | 11.1 s | 0.50 [1] | 0.00 | 0.00 | 0.00 |
| stove | 01:22:20 | 25.4 s | 1.00 | 0.00 | 0.00 | 0.00 |
| island | 01:22:49 | 9.8 s | 1.00 | 0.00 | 0.00 | 0.00 |
| stove | 01:23:23 | 16.8 s | 1.00 | 0.00 | 0.00 | 0.00 |
| island | 01:23:45 | 7.5 s | 1.00 | 0.00 | 0.00 | 0.00 |
| hall-walk-by | 01:24:02 | 13.7 s | 1.00 | 0.00 | 0.00 | 0.00 |
| **toilet** | 01:24:23 | 55.7 s | 1.00 | **1.00** | **1.00** | **1.00** |
| ~~stove~~ | ~~03:08:24~~ | ~~75.1 s~~ | ~~0.11~~ | ~~0.00~~ | ~~0.00~~ | ~~0.00~~ |
| stove | 03:10:54 | 101.2 s | 1.00 | 0.00 | **1.00** | 0.00 |
| island | 03:12:41 | 59.9 s | 1.00 | 0.00 | **1.00** | 0.00 |
| **toilet** | 03:15:27 | 429.2 s | 1.00 | **1.00** | **1.00** | **1.00** |
| empty | 03:27:07 | 398.6 s | 0.40 | 0.40 | 0.40 | 0.40 |

Zero entries in every out-of-room window at every gated setting, and the
control's false `hall-walk-by` entry is suppressed by all of them.

Both toilet visits are admitted at all three settings, entering *before* the
label event rather than inside it — 1.4–1.9 s before the first press, 27 s before
the second at 0.6/3 and 0.55/1. Latency is normal in the only sense the labels
can measure: the person was detected on the way in, before they reached the
phone.

Two caveats. At **0.45/1** occupancy begins 4 s before the second `stove` label
and runs through the `island` window: the rising edge falls outside every labeled
interval, so §6.2's entry test passes literally, but a through-wall episode has
started occupancy. 0.55/1 does not do this. And the `empty` window sits at 40 %
occupancy in *every* run including the control — the 03:15 toilet dwell held past
the occupant's departure to 03:29:47. That is §4's exit-side case, not an entry,
and out of scope.

## 4. Entry latency (§6.3)

Delay between the control occupancy rising edge inside a genuine-dwell episode
and the gated one:

| sensor | group | n | 0.6/3 median | 0.6/3 p90 | 0.45/1 median | 0.45/1 p90 |
| --- | --- | --- | --- | --- | --- | --- |
| `99:CD` | `pegged` | 7 | 0.71 s | 2.0 s | **0.00 s** | 0.00 s |
| `D0:6E` | `pegged` | 24 | 2.24 s | 66.2 s | 1.89 s | 54.5 s |
| `D0:6E` | `long_still_dwell` | 25 | 2.05 s | 329.1 s | 1.02 s | 79.1 s |
| `FD:68` | `pegged` | 36 | 8.89 s | 89.6 s | **0.30 s** | 64.1 s |
| `FD:68` | `long_still_dwell` | 54 | 65.6 s | 375.9 s | 31.7 s | 147.7 s |

`arrival_min_frames` = 3 at 10 Hz costs 0.2 s structurally; at the defaults the
measured median on `FD:68` is 65.6 s, two orders of magnitude above it. Dropping
to `arrival_min_frames` = 1 removes most of that: `FD:68`'s `pegged` median falls
to 0.30 s and `99:CD`'s to zero.

`FD:68`'s residual `long_still_dwell` median of 31.7 s is measured over a tag
population that its latched still channel makes meaningless (§2.2); its `pegged`
group is the one that tracks real arrivals there, and it is clean.

## 5. 24-hour replay (§6.4)

The last 24 hours of `D0:6E`, 2026-09-09 03:59:07 to 2026-09-10 03:59:07 UTC,
containing both labelling sessions.

| | entries | occupied |
| --- | --- | --- |
| control | 25 | 16 966 s |
| 0.6/3 | 4 | 1 460 s |
| 0.45/1 | 8 | 2 742 s |

No entry falls inside any labeled out-of-room interval in any run.

The control's three largest intervals — 5175 s, 2335 s, 2605 s — are the BLE
dropouts and frame-loss stretches of §2.4, not visits, and dropping them is
correct. Of the genuine visits, the defaults lose the 03:34:23 walk-in; 0.45/1
recovers it, along with two afternoon dwells at 15:33 and 15:39 and the 03:42
return. Its eight clusters are all consistent with plausible visits.

## 6. Cold start — pass

Three slices replayed from empty detector state, at `arrival_frac` 0 and 0.6,
output identical between the two through the passthrough phase:

| slice | ceiling learned | baseline ready | passthrough frames | occupancy ≠ device bit | first entry |
| --- | --- | --- | --- | --- | --- |
| 120 s before the 429 s toilet visit | +32.1 s | +272.1 s | 2722 | 0 | +0.0 s |
| 120 s before the 55 s toilet visit | +37.0 s | never | 2170 | 0 | +0.0 s |
| corpus start | +206.1 s | +406.1 s | 2510 | 0 | +0.0 s |

Occupancy tracks the device bit exactly for every passthrough frame, and entry is
admitted on the first frame. Arrival gating never blocks a fresh install.

`move_ceiling` closes its first 60 s bucket long before the baseline's five
buckets make the detector ready, so the §2 cold-start clause is satisfied by the
passthrough path rather than by the unlearned branch, which this corpus never
exercises once the baseline is ready.

## 7. Candidate-reset accumulation — not the cause

`_arrival_frames` clears whenever activity lapses, so arrival-scale frames could
in principle scatter across consecutive candidates and never reach
`arrival_min_frames` within one. A counterfactual detector, identical except that
the counter is cleared only on entering occupancy — the permissive upper bound on
what fixing this could recover — was replayed over both large sensors:

| sensor | | entries | occupied | tagged losses | genuine losses |
| --- | --- | --- | --- | --- | --- |
| `D0:6E` | shipped | 44 | 406 548 s | 12 | 8 |
| `D0:6E` | accumulating | 44 | 406 549 s | 12 | 8 |
| `FD:68` | shipped | 117 | 289 348 s | 5 | 1 |
| `FD:68` | accumulating | 117 | 289 429 s | 5 | 1 |

Zero entries recovered, zero losses recovered, and latency medians improve by
0.13 s and 0.50 s. Reset scattering is not an implementation defect worth fixing:
the frames simply are not there to accumulate.

An earlier reading of this corpus reported resets as a contributing mechanism.
That was a measurement error — the reset counter also decremented on every
occupied frame — and this run supersedes it. Admitted-gate moving energy also
equals whole-frame moving energy in all 17 windows, so gate-class exclusion is
not a mechanism either. What remains is the threshold itself: 9 of 17 windows
never reach 60.0 at all, and the other 8 reach it in 1 or 2 frames.

## 8. Operating point

Full replays at two candidate settings, scored against the §2 adjudication:

| setting | sensor | entries | occupied | genuine lost | unclear lost | artifact lost |
| --- | --- | --- | --- | --- | --- | --- |
| 0.6 / 3 | `D0:6E` | 44 | 406 548 s | **8** | 0 | 4 |
| 0.6 / 3 | `FD:68` | 117 | 289 348 s | **1** | 2 | 2 |
| 0.55 / 1 | `D0:6E` | 61 | 415 253 s | **0** | 0 | 4 |
| 0.55 / 1 | `FD:68` | 150 | 308 144 s | **0** | 2 | 2 |
| 0.45 / 1 | `D0:6E` | 68 | 418 301 s | **0** | 0 | 2 |
| 0.45 / 1 | `FD:68` | 171 | 324 099 s | **0** | 0 | 2 |

`99:CD` is unaffected at every setting: 20 entries throughout.

Both `min_frames` = 1 settings lose no adjudicated-genuine dwell on any sensor
while still removing 84 control entries on `D0:6E` and 132–153 on `FD:68`, and
both admit every labeled toilet visit with zero entries in every labeled
out-of-room window.

They differ on the margin. **0.55/1** holds every out-of-room window at zero
occupancy as well as zero entries, at the cost of the two `FD:68` UNCLEAR
windows and a slower `FD:68` latency tail. **0.45/1** is faster and keeps the two
unclear windows, but lets one through-wall episode start occupancy 4 s ahead of
the second `stove` label (§3).

Since §6.1 admits no trade and neither unclear window is established as genuine,
**0.55 / 1** is the recommended pair: it is the setting that keeps everything the
labels prove is a person and rejects everything the labels prove is not.

What decides the shipping question is the evidence base, not the frontier.
`arrival_frac` is doing its job at anything from 0.45 to 0.6; `arrival_min_frames`
= 3 is what loses people, and it loses the clearest genuine dwell in the corpus
(§2.3) by a single frame. Change it to 1. The labeled evidence behind §6.2 is
still twelve intervals from one session on one sensor, and `FD:68` has none at
all, so a v4 measurement against fresh labels — particularly a labeled departure
and a labeled `FD:68` session — should confirm the pair before it ships enabled.

## 9. Reproducing

Analysis scripts (scratch only; they read a private recording and are not
checked in):

- `v22_run.py` / `v22_run2.py` — full corpus replay per sensor at a given
  `arrival_frac` and `arrival_min_frames`, recording detection-scope episodes,
  occupancy intervals, rising edges and the `move_ceiling` trajectory.
- `v22_labels.py` — label intervals from the `events` table with per-interval raw
  energy, island trimming and the contaminated-interval exclusion.
- `v22_analyse.py` — §1, §3, §4 and §5 tables.
- `v22_forensic.py` — the §2 evidence profile per window: onset move, burst
  texture, sustained still, gate span, frame rate, device bit, pre-window state.
- `v22_why.py` — instrumented run inside each lost-entry window: arrival frame
  counts and admitted versus raw moving energy.
- `v22_sticky.py` — the §7 counterfactual detector.
- `v22_sweep.py` — the threshold frontier that located `min_frames` = 1.
- `v22_coldstart.py` — passthrough-phase slices from empty detector state.

All read `frames.db`, a `sqlite3 .backup` snapshot taken over a read-only
connection; nothing touches the live database, and the `events` and `frames`
tables are read through direct read-only `sqlite3` rather than `FrameStore`.
