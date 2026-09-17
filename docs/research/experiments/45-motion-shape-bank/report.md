# 45. Post-motion shape references reviewed over hold windows

Question: Does credible motion during occupancy supply new still-gate shapes as people move, allowing a completed hold window to be compared with recent occupied shapes?

The deployed `MotionAnchor` replaces its template only when a later motion-assisted candidate is **stronger** than the current one; it does not automatically make a new template for every move. In the experiment replay, the two trusted bathroom recordings had 17 and 10 template updates, respectively, all during labeled bathroom occupancy. The replacement living-room interval had 30 updates during labeled occupancy.

Method: The balanced anchor qualifies entry only. After each credible template update, save the z-scored still-gate profile two seconds later. Every completed hold window compares each frame's gate profile with the most similar saved profile, then judges the median similarity. The profile is invariant to positive scaling and uniform offset; multiple references allow motion between positions. Labels are evaluation only.

| Variant | Replacement LR occupied | Longest LR false vacancy | Known LR empty | `labeled-walk` bathroom clears | `labeled-loop` bathroom clear | Post-deploy bathroom clear |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Current anchor, 30 s hold | 29% | 529 s | 0% on | 31 / 31 s | 37 s | 37 s |
| Most recent shape, 20 s hold, correlation 0.8 | 98.0% | 8.9 s | 0% on | 23 / 17 s | 23 s | 34 s |
| Recent 4 shapes, 20 s hold, correlation 0.8 | 99.7% | 1.9 s | 0% on | 23 / 17 s | 43 s | 34 s |

The recent-four variant also holds the mixed-day known occupied interval for 99.8% of frames and the isolated 12:00–12:20 living-room stretch for 91%, versus 26%/32% under the current anchor. It stays off during the mixed-day known empty interval and 14:00–16:00 quiet-looking stretch. This is the best result on the primary daytime fixtures so far.

**Important control failure:** Overnight, when both humans were reportedly upstairs, the current balanced stack had two bathroom episodes with a longest episode of 70 seconds. Recent-four shape hold had two episodes with a longest episode of **461 seconds**. The cat-only kitchen fixture did not trigger the bathroom under either rule; the old living-room overnight sensor and cat kitchen sensor did not worsen. Thus the recent-four rule is **not deployable** despite strong daytime results. A saved raw gate shape can resemble a persistent background pattern after a false entry. The first `labeled-walk` short gap also needs care with 30-second review: it may not clear before the next visit. The 20-second review does clear it.

No production algo code changed. [Main results](results.json), [no-human controls](controls.json), [script](analyze.py).
