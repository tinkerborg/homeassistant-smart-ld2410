# Living-room continuous occupancy audit (2026-09-16)

Ground truth: user seated in living room throughout 07:49–08:16, per fixture
README and label. `states` records occupancy and confidence; `events` records
transitions. The deployed `motion_anchor` refreshes hold exclusively when its
stored template is supported; ordinary run score does not refresh hold when the
stage is enabled (`algo/pipeline.py`).

Recorded occupancy: 07:50:41–07:51:29, 07:51:29–07:52:18,
08:10:03–08:10:31, 08:10:36–08:10:55, 08:14:34–08:14:51.
The person remained seated through every vacant interval. At 07:51:29 the
vacant event still had score59.11 and active gates3–8. At08:10:31 the vacant
event still had score16.0 and active gates3–6. Thus ordinary score and gate
activity did not disappear; the anchor path had stopped refreshing occupancy
long enough for its configured hold countdown to expire. Exact anchor score,
template and countdown were not exported, so their frame-specific values cannot
be reconstructed as deployed.

Still gate2 was exactly100 in **100% of 16,117 frames**. A histogram baseline
could absorb such a constant as background; its deployed state was not exported.
As activity changed, later still energies were substantially lower on other
gates (at07:52:05–25, median gate3/4=29/32) and motion stayed below40 throughout
that interval. At08:00–01, peak motion never exceeded18; gate2 remained100.
The tracker stores the largest motion-associated template and compares later
still residual against that fixed pattern. A seated occupant can therefore
stop matching the original template while still producing a strong raw signal.
This is a plausible mechanism, not an exact replay of the persisted baseline.

The living-room failure is a **retention failure**, distinct from the bathroom
kitchen false-entry problem. Reinstating ordinary score as an unconditional
hold refresher would reopen the latter: kitchen through-wall activity often has
high score. Any revised retention rule needs both fixture classes evaluated
before deployment.

No production code or fixture changes.
