# Experiment 27 — post-deploy bathroom audit

## Scope and method

This is a read-only audit of `tests/fixtures/recordings/post-deploy-0915.db`.
The bathroom sensor is `D0:6E:81:D2:5D:A6` (6,150 frames, 02:29:43.5–02:40:19.7
UTC on 2026-09-16, corresponding to Sep 15 evening in EDT).  The supplied
`labels` table is empty.  Kitchen (`B3:26:9E:EE:C5:11`) and living room
(`FD:68:3B:41:6E:FF`) streams are retained only as context; they are not used as
occupancy ground truth.

Run the exact bounded audit with:

```sh
python docs/research/experiments/27-postdeploy-audit/audit.py \
  tests/fixtures/recordings/post-deploy-0915.db
```

It opens SQLite with `mode=ro&immutable=1` and prints every bathroom raw frame
in the five seconds before each occupied event.  Arrays are the raw byte values
for gates 2..8, in gate order; `peak_move_ge40_gates` applies the requested
`move >= 40` test to the same frame.

## Observed bathroom event trace

| local EDT time (Sep 15) | UTC epoch | event payload | raw move gates 2..8 on event frame | anchor evidence in preceding 5 s |
|---|---:|---|---|---|
| 22:29:43.363 | 1789525783.363 | `score=0`, `active_gates=[]` | `[8,5,3,5,4,4,3]` | none; 5 s max = 8 |
| 22:36:21.713 | 1789526181.713 | `score=27.7778`, `active_gates=[2,3,4]` | `[39,44,9,9,9,5,3]` | event frame gate 3 = 44; prior 5 s max = 11 |
| 22:36:49.164 | 1789526209.164 | `score=38.8889`, `active_gates=[3,4,5,6]` | `[6,29,45,14,4,3,2]` | event frame gate 4 = 45; prior 5 s max = 34 |
| 22:39:37.457 | 1789526377.457 | `score=39.3333`, `active_gates=[2,3]` | `[100,86,7,7,6,2,2]` | event frame gates 2,3 = 100,86; prior 5 s max = 21 |

Thus, under the narrow candidate definition `max(move[2:9]) >= 40`, 3 of 4
occupied events have evidence, but in each of those three cases the first
qualifying sample is the event sample itself.  There is no qualifying motion
sample in the preceding five seconds.  The initial occupied event is a
cold-start/passthrough-shaped event with no such evidence.  This supports
“possible anchor at the transition sample” for the latter three and provides
no anchor evidence for the first; it does not establish whether live anchor
state existed before the recording or what caused the decision.

The surrounding bathroom transition sequence is:

```text
22:29:43.363 occupied
22:34:10.224 vacant
22:36:21.713 occupied
22:36:35.286 nine `unknown` gate-class events (all gates: in_room -> unknown)
22:36:44.963 vacant
22:36:49.164 occupied
22:38:37.655 vacant
22:39:37.457 occupied
```

The event payloads contain confidence, score, and active gates for occupancy
transitions.  The `unknown` payload is different: it records a gate-class
change (`previous: "in_room"`, `current: "unknown"`).  Code defines
`CLASS_UNKNOWN` as the unclassified gate role; these events are gate taxonomy
diagnostics, not an occupancy label or person-location assertion.

## Limits

The recording has raw frames, occupancy events, event payloads, and an empty
labels table, but no exported learned baseline/config snapshot.  An
instrumented replay from a cold start would therefore not be an exact replay
of the deployed learned state and is intentionally not used to claim one.
Kitchen and living-room device events likewise do not prove bathroom
occupancy.  No production code or database content was changed.
