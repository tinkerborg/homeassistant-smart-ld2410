# Experiment 3: amplitude-histogram floor estimator

Data: fixture `livingroom-reset-seated-fd68.db` (learning reset ~21:04 with
the user seated at gates 2-3; true-ambient reference window 21:21-21:39;
user seated again 21:39:40-21:55; 21:49 = the shipped false-release
minute). Script: hist_floor.py.

## Verdict

**The amplitude-histogram floor works, and it is not a marginal win.** The
seated signature at gates 2-3 is not unimodal-above-ambient: the occupied
still distribution is a sharp ambient peak with a long fidget tail. Gate 2
keeps 61% of its occupied mass at ≤ ambient+2, gate 3 keeps 38%, and quiet
frames come in long blocks (49 runs, longest 1436 and 1126 frames ≈ 143s
and 112s at 10 Hz), so the low mode is easy to find. Histogram/KDE mode
lands within 2 units of true ambient in **2-3 minutes of occupied-only
data**; the shipped p25-of-bucket-medians takes 11 min at gate 2 and
**never converges at gate 3** (+2.2 at 21:20).

Larger finding: the floor was only half the contamination. The shipped
**spread** is equally poisoned (1.0 empty → 4.75 / 7.00 occupied at gates
2/3) and that, not the floor, is what erased the detection margin. A
mode-local MAD spread (MAD of samples within ±6 of the mode) recovers 1.48
vs 1.0 true.

## 1-2. Growing occupied-only window from 21:04:30 (error vs true ambient)

Gate 2 (true 7.0) / Gate 3 (true 6.0):

| until | g2 hist | g2 kde | g2 mix2 | g2 shipped | g3 hist | g3 kde | g3 mix2 | g3 shipped |
|---|---|---|---|---|---|---|---|---|
|21:05| +93 | +93 | +37.9 | — | +94 | +94 | +42.1 | — |
|21:06| **+1.0** | **+1.0** | +5.0 | — | +94 | +94 | +14.0 | — |
|21:07| +1.0 | +1.0 | +6.3 | — | **+2.0** | +3.0 | +4.0 | — |
|21:09| +1.0 | +1.0 | +1.1 | +5.0 | +2.0 | +3.0 | +6.4 | +13.0 |
|21:12| +1.0 | +1.0 | +1.2 | +2.5 | +3.0 | +3.0 | +4.2 | +8.2 |
|21:15| +1.0 | +1.0 | +1.2 | **+1.5** | +3.0 | +3.0 | +4.6 | +7.0 |
|21:17| +1.0 | +1.0 | +1.0 | +1.0 | +3.0 | **+2.0** | +3.9 | +6.0 |
|21:20| +1.0 | +1.0 | +0.9 | +1.0 | +0.0 | +0.0 | +2.1 | +2.2 |

Minutes-to-within-2: hist-mode 2 / 3 (g2/g3) · lowhalf-mode 2 / 2 ·
kde-mode 2 / 13 · mix2-low 4 / never · **shipped 11 / never**.

Caveat: at 21:05 every mode estimator reads 100 (post-power-cycle
saturation). Needs ~60s of data or a saturation guard before trusting it.

## 3. Sanity on the empty window (21:21-21:39)

All estimators reproduce true ambient within 1 unit at every gate (g2 7.0,
g3 6.0, others 5-6). The cat at gates 4-6 (21:28-21:33) drags nothing:
run on that sub-window alone and hist/kde still return 6.0/5.0/6.0 against
a true 6.0. mix2-low is weakest everywhere (~0.5 low bias); the plain
histogram peak is the best behaved.

## 4. Downstream — z of seated still signature, 21:39-21:55

Floor learned only from occupied 21:04-21:20:

| gate | shipped floor+spread | hist floor + mode-MAD spread | true |
|---|---|---|---|
| 2 | 0.21 | 0.67 | 0.42 |
| 3 | 0.82 | **5.40** | — |
| 4 | 4.30 | **8.77** | — |
| 3 @ 21:49 (false release) | 0.11 | **2.02** | — |
| 4 @ 21:49 | 0.30 | **2.02** | — |

Margin returns ~6.5x at gate 3; the 21:49 fully-still minute goes from
z≈0.1-0.3 (released) to z≈2.0 at two gates. The histogram floor alone
(keeping the shipped spread) only moves gate 3 from 0.82 to 1.14 — the
recovery is mostly the mode-local spread. Both halves must be replaced
together.
