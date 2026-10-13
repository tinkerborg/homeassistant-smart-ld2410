# Recorded fixtures

Real sensor recordings with user-confirmed ground truth, extracted from the
live databases. Schema matches store.py's `frames` and `events` tables. All
timestamps unix UTC; local times below are America/New_York. Sensor
D0:6E:81:D2:5D:A6 is the downstairs bathroom (in-wall, boresight through the
kitchen wall); FD:68:3B:41:6E:FF is the living room rear.

## throughwall-morning-d06e.db

2026-09-11 04:55–06:05. Ground truth: bathroom EMPTY the entire window; one
person active in the kitchen beyond the shared wall roughly 05:00–05:46
(bursty: solid 05:11–05:19, flare-ups 05:28–29, 05:34–37, 05:42). Any
occupancy here is a false positive. The shipped detector entered falsely at
05:11:49 and 05:36:24. Known hardware: bursty gate-0 move chatter on this
unit; still channel reports zero at gates 0–1.

## bathroom-visit-2204-d06e.db

2026-09-11 21:55–22:12. Ground truth: one genuine bathroom visit,
occupancy 22:04:01–22:06:43 (user-confirmed), walk-in lead-in and departure
included. Empty before and after.

## livingroom-reset-seated-fd68.db

2026-09-11 20:55–22:00. Ground truth: sensor power-cycled ~21:00 (clearing
a corrupted still channel), detector learning reset while the user sat
5–6 ft away (gates 2–3). User seated ~21:04–21:20 (typing, otherwise
still), out of the room ~21:20–21:39 (a cat around gates 4–6 near 21:30),
walked back in 21:39:40 and seated through 21:55. 21:49 is a fully-still
minute the shipped detector wrongly released (vacant 21:49:56). Frames
before ~21:04 do not exist (power cycle).

## stove-case-0913-d06e.db / stove-case-0913-fd68.db

2026-09-13 09:10–10:12, both sensors. Ground truth narrative: user in
the living room, walked to the downstairs bathroom and used the toilet
for ~30–60 s (occupancy on 09:24:03 — correct), walked out into the
kitchen and stayed at its FAR end (not the stove) through the window.
The bathroom stayed "detected": the walk-out never registered as a
crossing (ownership stayed disarmed) and the user's own far-kitchen
activity through the wall sustained retention (retention_max ~113,
gates clear, score ~0) — the leave-then-neighbor-activity failure
recorded live with one person in both roles, at longer range than the
stove/island label sessions. Later the user returned to
the bathroom for ~10–15 minutes of motion-rich activity (clipping hair,
roughly 09:50–10:05), left, and the room released at 10:05:32; the
occupied event at 10:07:16 is the user returning (genuine). Any release
design must turn the
bathroom off shortly after the 09:24 visit's walk-out while keeping the
seated-occupant fixtures held. Possible upstairs activity during the
window — unconfirmed.

## labeled-sessions-0909-d06e.db

2026-09-09 21:15–23:35, from the dev instance. Contains kind='label' events
(ground-truth select entity): toilet/stove/island/hall-walk-by/empty
sessions. Caveats recorded at the time: the stove interval starting
~23:08:24 is contaminated (BLE dropout, label on while user absent) — the
229 s frame gap 23:05:42–23:09:31 self-identifies; trim the last ~5 s of
island intervals; arrival motion begins up to ~27 s before a label flip.

## labeled-loop-0915.db

2026-09-15 19:20–19:30, bathroom (D0:6E), kitchen (B3:26), living room
(FD:68) in one file with `labels(person, room, ts_start, ts_end, note)`
and `states` tables. Ground truth from the user's narrative, timed by the raw traces:
user in the living room, walked to the bathroom (transit ~19:24:10–20),
used the toilet 19:24:20–19:25:38 (bathroom gates 2–4 saturated), walked
to the kitchen 19:25:40–19:26:42 (stood in two spots, looped the island —
kitchen saturated; bathroom sees it through the wall as still 22–44 /
move ≤26 at gates 2–4), walked out past the bathroom door and back into
the living room ~19:26:55. Wife seated near the living-room sensor the
whole window (LR still pinned at 100; the user's return is invisible
against her). Bathroom move gates 0–1 latched at 18 throughout, so no
near-band approach is visible for the entry. Watch/Bermuda reported
"Kitchen" for the entire window — unusable here. Shipped detector:
bathroom entered 19:24:20 (correct) and had not released by 19:32;
kitchen 19:25:41–19:27:14.

## living-room-continuous-occupancy-2026-09-16.db

2026-09-16 11:15–11:58, the REPLACEMENT living-room sensor
(68:43:B2:C2:7C:4A, "Living Room Back", frames from 11:19:59), bathroom
(D0:6E) and kitchen (B3:26), with `labels` and `states` tables. Ground
truth (per user, timed by the traces): user in the living room setting
up the new sensor until ~11:38:32; walked past the bathroom to the
kitchen (bathroom saw nothing); kitchen 11:39:12–11:40:20 (kitchen
saturated, bathroom through-wall still 43–89); walked back past the
bathroom door 11:40:20–11:40:36 — the bathroom falsely entered
11:40:18–11:40:34 on the walk-by (still 95–100, move 42); entered the
living room at 11:40:36 and stayed seated. The new living-room sensor
reads ambient (8–10) at gate 2 while the room is empty — the old unit's
pegged gate-2 still is gone — yet the detector still flapped on the
seated user (vacant 11:42:15, occupied 11:52:22, …). An earlier version
of this fixture (old FD:68 unit, 07:45–09:47, 107 flips) was replaced.

## living-room-mixed-2026-09-16.db

2026-09-16 10:00–17:00, living room (old unit FD:68 until 11:15:27, then
the replacement 68:43:B2:C2:7C:4A from 11:19:59), bathroom (D0:6E) and
kitchen (B3:26), with `labels` and `states` tables. Unlabeled beyond
what living-room-continuous-occupancy-2026-09-16 documents for
11:15–11:58; a mixed day of ordinary use, 270 occupancy transitions
across the four sensor ids.

## bathroom-false-clear-2026-09-16.db

2026-09-16 20:03:41–20:14:41, bathroom (D0:6E) only, with `labels` and
`states`. Ground truth (per user): in the bathroom the whole visit
(~20:08:45–20:13:10 by the traces), making extensive motion trying to
get it to detect. Detector: occupied 20:09:00, a 3 s vacant/occupied
blip at 20:09:41, then a FALSE CLEAR 20:10:38–20:11:31 with the user
present (still 37–78 at gates 2–4 in the gap, move only 12–23), re-entry
at 20:11:31 on move 100, and an early release at 20:12:31 while still
read 53–83 for another 30 s. Five minutes of empty lead-in included.

## overnight-2026-09-16.db

2026-09-15 23:00 – 2026-09-16 07:00, all five sensors (bathroom D0:6E,
kitchen B3:26, living room FD:68, dining 99:CD, mud room 20:4C), with a
`labels` table. Ground truth (per user): both humans in bed upstairs the
whole night, so every downstairs detection is the cat or a false
positive. Twenty-two occupancy episodes, all 15–77 s, in clusters:
23:03–23:10 (dining→mud→mud→dining, move 100 at gates 1–2), 23:31–23:39
(dining/mud/living, weak), 02:06–02:28 (living/dining/mud ×8, mixed),
06:06–06:14 (dining ×4, move 100 at gates 1–2), plus two lone bathroom
blips at 04:03 and 05:27 (move ≤46, still 100 at gate 3, 3–4 hot frames
each, no other sensor active within ±5 min). Cause unconfirmed: the user
recalls possibly using an upstairs bathroom around 04:00 and his wife
around 05:30, so through-ceiling bleed from the floor above is one
candidate; a still-channel artifact on that unit is another. The
clusters read as the cat doing rounds; whether 06:06–06:14 involved a
human is unconfirmed.
The kitchen sensor never entered: it saw only four faint brushes at gate
1 (move 31–38, still 69–84) coinciding with the clusters. Mounting
explains it — dining and mud-room sensors sit at standard outlet height,
the kitchen sensor is at counter height with the counter between it and
the floor, so a floor-level cat is largely shielded while a standing
human is in-beam.

## cat-kitchen-0915.db

2026-09-15 19:30–19:51, kitchen (B3:26) and bathroom (D0:6E), with a
`labels` table. Ground truth (per user): no humans in the kitchen; the
cat (Max) produced the only activity — two bursts at kitchen gates 4–6,
19:32:38–19:33:05 (still to 67, move to 27) and 19:49:05–19:49:35 (still
to 96, move to 45). The shipped detector did not enter on either; the
device's own occupancy bit (which the InvisOutlet follows) did, and the
kitchen light came on. The bathroom sensor is included for the
through-wall view of a cat-sized target.

## labeled-walk-0915.db

2026-09-15 18:29–18:54, all five sensors in one file (B3:26:9E:EE:C5:11 is
the kitchen). Carries a `labels(person, room, ts_start, ts_end, note)`
table with per-person room spans, built from the user's narrative and the
three sensors' raw traces. Ground truth: user in the living room until
18:50:36; wife enters the kitchen 18:50:40 and stays until 18:52:20 (at
the stove from ~18:51:24); user in the bathroom 18:50:52–18:51:11, in the
kitchen with her 18:51:11–18:51:36, living room 18:51:36–18:51:47,
bathroom again 18:51:48–18:52:11, then living room. Both bathroom visits
saturate gates 2–4 with the kitchen occupied the whole time; the
both-at-the-stove span 18:51:24–18:51:46 is the through-wall reference
(bathroom gate 2 stays ≤30, peak at gate 4). Bathroom move gates 0–1 are
latched at 18 throughout. The shipped detector entered the bathroom at
18:50:53 and never released within the window.

## bathroom-session-2026-09-29.db

2026-09-29 00:45:00–01:14:57, bathroom (D0:6E) and kitchen (B3:26), with
`labels` and `states` tables. Ground truth (per user): on the toilet the
whole visit, 00:56:04.7 (first move ≥ 60) to 01:08:26.4 (user hit the
light switch on the way out; last move ≥ 60 at 01:08:26.3). Lead-in
00:45–00:56 and tail after 01:08:30 are unlabeled. Detector cleared
seven times while occupied (00:59:01 7 s, 01:00:03 2 s, 01:02:11 2 s,
01:02:54 55 s, 01:04:47 1 s, 01:05:44 39 s; final clear 01:08:44), every
clear at confidence ~1.0 with gates 2–5/6 active. Motion gates 0–1 read
13–17 on this unit here (no longer latched at 18).

<!-- experiment 67 fixtures -->

## bathroom-visit-2026-10-05-0006.db

2026-10-05 00:03:15–00:22:56, bathroom (D0:6E) and kitchen (B3:26), with `labels`, `states` (live bathroom/kitchen smart_ld2410, InvisOutlet kitchen occupancy, bathroom light) and `events` tables. Ground truth (hand-labelled by Claude from the radar plots in experiment 67; not user-confirmed; person unknown): in the bathroom 00:06:15–00:06:37 (high; entry burst, still collapses 00:06:37, kitchen sensor lit; person stepped back out and re-entered at 00:07:11; left into an occupied kitchen); in the bathroom 00:07:11–00:17:56 (high; continuous gate 2-4 presence, exit burst 00:17:45-56 then still collapses; kitchen sensor sees the person at 00:18:25; left into an occupied kitchen). Why it is here: exit into an active kitchen. Caveats: labels are a reading of the radar plots, not a user narrative; visits were found from move >= 90 bursts, so an entry without one can be missing from the labels; the InvisOutlet kitchen often turns on from the bathroom occupant alone.

## bathroom-visit-2026-10-05-0323.db

2026-10-05 03:20:51–03:30:50, bathroom (D0:6E) and kitchen (B3:26), with `labels`, `states` (live bathroom/kitchen smart_ld2410, InvisOutlet kitchen occupancy, bathroom light) and `events` tables. Ground truth (hand-labelled by Claude from the radar plots in experiment 67; not user-confirmed; person unknown): in the bathroom 03:23:51–03:25:50 (medium; single entry burst then seated; gate-2 still fades ~03:25:45 with no exit burst; kitchen InvisOutlet on 03:26:05, kitchen sensor blips 03:26:25; left into an occupied kitchen). Why it is here: exit into an active kitchen. Caveats: labels are a reading of the radar plots, not a user narrative; visits were found from move >= 90 bursts, so an entry without one can be missing from the labels; medium-confidence departures are signal fades without an exit burst, ±10–20 s; the InvisOutlet kitchen often turns on from the bathroom occupant alone.

## bathroom-visit-2026-10-05-0633.db

2026-10-05 06:30:17–06:46:12, bathroom (D0:6E) and kitchen (B3:26), with `labels`, `states` (live bathroom/kitchen smart_ld2410, InvisOutlet kitchen occupancy, bathroom light) and `events` tables. Ground truth (hand-labelled by Claude from the radar plots in experiment 67; not user-confirmed; person unknown): in the bathroom 06:33:17–06:41:12 (high; arrives from the kitchen, presence throughout, exit burst 06:40:30-06:41:12 then still collapses; left into an occupied kitchen). Why it is here: exit into an active kitchen, quiet hold with the kitchen active. Caveats: labels are a reading of the radar plots, not a user narrative; visits were found from move >= 90 bursts, so an entry without one can be missing from the labels; the InvisOutlet kitchen often turns on from the bathroom occupant alone.

## bathroom-visit-2026-10-05-0921.db

2026-10-05 09:18:06–09:30:50, bathroom (D0:6E) and kitchen (B3:26), with `labels`, `states` (live bathroom/kitchen smart_ld2410, InvisOutlet kitchen occupancy, bathroom light) and `events` tables. Ground truth (hand-labelled by Claude from the radar plots in experiment 67; not user-confirmed; person unknown): in the bathroom 09:21:06–09:25:50 (medium; seated, gate-3 motion until ~09:25:42, still fades by 09:26; kitchen off and kitchen sensor quiet; left into a quiet kitchen). Why it is here: ordinary visit. Caveats: labels are a reading of the radar plots, not a user narrative; visits were found from move >= 90 bursts, so an entry without one can be missing from the labels; medium-confidence departures are signal fades without an exit burst, ±10–20 s; the InvisOutlet kitchen often turns on from the bathroom occupant alone.

## bathroom-visit-2026-10-05-1101.db

2026-10-05 10:58:11–11:12:42, bathroom (D0:6E) and kitchen (B3:26), with `labels`, `states` (live bathroom/kitchen smart_ld2410, InvisOutlet kitchen occupancy, bathroom light) and `events` tables. Ground truth (hand-labelled by Claude from the radar plots in experiment 67; not user-confirmed; person unknown): in the bathroom 11:01:11–11:07:42 (high; long active visit with a quieter 11:05-11:06:30 stretch, exit burst to 11:07:42; kitchen sensor and InvisOutlet active at exit; left into an occupied kitchen). Why it is here: exit into an active kitchen. Caveats: labels are a reading of the radar plots, not a user narrative; visits were found from move >= 90 bursts, so an entry without one can be missing from the labels; the InvisOutlet kitchen often turns on from the bathroom occupant alone.

## bathroom-visit-2026-10-05-1404.db

2026-10-05 14:01:15–14:10:48, bathroom (D0:6E) and kitchen (B3:26), with `labels`, `states` (live bathroom/kitchen smart_ld2410, InvisOutlet kitchen occupancy, bathroom light) and `events` tables. Ground truth (hand-labelled by Claude from the radar plots in experiment 67; not user-confirmed; person unknown): in the bathroom 14:04:15–14:05:48 (high; saturated motion whole visit, collapse 14:05:52; kitchen sensor blips 14:06:13; left into an occupied kitchen). Why it is here: exit into an active kitchen. Caveats: labels are a reading of the radar plots, not a user narrative; visits were found from move >= 90 bursts, so an entry without one can be missing from the labels; the InvisOutlet kitchen often turns on from the bathroom occupant alone.

## bathroom-visit-2026-10-05-1951.db

2026-10-05 19:48:04–19:57:00, bathroom (D0:6E) and kitchen (B3:26), with `labels`, `states` (live bathroom/kitchen smart_ld2410, InvisOutlet kitchen occupancy, bathroom light) and `events` tables. Ground truth (hand-labelled by Claude from the radar plots in experiment 67; not user-confirmed; person unknown): in the bathroom 19:51:04–19:52:00 (high; exit burst ends 19:52:00, kitchen sensor saturates 19:52:10; later bathroom blips are bleed; left into an occupied kitchen). Why it is here: exit into an active kitchen. Caveats: labels are a reading of the radar plots, not a user narrative; visits were found from move >= 90 bursts, so an entry without one can be missing from the labels; the InvisOutlet kitchen often turns on from the bathroom occupant alone.

## bathroom-visit-2026-10-05-2115.db

2026-10-05 21:12:40–21:28:40, bathroom (D0:6E) and kitchen (B3:26), with `labels`, `states` (live bathroom/kitchen smart_ld2410, InvisOutlet kitchen occupancy, bathroom light) and `events` tables. Ground truth (hand-labelled by Claude from the radar plots in experiment 67; not user-confirmed; person unknown): in the bathroom 21:15:40–21:16:28 (high; exit burst ends 21:16:28, kitchen saturates 21:16:45; left into an occupied kitchen); in the bathroom 21:22:13–21:23:40 (high; exit burst ends 21:23:40, kitchen saturates 21:24:00; left into an occupied kitchen). Why it is here: exit into an active kitchen. Caveats: labels are a reading of the radar plots, not a user narrative; visits were found from move >= 90 bursts, so an entry without one can be missing from the labels; the InvisOutlet kitchen often turns on from the bathroom occupant alone.

## bathroom-visit-2026-10-05-2305.db

2026-10-05 23:02:33–23:11:36, bathroom (D0:6E) and kitchen (B3:26), with `labels`, `states` (live bathroom/kitchen smart_ld2410, InvisOutlet kitchen occupancy, bathroom light) and `events` tables. Ground truth (hand-labelled by Claude from the radar plots in experiment 67; not user-confirmed; person unknown): in the bathroom 23:05:33–23:06:36 (high; exit burst ends 23:06:36, kitchen saturates 23:06:55; left into an occupied kitchen). Why it is here: exit into an active kitchen. Caveats: labels are a reading of the radar plots, not a user narrative; visits were found from move >= 90 bursts, so an entry without one can be missing from the labels; the InvisOutlet kitchen often turns on from the bathroom occupant alone.

## bathroom-visit-2026-10-05-2327.db

2026-10-05 23:24:16–23:34:54, bathroom (D0:6E) and kitchen (B3:26), with `labels`, `states` (live bathroom/kitchen smart_ld2410, InvisOutlet kitchen occupancy, bathroom light) and `events` tables. Ground truth (hand-labelled by Claude from the radar plots in experiment 67; not user-confirmed; person unknown): in the bathroom 23:27:16–23:29:54 (high; quiet first minute then busy, exit burst ends 23:29:54, kitchen saturates 23:30:05; left into an occupied kitchen). Why it is here: exit into an active kitchen. Caveats: labels are a reading of the radar plots, not a user narrative; visits were found from move >= 90 bursts, so an entry without one can be missing from the labels; the InvisOutlet kitchen often turns on from the bathroom occupant alone.

## bathroom-visit-2026-10-05-2353.db

2026-10-05 23:50:29–00:00:05, bathroom (D0:6E) and kitchen (B3:26), with `labels`, `states` (live bathroom/kitchen smart_ld2410, InvisOutlet kitchen occupancy, bathroom light) and `events` tables. Ground truth (hand-labelled by Claude from the radar plots in experiment 67; not user-confirmed; person unknown): in the bathroom 23:53:29–23:55:05 (medium; seated, fades from ~23:55; kitchen InvisOutlet on 23:55:01 and weak kitchen blip; left into an occupied kitchen). Why it is here: exit into an active kitchen. Caveats: labels are a reading of the radar plots, not a user narrative; visits were found from move >= 90 bursts, so an entry without one can be missing from the labels; medium-confidence departures are signal fades without an exit burst, ±10–20 s; the InvisOutlet kitchen often turns on from the bathroom occupant alone.

## bathroom-visit-2026-10-06-1051.db

2026-10-06 10:48:28–10:57:09, bathroom (D0:6E) and kitchen (B3:26), with `labels`, `states` (live bathroom/kitchen smart_ld2410, InvisOutlet kitchen occupancy, bathroom light) and `events` tables. Ground truth (hand-labelled by Claude from the radar plots in experiment 67; not user-confirmed; person unknown): in the bathroom 10:51:28–10:52:09 (high; exit burst ends 10:52:09, kitchen saturates 10:52:15; left into an occupied kitchen). Why it is here: exit into an active kitchen. Caveats: labels are a reading of the radar plots, not a user narrative; visits were found from move >= 90 bursts, so an entry without one can be missing from the labels; the InvisOutlet kitchen often turns on from the bathroom occupant alone.

## bathroom-visit-2026-10-06-1617.db

2026-10-06 16:14:58–16:24:00, bathroom (D0:6E) and kitchen (B3:26), with `labels`, `states` (live bathroom/kitchen smart_ld2410, InvisOutlet kitchen occupancy, bathroom light) and `events` tables. Ground truth (hand-labelled by Claude from the radar plots in experiment 67; not user-confirmed; person unknown): in the bathroom 16:17:58–16:19:00 (high; exit burst ends 16:19:01, kitchen saturates 16:19:07; left into an occupied kitchen). Why it is here: exit into an active kitchen. Caveats: labels are a reading of the radar plots, not a user narrative; visits were found from move >= 90 bursts, so an entry without one can be missing from the labels; the InvisOutlet kitchen often turns on from the bathroom occupant alone.

## bathroom-visit-2026-10-06-1757.db

2026-10-06 17:54:37–18:03:26, bathroom (D0:6E) and kitchen (B3:26), with `labels`, `states` (live bathroom/kitchen smart_ld2410, InvisOutlet kitchen occupancy, bathroom light) and `events` tables. Ground truth (hand-labelled by Claude from the radar plots in experiment 67; not user-confirmed; person unknown): in the bathroom 17:57:37–17:58:26 (high; exit burst ends 17:58:27, kitchen saturates 17:58:40; later bathroom blips are bleed; left into an occupied kitchen). Why it is here: exit into an active kitchen. Caveats: labels are a reading of the radar plots, not a user narrative; visits were found from move >= 90 bursts, so an entry without one can be missing from the labels; the InvisOutlet kitchen often turns on from the bathroom occupant alone.

## bathroom-visit-2026-10-06-1953.db

2026-10-06 19:50:30–19:59:51, bathroom (D0:6E) and kitchen (B3:26), with `labels`, `states` (live bathroom/kitchen smart_ld2410, InvisOutlet kitchen occupancy, bathroom light) and `events` tables. Ground truth (hand-labelled by Claude from the radar plots in experiment 67; not user-confirmed; person unknown): in the bathroom 19:53:30–19:54:51 (high; arrives from the kitchen, exit burst ends 19:54:52; kitchen sensor quiet after; left into a quiet kitchen). Why it is here: ordinary visit. Caveats: labels are a reading of the radar plots, not a user narrative; visits were found from move >= 90 bursts, so an entry without one can be missing from the labels; the InvisOutlet kitchen often turns on from the bathroom occupant alone.

## bathroom-visit-2026-10-06-2212.db

2026-10-06 22:09:16–22:18:26, bathroom (D0:6E) and kitchen (B3:26), with `labels`, `states` (live bathroom/kitchen smart_ld2410, InvisOutlet kitchen occupancy, bathroom light) and `events` tables. Ground truth (hand-labelled by Claude from the radar plots in experiment 67; not user-confirmed; person unknown): in the bathroom 22:12:16–22:13:26 (high; exit burst ends 22:13:26, kitchen saturates 22:13:35; 22:15-22:17 bathroom blips and live re-triggers are kitchen bleed; left into an occupied kitchen). Why it is here: exit into an active kitchen. Caveats: labels are a reading of the radar plots, not a user narrative; visits were found from move >= 90 bursts, so an entry without one can be missing from the labels; the InvisOutlet kitchen often turns on from the bathroom occupant alone.

## bathroom-visit-2026-10-07-0841.db

2026-10-07 08:38:10–08:59:58, bathroom (D0:6E) and kitchen (B3:26), with `labels`, `states` (live bathroom/kitchen smart_ld2410, InvisOutlet kitchen occupancy, bathroom light) and `events` tables. Ground truth (hand-labelled by Claude from the radar plots in experiment 67; not user-confirmed; person unknown): in the bathroom 08:41:10–08:54:58 (medium; 14 min quiet sit, gate-3 motion to 08:54:55 then fade; InvisOutlet on but kitchen sensor nearly silent; left kitchen unclear). Why it is here: long still sit. Caveats: labels are a reading of the radar plots, not a user narrative; visits were found from move >= 90 bursts, so an entry without one can be missing from the labels; medium-confidence departures are signal fades without an exit burst, ±10–20 s; the InvisOutlet kitchen often turns on from the bathroom occupant alone.

## bathroom-visit-2026-10-07-1206.db

2026-10-07 12:03:05–12:11:39, bathroom (D0:6E) and kitchen (B3:26), with `labels`, `states` (live bathroom/kitchen smart_ld2410, InvisOutlet kitchen occupancy, bathroom light) and `events` tables. Ground truth (hand-labelled by Claude from the radar plots in experiment 67; not user-confirmed; person unknown): in the bathroom 12:06:05–12:06:39 (high; exit burst ends 12:06:40, kitchen saturates 12:06:47; left into an occupied kitchen). Why it is here: exit into an active kitchen. Caveats: labels are a reading of the radar plots, not a user narrative; visits were found from move >= 90 bursts, so an entry without one can be missing from the labels; the InvisOutlet kitchen often turns on from the bathroom occupant alone.

## bathroom-visit-2026-10-07-1542.db

2026-10-07 15:39:43–15:48:41, bathroom (D0:6E) and kitchen (B3:26), with `labels`, `states` (live bathroom/kitchen smart_ld2410, InvisOutlet kitchen occupancy, bathroom light) and `events` tables. Ground truth (hand-labelled by Claude from the radar plots in experiment 67; not user-confirmed; person unknown): in the bathroom 15:42:43–15:43:41 (high; exit burst ends 15:43:41, kitchen saturates 15:44:00; left into an occupied kitchen). Why it is here: exit into an active kitchen. Caveats: labels are a reading of the radar plots, not a user narrative; visits were found from move >= 90 bursts, so an entry without one can be missing from the labels; the InvisOutlet kitchen often turns on from the bathroom occupant alone.

## bathroom-visit-2026-10-07-1639.db

2026-10-07 16:36:59–16:45:49, bathroom (D0:6E) and kitchen (B3:26), with `labels`, `states` (live bathroom/kitchen smart_ld2410, InvisOutlet kitchen occupancy, bathroom light) and `events` tables. Ground truth (hand-labelled by Claude from the radar plots in experiment 67; not user-confirmed; person unknown): in the bathroom 16:39:59–16:40:49 (high; exit burst ends 16:40:49, kitchen saturates 16:40:56; left into an occupied kitchen). Why it is here: exit into an active kitchen. Caveats: labels are a reading of the radar plots, not a user narrative; visits were found from move >= 90 bursts, so an entry without one can be missing from the labels; the InvisOutlet kitchen often turns on from the bathroom occupant alone.

## bathroom-visit-2026-10-07-1731.db

2026-10-07 17:28:46–17:51:07, bathroom (D0:6E) and kitchen (B3:26), with `labels`, `states` (live bathroom/kitchen smart_ld2410, InvisOutlet kitchen occupancy, bathroom light) and `events` tables. Ground truth (hand-labelled by Claude from the radar plots in experiment 67; not user-confirmed; person unknown): in the bathroom 17:31:46–17:46:07 (high; 14 min visit with long quiet stretches (live cleared 4x), exit burst ends 17:46:07; kitchen quiet after; left into a quiet kitchen). Why it is here: long still sit, one of the longest quiet holds. Caveats: labels are a reading of the radar plots, not a user narrative; visits were found from move >= 90 bursts, so an entry without one can be missing from the labels; the InvisOutlet kitchen often turns on from the bathroom occupant alone.

## bathroom-visit-2026-10-07-1822.db

2026-10-07 18:19:28–18:28:41, bathroom (D0:6E) and kitchen (B3:26), with `labels`, `states` (live bathroom/kitchen smart_ld2410, InvisOutlet kitchen occupancy, bathroom light) and `events` tables. Ground truth (hand-labelled by Claude from the radar plots in experiment 67; not user-confirmed; person unknown): in the bathroom 18:22:28–18:23:41 (high; exit burst ends 18:23:41, kitchen saturates 18:24:00; later blips are bleed; left into an occupied kitchen). Why it is here: exit into an active kitchen. Caveats: labels are a reading of the radar plots, not a user narrative; visits were found from move >= 90 bursts, so an entry without one can be missing from the labels; the InvisOutlet kitchen often turns on from the bathroom occupant alone.

## bathroom-visit-2026-10-07-1945.db

2026-10-07 19:42:25–19:51:03, bathroom (D0:6E) and kitchen (B3:26), with `labels`, `states` (live bathroom/kitchen smart_ld2410, InvisOutlet kitchen occupancy, bathroom light) and `events` tables. Ground truth (hand-labelled by Claude from the radar plots in experiment 67; not user-confirmed; person unknown): in the bathroom 19:45:25–19:46:03 (high; exit burst ends 19:46:03, kitchen sensor blips 19:46:13; left into an occupied kitchen). Why it is here: exit into an active kitchen. Caveats: labels are a reading of the radar plots, not a user narrative; visits were found from move >= 90 bursts, so an entry without one can be missing from the labels; the InvisOutlet kitchen often turns on from the bathroom occupant alone.

## bathroom-visit-2026-10-07-2111.db

2026-10-07 21:08:14–21:18:46, bathroom (D0:6E) and kitchen (B3:26), with `labels`, `states` (live bathroom/kitchen smart_ld2410, InvisOutlet kitchen occupancy, bathroom light) and `events` tables. Ground truth (hand-labelled by Claude from the radar plots in experiment 67; not user-confirmed; person unknown): in the bathroom 21:11:14–21:13:46 (high; quiet middle, exit burst ends 21:13:46, kitchen sensor active 21:13:10-21:14:35; left into an occupied kitchen). Why it is here: exit into an active kitchen. Caveats: labels are a reading of the radar plots, not a user narrative; visits were found from move >= 90 bursts, so an entry without one can be missing from the labels; the InvisOutlet kitchen often turns on from the bathroom occupant alone.

## bathroom-bleed-2026-10-10-0007.db

2026-10-10 00:05:00–00:13:09, bathroom (D0:6E) and kitchen (B3:26), with `labels`, `states` (live bathroom/kitchen smart_ld2410, InvisOutlet kitchen occupancy, bathroom light) and `events` tables. Ground truth (exp 67 rule, not user-confirmed): bathroom empty, kitchen occupied — no bathroom burst within 10 min before or 2 min after, while the bathroom's smoothed score stays above exit_score from through-wall kitchen activity. Why it is here: bleed-only control (bathroom empty, kitchen occupied; checked visually). Caveats: labels are a reading of the radar plots, not a user narrative; visits were found from move >= 90 bursts, so an entry without one can be missing from the labels; the InvisOutlet kitchen often turns on from the bathroom occupant alone.

## bathroom-visit-2026-10-10-0723.db

2026-10-10 07:20:10–07:33:45, bathroom (D0:6E) and kitchen (B3:26), with `labels`, `states` (live bathroom/kitchen smart_ld2410, InvisOutlet kitchen occupancy, bathroom light) and `events` tables. Ground truth (hand-labelled by Claude from the radar plots in experiment 67; not user-confirmed; person unknown): in the bathroom 07:23:10–07:28:45 (medium; seated 5 min with a dim stretch 07:25:40-07:26:20 (live cleared) and renewed still at 07:26:22 without an entry burst; fades ~07:28:45; left into a quiet kitchen). Why it is here: ordinary visit. Caveats: labels are a reading of the radar plots, not a user narrative; visits were found from move >= 90 bursts, so an entry without one can be missing from the labels; medium-confidence departures are signal fades without an exit burst, ±10–20 s; the InvisOutlet kitchen often turns on from the bathroom occupant alone.

## bathroom-visit-2026-10-10-0846.db

2026-10-10 08:43:43–09:00:50, bathroom (D0:6E) and kitchen (B3:26), with `labels`, `states` (live bathroom/kitchen smart_ld2410, InvisOutlet kitchen occupancy, bathroom light) and `events` tables. Ground truth (hand-labelled by Claude from the radar plots in experiment 67; not user-confirmed; person unknown): in the bathroom 08:46:43–08:55:50 (high; arrives from the kitchen, quiet middle (live cleared 08:50:35), exit burst ends 08:55:47, kitchen saturates 08:56:00; left into an occupied kitchen). Why it is here: exit into an active kitchen. Caveats: labels are a reading of the radar plots, not a user narrative; visits were found from move >= 90 bursts, so an entry without one can be missing from the labels; the InvisOutlet kitchen often turns on from the bathroom occupant alone.

## bathroom-visit-2026-10-10-1015.db

2026-10-10 10:12:30–10:28:03, bathroom (D0:6E) and kitchen (B3:26), with `labels`, `states` (live bathroom/kitchen smart_ld2410, InvisOutlet kitchen occupancy, bathroom light) and `events` tables. Ground truth (hand-labelled by Claude from the radar plots in experiment 67; not user-confirmed; person unknown): in the bathroom 10:15:30–10:23:03 (high; long visit with quiet stretches, exit burst ends 10:23:03; InvisOutlet on and kitchen blip 10:23:58; left into an occupied kitchen). Why it is here: exit into an active kitchen. Caveats: labels are a reading of the radar plots, not a user narrative; visits were found from move >= 90 bursts, so an entry without one can be missing from the labels; the InvisOutlet kitchen often turns on from the bathroom occupant alone.

## bathroom-visit-2026-10-10-1208.db

2026-10-10 12:05:55–12:14:35, bathroom (D0:6E) and kitchen (B3:26), with `labels`, `states` (live bathroom/kitchen smart_ld2410, InvisOutlet kitchen occupancy, bathroom light) and `events` tables. Ground truth (hand-labelled by Claude from the radar plots in experiment 67; not user-confirmed; person unknown): in the bathroom 12:08:55–12:09:35 (medium; kitchen sensor goes dark exactly while the bathroom saturates: person stepped in for ~40 s and back to the kitchen; left into an occupied kitchen). Why it is here: exit into an active kitchen. Caveats: labels are a reading of the radar plots, not a user narrative; visits were found from move >= 90 bursts, so an entry without one can be missing from the labels; medium-confidence departures are signal fades without an exit burst, ±10–20 s; the InvisOutlet kitchen often turns on from the bathroom occupant alone.

## bathroom-bleed-2026-10-10-1301.db

2026-10-10 12:59:06–13:08:18, bathroom (D0:6E) and kitchen (B3:26), with `labels`, `states` (live bathroom/kitchen smart_ld2410, InvisOutlet kitchen occupancy, bathroom light) and `events` tables. Ground truth (exp 67 rule, not user-confirmed): bathroom empty, kitchen occupied — no bathroom burst within 10 min before or 2 min after, while the bathroom's smoothed score stays above exit_score from through-wall kitchen activity. Why it is here: bleed-only control (bathroom empty, kitchen occupied; checked visually). Caveats: labels are a reading of the radar plots, not a user narrative; visits were found from move >= 90 bursts, so an entry without one can be missing from the labels; the InvisOutlet kitchen often turns on from the bathroom occupant alone.

## bathroom-bleed-2026-10-10-1320.db

2026-10-10 13:18:41–13:26:20, bathroom (D0:6E) and kitchen (B3:26), with `labels`, `states` (live bathroom/kitchen smart_ld2410, InvisOutlet kitchen occupancy, bathroom light) and `events` tables. Ground truth (exp 67 rule, not user-confirmed): bathroom empty, kitchen occupied — no bathroom burst within 10 min before or 2 min after, while the bathroom's smoothed score stays above exit_score from through-wall kitchen activity. Why it is here: bleed-only control (bathroom empty, kitchen occupied; checked visually). Caveats: labels are a reading of the radar plots, not a user narrative; visits were found from move >= 90 bursts, so an entry without one can be missing from the labels; the InvisOutlet kitchen often turns on from the bathroom occupant alone.

## bathroom-visit-2026-10-10-1558.db

2026-10-10 15:55:26–16:04:20, bathroom (D0:6E) and kitchen (B3:26), with `labels`, `states` (live bathroom/kitchen smart_ld2410, InvisOutlet kitchen occupancy, bathroom light) and `events` tables. Ground truth (hand-labelled by Claude from the radar plots in experiment 67; not user-confirmed; person unknown): in the bathroom 15:58:26–15:59:20 (high; exit burst ends 15:59:23, kitchen saturates 15:59:20 onward; left into an occupied kitchen). Why it is here: exit into an active kitchen. Caveats: labels are a reading of the radar plots, not a user narrative; visits were found from move >= 90 bursts, so an entry without one can be missing from the labels; the InvisOutlet kitchen often turns on from the bathroom occupant alone.

## bathroom-visit-2026-10-10-2203.db

2026-10-10 22:00:20–22:09:26, bathroom (D0:6E) and kitchen (B3:26), with `labels`, `states` (live bathroom/kitchen smart_ld2410, InvisOutlet kitchen occupancy, bathroom light) and `events` tables. Ground truth (hand-labelled by Claude from the radar plots in experiment 67; not user-confirmed; person unknown): in the bathroom 22:03:20–22:04:26 (high; visit while someone is in the kitchen the whole time, exit burst ends 22:04:28; later blips are bleed; left into an occupied kitchen). Why it is here: exit into an active kitchen. Caveats: labels are a reading of the radar plots, not a user narrative; visits were found from move >= 90 bursts, so an entry without one can be missing from the labels; the InvisOutlet kitchen often turns on from the bathroom occupant alone.

## bathroom-bleed-2026-10-10-2232.db

2026-10-10 22:30:56–22:40:46, bathroom (D0:6E) and kitchen (B3:26), with `labels`, `states` (live bathroom/kitchen smart_ld2410, InvisOutlet kitchen occupancy, bathroom light) and `events` tables. Ground truth (exp 67 rule, not user-confirmed): bathroom empty, kitchen occupied — no bathroom burst within 10 min before or 2 min after, while the bathroom's smoothed score stays above exit_score from through-wall kitchen activity. Why it is here: bleed-only control (bathroom empty, kitchen occupied; checked visually). Caveats: labels are a reading of the radar plots, not a user narrative; visits were found from move >= 90 bursts, so an entry without one can be missing from the labels; the InvisOutlet kitchen often turns on from the bathroom occupant alone.

## bathroom-visit-2026-10-10-2320.db

2026-10-10 23:17:51–23:26:59, bathroom (D0:6E) and kitchen (B3:26), with `labels`, `states` (live bathroom/kitchen smart_ld2410, InvisOutlet kitchen occupancy, bathroom light) and `events` tables. Ground truth (hand-labelled by Claude from the radar plots in experiment 67; not user-confirmed; person unknown): in the bathroom 23:20:51–23:21:59 (high; exit burst ends 23:21:59, kitchen saturates 23:22:03; left into an occupied kitchen). Why it is here: exit into an active kitchen. Caveats: labels are a reading of the radar plots, not a user narrative; visits were found from move >= 90 bursts, so an entry without one can be missing from the labels; the InvisOutlet kitchen often turns on from the bathroom occupant alone.

## bathroom-visit-2026-10-11-0832.db

2026-10-11 08:29:44–08:57:05, bathroom (D0:6E) and kitchen (B3:26), with `labels`, `states` (live bathroom/kitchen smart_ld2410, InvisOutlet kitchen occupancy, bathroom light) and `events` tables. Ground truth (hand-labelled by Claude from the radar plots in experiment 67; not user-confirmed; person unknown): in the bathroom 08:32:44–08:52:05 (high; 19 min visit with many quiet stretches (live cleared repeatedly), exit burst ends 08:52:05, kitchen saturates 08:52:20; left into an occupied kitchen). Why it is here: exit into an active kitchen, one of the longest quiet holds. Caveats: labels are a reading of the radar plots, not a user narrative; visits were found from move >= 90 bursts, so an entry without one can be missing from the labels; the InvisOutlet kitchen often turns on from the bathroom occupant alone.

## bathroom-visit-2026-10-11-1027.db

2026-10-11 10:24:06–10:33:07, bathroom (D0:6E) and kitchen (B3:26), with `labels`, `states` (live bathroom/kitchen smart_ld2410, InvisOutlet kitchen occupancy, bathroom light) and `events` tables. Ground truth (hand-labelled by Claude from the radar plots in experiment 67; not user-confirmed; person unknown): in the bathroom 10:27:06–10:28:07 (high; exit burst ends 10:28:07, kitchen blip 10:28:20; left into an occupied kitchen). Why it is here: exit into an active kitchen. Caveats: labels are a reading of the radar plots, not a user narrative; visits were found from move >= 90 bursts, so an entry without one can be missing from the labels; the InvisOutlet kitchen often turns on from the bathroom occupant alone.

## bathroom-visit-2026-10-11-1106.db

2026-10-11 11:04:20–11:25:14, bathroom (D0:6E) and kitchen (B3:26), with `labels`, `states` (live bathroom/kitchen smart_ld2410, InvisOutlet kitchen occupancy, bathroom light) and `events` tables. Ground truth (hand-labelled by Claude from the radar plots in experiment 67; not user-confirmed; person unknown): in the bathroom 11:06:32–11:06:47 (high, pass-through; 15 s in, out to the kitchen, back at 11:07:20; left into an occupied kitchen); in the bathroom 11:07:20–11:20:14 (high; 13 min busy visit, exit burst ends 11:20:14, kitchen saturates 11:20:30; left into an occupied kitchen). Why it is here: exit into an active kitchen. Caveats: labels are a reading of the radar plots, not a user narrative; visits were found from move >= 90 bursts, so an entry without one can be missing from the labels; the InvisOutlet kitchen often turns on from the bathroom occupant alone.

## bathroom-visit-2026-10-11-1324.db

2026-10-11 13:21:00–13:35:05, bathroom (D0:6E) and kitchen (B3:26), with `labels`, `states` (live bathroom/kitchen smart_ld2410, InvisOutlet kitchen occupancy, bathroom light) and `events` tables. Ground truth (hand-labelled by Claude from the radar plots in experiment 67; not user-confirmed; person unknown): in the bathroom 13:24:00–13:30:05 (medium; arrives from the kitchen, quiet/dim 13:27:50-13:29:45 then renewed motion without entry burst, leaves ~13:30:05 as the kitchen lights; later blips are bleed; left into an occupied kitchen). Why it is here: exit into an active kitchen. Caveats: labels are a reading of the radar plots, not a user narrative; visits were found from move >= 90 bursts, so an entry without one can be missing from the labels; medium-confidence departures are signal fades without an exit burst, ±10–20 s; the InvisOutlet kitchen often turns on from the bathroom occupant alone.

## bathroom-visit-2026-10-11-1809.db

2026-10-11 18:06:23–18:15:47, bathroom (D0:6E) and kitchen (B3:26), with `labels`, `states` (live bathroom/kitchen smart_ld2410, InvisOutlet kitchen occupancy, bathroom light) and `events` tables. Ground truth (hand-labelled by Claude from the radar plots in experiment 67; not user-confirmed; person unknown): in the bathroom 18:09:23–18:10:47 (high; exit burst ends 18:10:47 into a busy kitchen; later blips and live re-triggers are bleed; left into an occupied kitchen). Why it is here: exit into an active kitchen. Caveats: labels are a reading of the radar plots, not a user narrative; visits were found from move >= 90 bursts, so an entry without one can be missing from the labels; the InvisOutlet kitchen often turns on from the bathroom occupant alone.

## bathroom-visit-2026-10-11-1952.db

2026-10-11 19:49:57–19:58:45, bathroom (D0:6E) and kitchen (B3:26), with `labels`, `states` (live bathroom/kitchen smart_ld2410, InvisOutlet kitchen occupancy, bathroom light) and `events` tables. Ground truth (hand-labelled by Claude from the radar plots in experiment 67; not user-confirmed; person unknown): in the bathroom 19:52:57–19:53:45 (high; exit burst ends 19:53:45, kitchen saturates 19:53:50; left into an occupied kitchen). Why it is here: exit into an active kitchen. Caveats: labels are a reading of the radar plots, not a user narrative; visits were found from move >= 90 bursts, so an entry without one can be missing from the labels; the InvisOutlet kitchen often turns on from the bathroom occupant alone.

## bathroom-visit-2026-10-11-2154.db

2026-10-11 21:51:28–22:52:05, bathroom (D0:6E) and kitchen (B3:26), with `labels`, `states` (live bathroom/kitchen smart_ld2410, InvisOutlet kitchen occupancy, bathroom light) and `events` tables. Ground truth (hand-labelled by Claude from the radar plots in experiment 67; not user-confirmed; person unknown): in the bathroom 21:54:28–22:11:00 (high; 16 min visit (live cleared 3x), exit burst ends 22:11:00, kitchen saturates 22:11:05; left into an occupied kitchen); in the bathroom 22:13:10–22:13:14 (high, pass-through; 5 s pass, kitchen saturates 22:13:20; left into an occupied kitchen); in the bathroom 22:14:40–22:14:43 (high, pass-through; 4 s pass; InvisOutlet just turned off, kitchen sensor dim; left kitchen unclear); in the bathroom 22:17:48–22:47:05 (medium; 29 min very still sit (live cleared 4x, and from 22:43:50), gate-3 motion to 22:46:40, gate-2 still to 22:47:20; kitchen saturates 22:47:03; left into an occupied kitchen). Why it is here: exit into an active kitchen. Caveats: labels are a reading of the radar plots, not a user narrative; visits were found from move >= 90 bursts, so an entry without one can be missing from the labels; medium-confidence departures are signal fades without an exit burst, ±10–20 s; the InvisOutlet kitchen often turns on from the bathroom occupant alone.

## bathroom-visit-2026-10-12-0606.db

2026-10-12 06:03:30–06:27:46, bathroom (D0:6E) and kitchen (B3:26), with `labels`, `states` (live bathroom/kitchen smart_ld2410, InvisOutlet kitchen occupancy, bathroom light) and `events` tables. Ground truth (hand-labelled by Claude from the radar plots in experiment 67; not user-confirmed; person unknown): in the bathroom 06:06:30–06:22:46 (high; one 16 min visit (algorithm split it), exit burst ends 06:22:45, kitchen saturates 06:22:55; left into an occupied kitchen). Why it is here: exit into an active kitchen, one of the longest quiet holds. Caveats: labels are a reading of the radar plots, not a user narrative; visits were found from move >= 90 bursts, so an entry without one can be missing from the labels; the InvisOutlet kitchen often turns on from the bathroom occupant alone.

## bathroom-visit-2026-10-12-0925.db

2026-10-12 09:22:29–09:32:15, bathroom (D0:6E) and kitchen (B3:26), with `labels`, `states` (live bathroom/kitchen smart_ld2410, InvisOutlet kitchen occupancy, bathroom light) and `events` tables. Ground truth (hand-labelled by Claude from the radar plots in experiment 67; not user-confirmed; person unknown): in the bathroom 09:25:29–09:27:15 (medium; seated, fades ~09:27:15; kitchen blips 09:27:35 and 09:28:10; left into an occupied kitchen). Why it is here: exit into an active kitchen. Caveats: labels are a reading of the radar plots, not a user narrative; visits were found from move >= 90 bursts, so an entry without one can be missing from the labels; medium-confidence departures are signal fades without an exit burst, ±10–20 s; the InvisOutlet kitchen often turns on from the bathroom occupant alone.

## bathroom-visit-2026-10-12-1048.db

2026-10-12 10:45:50–10:54:52, bathroom (D0:6E) and kitchen (B3:26), with `labels`, `states` (live bathroom/kitchen smart_ld2410, InvisOutlet kitchen occupancy, bathroom light) and `events` tables. Ground truth (hand-labelled by Claude from the radar plots in experiment 67; not user-confirmed; person unknown): in the bathroom 10:48:50–10:49:52 (high; visit while the kitchen is occupied throughout, motion ends 10:49:53; left into an occupied kitchen). Why it is here: exit into an active kitchen. Caveats: labels are a reading of the radar plots, not a user narrative; visits were found from move >= 90 bursts, so an entry without one can be missing from the labels; the InvisOutlet kitchen often turns on from the bathroom occupant alone.

## bathroom-visit-2026-10-12-1430.db

2026-10-12 14:27:51–14:38:30, bathroom (D0:6E) and kitchen (B3:26), with `labels`, `states` (live bathroom/kitchen smart_ld2410, InvisOutlet kitchen occupancy, bathroom light) and `events` tables. Ground truth (hand-labelled by Claude from the radar plots in experiment 67; not user-confirmed; person unknown): in the bathroom 14:30:51–14:33:30 (medium; seated, fades ~14:33:30; kitchen off; left into a quiet kitchen). Why it is here: ordinary visit. Caveats: labels are a reading of the radar plots, not a user narrative; visits were found from move >= 90 bursts, so an entry without one can be missing from the labels; medium-confidence departures are signal fades without an exit burst, ±10–20 s; the InvisOutlet kitchen often turns on from the bathroom occupant alone.

## bathroom-visit-2026-10-12-1548.db

2026-10-12 15:45:53–15:54:46, bathroom (D0:6E) and kitchen (B3:26), with `labels`, `states` (live bathroom/kitchen smart_ld2410, InvisOutlet kitchen occupancy, bathroom light) and `events` tables. Ground truth (hand-labelled by Claude from the radar plots in experiment 67; not user-confirmed; person unknown): in the bathroom 15:48:53–15:49:46 (high; exit burst ends 15:49:46, kitchen saturates 15:49:50; left into an occupied kitchen). Why it is here: exit into an active kitchen. Caveats: labels are a reading of the radar plots, not a user narrative; visits were found from move >= 90 bursts, so an entry without one can be missing from the labels; the InvisOutlet kitchen often turns on from the bathroom occupant alone.

## bathroom-visit-2026-10-12-1656.db

2026-10-12 16:53:46–17:02:42, bathroom (D0:6E) and kitchen (B3:26), with `labels`, `states` (live bathroom/kitchen smart_ld2410, InvisOutlet kitchen occupancy, bathroom light) and `events` tables. Ground truth (hand-labelled by Claude from the radar plots in experiment 67; not user-confirmed; person unknown): in the bathroom 16:56:46–16:57:42 (high; exit burst ends 16:57:42, kitchen saturates 16:57:48; left into an occupied kitchen). Why it is here: exit into an active kitchen. Caveats: labels are a reading of the radar plots, not a user narrative; visits were found from move >= 90 bursts, so an entry without one can be missing from the labels; the InvisOutlet kitchen often turns on from the bathroom occupant alone.
