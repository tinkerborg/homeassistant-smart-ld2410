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

## labeled-sessions-0909-d06e.db

2026-09-09 21:15–23:35, from the dev instance. Contains kind='label' events
(ground-truth select entity): toilet/stove/island/hall-walk-by/empty
sessions. Caveats recorded at the time: the stove interval starting
~23:08:24 is contaminated (BLE dropout, label on while user absent) — the
229 s frame gap 23:05:42–23:09:31 self-identifies; trim the last ~5 s of
island intervals; arrival motion begins up to ~27 s before a label flip.
