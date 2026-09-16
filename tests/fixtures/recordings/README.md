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

2026-09-15 19:20–19:32, bathroom (D0:6E), kitchen (B3:26), living room
(FD:68) in one file with a `labels(person, room, ts_start, ts_end, note)`
table. Ground truth from the user's narrative, timed by the raw traces:
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
