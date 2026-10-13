# 41. Living-room shape across the mixed day

The replacement living-room sensor records 11:20–17:00 in `living-room-mixed-2026-09-16.db`. The database's sole label marks the entire window unlabeled. The user says the period before 13:00 was mostly just them in the living room, with occasional trips; this is useful context, not a frame-accurate label. The integration's `states` table records detector decisions, not truth.

Still-gate shape uses gates 2–8. Centroid is the gate-weighted center of energy (lower means nearer gates); kurtosis describes how concentrated the gate profile is. Neither metric is total energy. The 11:39–11:40 known empty and 11:41–11:58 known occupied intervals come from the earlier narrated fixture.

| Period (local) | Integration on | Median centroid | Median kurtosis |
| --- | ---: | ---: | ---: |
| 11:39–11:40 known empty | 10% | 5.19 | 2.54 |
| 11:41–11:58 known occupied | 30% | 4.15 | 1.89 |
| 12:00–13:00 mostly living room | 33% | 4.23 | 1.87 |
| 13:00–14:00 mixed use | 44% | 4.40 | 1.89 |
| 14:00–16:00 quiet-looking, unverified | 0% | 5.00 | 2.43 |

When the integration says **off** from 12:00–13:00, centroid still has median 4.25 and kurtosis 1.88, close to the known occupied interval and unlike the known empty interval (off medians 5.20 and 2.61). Thus the longer recording reinforces the hypothesis that gate shape retains evidence of living-room occupancy during false clears. It also shows a distinct quiet-looking regime from 14:00–16:00, but that interval has no verified location label.

This is a shape survey, not a tested occupancy algorithm. It does not establish behavior during every bathroom trip, your wife's visit, or a second person moving through the room. No production code changed. [Data](results.json) and [script](analyze.py).

## Isolated living-room flapping before 13:00

Following the user's suggestion, two intervals have repeated living-room state changes while **both kitchen and bathroom occupancy states remain off throughout**:

| Period | Living-room flips | Living-room on | Still centroid when on / off | Still kurtosis when on / off |
| --- | ---: | ---: | ---: | ---: |
| 12:00–12:20 | 14 | 45% | 4.18 / 4.17 | 1.82 / 1.86 |
| 12:30–12:50 | 12 | 34% | 4.19 / 4.40 | 1.92 / 1.85 |

The first interval is particularly persuasive: the sensor's gate shape barely changes between the detector's on and off decisions, and both shapes are close to the earlier known-occupied profile. These stretches support a false-clear diagnosis, though the user's “mostly in the living room” account still allows short absences. Other-room *occupancy states* are quiet; that is not a claim that every raw gate in those sensors is perfectly flat.
