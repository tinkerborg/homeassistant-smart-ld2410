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
