# Experiments

## 25. Histogram floor/spread with motion-anchored still tracking

**Status: done — bounded reassessment.** Exp21's causal motion anchor was
paired with the spec-25 amplitude histogram floor (bin width 2, mode-local
MAD ±6, MAD floor 1, 60 s trust guard).  The floor-only ablation isolates the
spread contribution.  Only the trusted `labeled-walk-0915.db` and
`labeled-loop-0915.db` fixtures were used for evaluation; labels are not
inputs.  See `experiments/25-histogram-motion-anchor/report.md` and its
`results.json` for per-visit detection, dropout, release-tail, and causality
checks.

Candidate techniques (mostly from [prior-art.md](prior-art.md)) to evaluate
against recorded data before any spec work. One entry per experiment; log
results under the entry as they happen. Status: idea / running / done.

## 1. Slow/fast filter difference (Acconeer inter-frame deviation)

Per-gate fast EMA vs slow EMA of still energy; statistic = |fast − slow|.
Targets: motionless-person retention (the faint sustained residual a tuned
device threshold rides). Risk: designed for raw sweep-rate data, may not
transfer to 10 Hz processed energies.
**Status: done — WORKS (still channel only).** 2026-09-11 living-room
recording: at tau=(2s, 60s) the statistic bridges the 21:49 very-still
dropout minute with ~25x margin over the empty reference (gate-3 median 5.17
vs 0.20); never touches the empty band across 21:40-21:55. Move channel: no
separation (1.37 vs 0.26) — still-channel-only. A toy detector on it (score
= stat/floor over gates 2-3, ON 20 / OFF 10) scored 0 false drops while
seated and 0 false occupancy during the empty window, where the shipped
detector had 1 false drop and a latched cat false. Cat rejection came purely
from the gate restriction — cat activity at gates 4-7 scores 20-80, human-
scale; magnitude does not separate species, location does.

Blind counter-test (bathroom D0:6E, 2026-09-11 05:00-06:00, ground truth:
bathroom empty, wife active in the kitchen through the shared wall): the
statistic held near-continuous false occupancy for 46 min (raw still bleed
excursions to 60-85 at gates 2-3), vs the shipped detector's two brief
falses. Conclusion: the filter is a retention/hold statistic ONLY — it
amplifies bleed exactly as well as presence and must sit behind arrival
entry gating, never drive entry. Also: the shipped detector's two entries
that hour were themselves arrival-gate leaks (energetic close-to-wall
kitchen activity cleared the bar at gates 2-4) — entry discrimination is
not finished either. Hardware fact from the same run: the LD2410 reports no
still energy at gates 0-1 (still detection starts at gate 2), so still-
channel near-gate rules begin at gate 2.

## 2. Frame-to-frame noise floor (Acconeer-style)

Per-gate floor from robust mean |first difference| of consecutive frames,
continuously updated (~10 s time constant). Targets: occupancy-immune floor
learning — would replace the windowed quietest-quarter machinery and the
learn-while-occupied constraint. Same transfer risk as #1.
**Status: done — FAILS as occupancy-immune.** A seated human inflates the
frame-to-frame floor 3-6x (gate 3: 0.34 occupied-learning vs 0.08 empty):
at 10 Hz on pre-smoothed energies, human micro-motion lives in the same band
the floor measures; Acconeer's original depends on sweep rates orders of
magnitude faster than a body. Only ~21% of consecutive frames differ at all,
so the floor is largely a quantization statistic. Still usable as a
normalizer (errs toward desensitizing, never false drops) with an EMA(10s)
and a 0.10 clamp; not a replacement for baseline learning.

## 3. Amplitude-histogram detection (Gennarelli 2022)

Decide occupied/vacant from the distribution shape of a gate's energy stream
rather than a quantile floor. Targets: floor contamination, mixture framing.
**Status: done — WORKS, strongly.** livingroom-reset-seated fixture: the
occupied still distribution at the seat gates is a sharp ambient peak plus
a fidget tail (61%/38% of occupied mass within ambient+2 at g2/g3; quiet
runs up to ~143s), so the histogram mode finds true ambient from
occupied-ONLY data in 2-3 minutes; the shipped p25-of-bucket-medians took
11 min at g2 and never converged at g3. Empty-window sanity clean (cat
drags nothing). Bigger finding: the SPREAD was the worse contamination
(1.0 empty → 4.75/7.0 occupied); a mode-local MAD recovers 1.48. Both
halves must be replaced together: floor-only moves g3 z from 0.82 to just
1.14, floor+mode-MAD reaches 5.40, and the 21:49 false-release minute goes
z 0.1→2.0. Caveats: mode estimators read saturated for the first ~60s
after a power cycle (needs a guard); plain histogram peak beat KDE and
2-component mixture.

## 4. Fade-in-place vs departure release

Release occupancy only when a gate cluster's evidence ends in departure
motion; evidence that fades to ambient without motion means chip absorption,
not departure — hold indefinitely. Multi-person caveat: a departure proves
someone left, not that the room emptied; needs per-gate clusters and
eventually Phase 3 cross-sensor attribution.
**Status: idea.**

## 4a. Leading edge over suppressed residuals

Scan the leading gate over the same neighbor-support-suppressed move
residuals the score trusts, instead of raw residuals; entry requires
leading gate ≤ 1.
**Status: done — WORKS.** 2026-09-11 05:00-06:00 bathroom through-wall hour
(ground truth empty): suppressed leading gate ≤1 in 1 of 36,001 frames;
both shipped false entries lead at gate 2 and would be refused. Both
labeled genuine toilet entries (2026-09-09) lead at gate 0 with sustained
suppressed near-gate residual (9-73 frames at g0/g1) — admitted. Gate-0
chatter: suppression kills 94% of its hot frames. Also found: the shipped
leading_gate diagnostic is sticky — one gate-0 frame anywhere in a
candidate pins the recorded value; the scan must be non-sticky (block
minimum), and classifier masking was not applied (suppression-only pass is
strictly weaker, so refusals hold with the mask on).

## 4b. Synthetic overlap (bathroom visit + kitchen bleed superimposed)

Frame-level mix (max and clipped-sum) of the confirmed 22:04 bathroom visit
over the 05:11 kitchen-bleed block, shared real 6h warm-up.
**Status: done.** Findings: (a) the kitchen-only control latched shipped
occupancy by itself for 541s — arrival at 0.55/min_frames=1 is a coin flip
against bleed (one frame at 58 cleared the 55 bar); (b) the suppressed
leading edge was the ONLY rule clean in both directions — gate-0/1 frame
counts in the mix identical to the pure-bathroom control, kitchen never
touches 0-1; (c) the retention statistic cannot distinguish "occupant
still here" from "neighbor still cooking" (reads HIGHER on the empty-
bathroom kitchen control than the genuine visit at the same minute) —
under adjacent activity it is not a vacancy discriminator; (d) the
wife-at-stove departure hole reproduces: release 104s late on the max mix,
never on the sum mix. Pointer: release should condition on the leading
edge retreating past the near gates, not on score/retention decay, both of
which a neighbor holds up indefinitely. Amplitudes in synthetic mixes are
fiction (energies not additive) — rule behavior only.

## 4c. Composite entry (arrival + suppressed leading edge) on the overlap

**Status: done — WORKS.** Same four streams as 4b, entry now also requiring
suppressed leading gate ≤ lead_gate_max. Kitchen-only control: never
enters (2968 score-hot frames, zero with lead ≤1 — through-wall always
leads g2+). Bathroom control: entry 22:04:01 and release identical to
shipped — zero latency cost (the lead condition goes true the same frame
arrival clears). MAX mix: 5-min false pre-latch eliminated, one correct
visit. SUM mix: unchanged, but shown to be an invalid worst case (additive
clipping fabricates g0/g1 energy present in neither source; energies don't
sum) — MAX is the meaningful mix. Sweep: lead_gate_max 0 and 1 identical
everywhere, 2 collapses to shipped (g2 is exactly where bleed leads);
default 1. Departure hole persists by design (+104s on MAX: the neighbor
pokes score over exit_score, longest continuous sub-exit run 122s vs
hold_s=30) — the hold path is the remaining problem; retention stays
unwired after 4b.

## 4d. Leading-edge-conditioned release

**Status: done — split result.** Near-lead release (countdown resets only
on suppressed-lead ≤1 frames, 60s grace): neutralizes the neighbor
completely — MAX overlap becomes bit-identical to the pure-bathroom
control, kitchen never enters, −104s. But it is a motion-recency latch:
drops the seated living-room user at 21:42 (near-leads stop recurring once
settled) — wrong for sofa/desk rooms. Retention refresh (near-lead OR
slow/fast ≥20): perfect in the neighbor-free room (no drops incl. 21:49,
releases 21:19 on the real exit) but blocks release forever under a
neighbor (neighbor retention reads HIGHER than a genuine still occupant —
4b's inversion at per-gate resolution). Far-lead veto fails to reconcile:
an in-room occupant also produces g2+ leads, so the veto kills retention
during genuine holds. Missing discriminator: through-wall scatterer vs
still occupant at the same gates post-entry. Next idea: entry-established
ownership (occupant provably reached g0/1; neighbor never can) decaying
slowly, retention refresh allowed only while ownership lives. Full report:
experiments/4d-leading-edge-release/.

## 4e. Ownership release (variant D′)

**Status: done — PASSES ALL FOUR targets** (overlap release on time, pure
controls unchanged, kitchen never enters, seated fixture zero drops incl.
21:49 with on-time seeded release). Two load-bearing mechanics: SIGNED
retention (positive part of fast−slow, peak-held ~90s — the unsigned form
is a change detector that a departure maximizes, which caused 4d's
inversion) and DEPARTURE ARMING (ownership starts disarmed so stillness
can never release; a post-entry re-crossing of the near band after a quiet
gap arms release on attributed evidence only; retention decay is the
no-crossing fallback). Robust across a wide parameter plateau. Spec 24
release semantics updated to match. Full report:
experiments/4e-ownership-release/.

## 4f. Differential release → retention reset (D″)

**Status: done — WORKS (reset variant).** The literal pre/post
differential fails structurally (pre-window measures the crosser's
motion, post measures the stayer's stillness, so a present-but-still
occupant reads as a collapse). The reset form passes all six targets
including the two D′ failures: a near-band crossing clamps the held
retention to zero for ~60s — a room still holding someone re-lifts it
within the window, an empty room can't. No armed state, no per-room
knobs; every prior D′ pass bit-identical; cat-exit and two-person
overlays both HELD. New global constant clamp_s≈60 (plateau ±12s).
Spec 24 release semantics need rewriting from arming to reset. Full
report: experiments/4f-differential-release/.

## 5. Regime-change detection (clutter-edge literature)

Detect when a gate's statistics switch population. Targets: ceiling
re-anchoring, relocation detection, "sensor moved" without decay heuristics.
**Status: idea.**

## 6. Motion-gated ceiling window

Keep the ceiling's rolling window but advance it only through buckets that
contain meaningful motion (raw-data predicate, not detector verdict). Empty
time contributes nothing to a ceiling, so vacations stop aging it out.
**Status: done — WORKS.** Real history never shows the failure (occupancy
never leaves a 12h gap; ceiling pinned at 100 post-warmup), but a
simulated vacation collapses the current ceiling to bleed level in ~24h
(bar ~26, bleed re-admitted for the rest). Motion-gating with admission
floor 60 is stable through a 30-day bleed-heavy vacation AND relearns an
adversarial capped-at-60 regime change by day 4; floor 50 leaks, floor 65
never relearns. Cold start unaffected. Full report:
experiments/6-motion-gated-ceiling/.

## 7. Learned arrival threshold from peak clustering

Replace fixed arrival_frac with per-sensor clustering of arrival peaks
(strong ~100 vs weak ≤~50 populations), clustered on peaks not dwell length
so brief visits don't pollute. Bootstrapping via passthrough phase is the
risk.
**Status: idea.**

## 8. Heavy-tailed per-gate noise models

Indoor clutter is Weibull/log-normal, not Gaussian; z-scores understate the
noise tail. Recalibrate exceedance scoring accordingly.
**Status: idea.**

## 9. Unsupervised two-state HMM

Occupied/vacant latent over gate energies, fit without labels — candidate
long-term replacement for hand-built hysteresis.
**Status: done — NOT VIABLE**, as replacement or confidence layer. The
unsupervised latent is energy-present, not occupied (a neighbor maximizes
it — 4b's wall); no configuration is good at both seated-hold and bleed
rejection; posterior AUC 0.650 pooled, below its own retention input
(0.768), P(occ|post>0.9)=0.30. A two-state fit also cannot express an
all-empty span (forced to label 15-55% of an empty hour occupied).
Bonus: same grader scored 4e D′ balanced-accuracy 0.835 with TNR 1.000 vs
shipped 0.701. Full report: experiments/9-unsupervised-hmm/.

## 11. Separation learning (leading-edge enablement)

Learn label-free per sensor whether leading-gate separation exists, via
confirmed-vs-fizzled leading-gate histograms (spec 24 §1 enablement).
**Status: done — NOT LEARNABLE with this proxy.** "Confirmed dwell ≥60s"
is dominated by through-wall activity (cooking sustains 60s too; 65% of
the bathroom's confirmed class leads g2), so true entries are a minority
inside their own label, split exactly along the learned axis. All sensors
return disable; excising known bleed hours doesn't help (diurnal, not
episodic). Spec 24 §1 enablement + acceptance §8 invalidated as designed
— enablement stays a global option until a proxy the through-wall class
can't satisfy is validated (departure-signature proxy or gap-separated
mixture mode + support term, both untested). Full report:
experiments/11-separation-learning/.

## 12. Per-room exit policy

Arming vs retention-only chosen per room by learned bleed pressure.
**Status: done — resolves nothing, ship uniform arming.** Matched policy
equals uniform D′ on every fixture (in the living room arming can never
fire — zero near-band frames ever — so the two policies are identical
there); the true multi-occupant hazard (far-gate stayer in a
near-band-capable room, dropped +24s after a leaver) is not predicted by
pressure — the policy picks arming exactly where the hazard lives.
Realistic two-person bathroom is safe (the still occupant keeps
re-lighting the near band). Misclassification cost is asymmetric
(retention-in-bathroom +202s latch; arming-in-living-room free).
By-product worth keeping: the episode-level bleed-pressure statistic
(orphan-episode ratio) separates rooms 4-7x label-free — good diagnostic.
Far-gate multi-occupant case deferred to Phase 3. Full report:
experiments/12-per-room-exit-policy/.

## 13. Fade-character discrimination

Rician-vs-Rayleigh fade statistics per event (through-wall adds deep
fades per the physics literature).
**Status: done — FALSIFIED on this hardware.** The chip's 10 Hz smoothing
leaves no fading envelope (move channel decorrelated, still channel a
slow filtered level) — same failure family as the frame-to-frame floor.
Residual separation is proximity wearing fade clothing, sign-unstable
across sensors; through-wall indistinguishable from empty on fade
features; per-gate accumulation recovers no room structure. Full report:
experiments/13-fade-character/.

## 14. Trajectory boundary learning

**Status: done — WORKS where rooms are deep, degenerate where they
aren't.** Arrival-conditioned travel-origin histograms recover the
living room's door (gate 5-6) and seat (2-3) label-free on two
databases, and admit all the genuine walk-ins the fixed lead≤1 rule
rejected live — the config-free replacement for `lead_gate_max` on any
sensor accumulating ≥20 arrivals (3-7 days). The bathroom is provably
degenerate for position (2 gates deep; through-wall occupies the same
band and travels more) — it keeps the near-band rule + shielding.
Marginal histograms carry nothing (exit≈enter); arrival conditioning is
the whole signal. Argmax tracking unusable; residual-weighted centroid
required. IP-adjacent to the intent-mapping patents. Full report:
experiments/14-trajectory-boundaries/.

## 15. Gate-profile shape

Read the spatial profile across all 9 gates per frame (or over ≤5 s)
instead of gates individually: near-mass fraction, centroid, spread,
peak falloff, gate count above floor, template cosine — on the theory
that an occupant and a through-wall neighbour look different in shape
even when they look the same in level.
**Status: done — BEST INSTANTANEOUS DISCRIMINATOR YET, still not a
hold.** Profile depth cuts the longest false "occupied-looking" run in
the bathroom's far cases 4-9x versus a level rule (far kitchen 338s ->
38s, through-wall morning 255s -> 30s, post-departure decay 113s -> 5s)
at TPR 0.84 / FPR_TW 0.09 / FPR_EMPTY 0.01, and needs no learned floor
(raw deep-gate thresholds match floor-subtracted ones). It fails on the
near-wall case that matters: the labeled stove+island session is 172s of
continuous 100%-IN-looking profile on every statistic tried, so a hold
must survive 52.6s of genuine-visit silence and release inside a 172s
false refresh — negative margin, same overlap as the single-gate rule,
narrowed on the far cases and unfixed on the near one. Shape adds
nothing over amplitude: every normalised ratio is matched or beaten by
one raw deep gate (still[5]), the IN and TW mean templates are 0.99
parallel, and near-mass fraction is inverted from the intuition
(in-room saturates gates 2-4 and spills; far through-wall is the narrow
profile). Move channel carries nothing (J <= 0.58). Living room: the
21:49 very-still minute does keep an in-room-shaped profile (+3 counts
across gates 3-5, 100% of the minute flagged) so no bridging is needed
there — but it sits at the 88th percentile of that sensor's empty tail
and rides on a one-count floor from a single empty session. Cat is a
clean far-only profile (gates 4-6, near gates at floor): depth-only
rules hold on it for 2.5 min, near-gate terms reject it outright.
Deliverable: profile depth is a good arming/suppression input, not a
hold; the near-wall case needs shielding or cross-room ownership. Full
report: experiments/15-gate-profile/.

## 16. Motion–still temporal coupling

Question: after matching a motion burst by peak gate and motion strength, does
the still-energy response over the following seconds distinguish in-room from
through-wall activity? This is a temporal relationship test, not an entry or
exit transition rule. Bathroom sensor only; the living-room fixtures have no
through-wall labels.
**Status: done — NO RELIABLE GAIN FROM TESTED PEAK-RESPONSE FEATURES.** After
excluding dead still gates 0–1, whole-fixture holdout AUC was 0.624 baseline,
0.640 with sampled temporal changes, and 0.649 with the closely related
future-level variant on `labeled-sessions`; on `stove-case` it was 0.878,
0.852, and 0.843. Matched close-wall bursts had median IN-minus-TW still
change −0.8 at 0.5 s, 1.7 at 1 s, 5.5 at 2 s, and 5.7 at 3 s, with a broad
−12.6 to +18.2 middle-80% range at 2 s. Do not add a motion-followed-by-still
rule or use motion as a departure proxy. Full report:
experiments/16-motion-still-coupling/.

## 17. Continuous motion–still relationships

Question: do rolling move/still relationships distinguish bathroom in-room
activity from through-wall activity without selecting motion events or using
transition gating? **Status: done — INCONCLUSIVE, NO ROBUST GAIN SHOWN.** With
the stronger per-gate level/variability baseline, 10 s features were
effectively baseline (hard labeled-sessions .449/.465/.445; stove
.804/.806/.805). At 30 s, level correlations improved labeled-sessions
.550→.617 but decreased stove-case .742→.724; first-difference features gave
.565 and .732. The sparse non-overlapping 30 s sensitivity was only 15 hard
windows (.472/.528/.500), so it cannot resolve the effect. This is a bounded
result for the tested rolling aggregates, not a claim that all temporal models
fail. Full report: experiments/17-continuous-motion-still/.

Held-out validation on `labeled-walk-0915.db` (bathroom sensor only, frozen
old-fixture model): both 19 s and 23 s visits are covered by 10 s strict
windows while the baseline already scores AUC 1.000; adding rolling level or
first-difference correlations remains 1.000. There are no 30 s strict IN
windows. This validates the baseline on a new labeled recording but shows no
incremental correlation gain. Details:
experiments/17-continuous-motion-still/walk0915-report.md.

## 18. Per-frame bathroom separability

Held-out per-frame test on `labeled-loop-0915.db` and `labeled-walk-0915.db`
using only the bathroom sensor and models trained on older bathroom fixtures.
**Status: done — neither tested model meets sub-second entry plus reliable
through-wall rejection.** The full raw 9-move+7-still ridge and four-feature
amplitude ridge rank new IN/TW frames well, but frozen thresholds fail the
operational target: loop apparent entry takes 2.63/1.81 s (full/amplitude),
with 5.3%/7.1% kitchen false frames. On the simultaneous walk, full has
54.3% kitchen false frames and is already positive before both entries;
amplitude has 1.1% kitchen false frames but takes 1.69 s on the first entry.
Three-frame confirmation does not fix the tradeoff. Transition labels were
timed using radar, so these delays are not independent latency ground truth.
Older mixed-fixture holdouts remain weak, especially
`labeled-sessions` (full AUC .479, 37.5% IN missed; amplitude .580, 64.6%
missed), so the new files do not establish general reliability. Full report:
experiments/18-frame-separability/report.md.

## 19. Raw signal inspection / spatial ordering

**Status: descriptive — not a wall discriminator.** Plotted unsmoothed bathroom
move/still streams for the Sept 15 loop and overlap and Sept 9 close-wall
recording; no classifier trained. Gate 3 exceeds gate 2 throughout the older
evaluated stove/island spans, but also during 26.4% of the longer toilet visit
(longest run 33.28 s). The reverse ordering occurs in 54.5% of the new loop's
kitchen frames. The normalized spatial slope describes a visible difference,
but range bands are not room boundaries and this does not establish a physical
through-wall signature or automatic room learning. Plots and measurements:
experiments/19-raw-signal-inspection/report.md.

## 20. Per-gate motion/still balance

**Status: done — useful local evidence, not a wall discriminator.** A per-gate
motion/still share preserves more bathroom evidence than a whole-sensor ratio
in the Sept 15 simultaneous capture (42% vs 16% of IN frames at the fixed
illustrative setting). Motion alone also rejects its kitchen frames, however,
and older bathroom-empty kitchen bursts pass both conditions. Quiet bathroom
and kitchen balance distributions overlap. This tests positive evidence, not
release after departure. Report: experiments/20-channel-balance/report.md.

## 21. Motion-anchored still footprint through departure

**Status: done — follows the target visits, fails older controls.** Causal,
bathroom-only prototype uses motion to select a still-energy footprint, then
follows its remaining amplitude without requiring a departure motion event.
In the simultaneous Sept 15 capture it holds both visits after detection and
clears .97/.57 s after exit labels despite continued kitchen presence. First
entry is 1.69 s after its label; these are not independent latency measurements.
Older bathroom-empty kitchen activity falsely holds 14.14% of frames, while
quiet bathroom visits suffer long false drops. All 18 sensitivity settings
retain substantial older failures. Labels evaluate only; no supervised model.
Report and plot: experiments/21-component-retention/report.md.

### 21 reassessment — trusted Sept 15 fixtures

The original `tau=15 s`, motion 40, retention .4 replay was rerun unchanged
on only `labeled-walk-0915.db` and `labeled-loop-0915.db`, now treated as the
reliable validation set.  Historical older-label failures are retained as
uncertain-ground-truth context and do not disqualify this narrow result.  The
default outputs match the historical exp21 outputs exactly: 95.962%/99.487%
IN positive frames and 2.627%/7.742% TW positive frames for walk/loop.  No
trusted visit has a premature dropout after first detection; first detection
offsets are 1.693 s, .016 s, and .385 s, and first clear offsets after exit
labels are .970 s, .567 s, and 6.859 s.  The loop's labeled kitchen starts 2 s
after its exit label; the 20-frame unlabeled gap and 48-frame labeled release
tail are reported separately from the zero-positive after-clear kitchen span.
See
`experiments/21-component-retention/reassessment-0915/report.md` for the
descriptive raw motion/still controls and full qualification.

## 22. Footprint retention with hysteresis

**Status: done — no tested improvement, and entry hysteresis is vacuous for
this initialization.** Replayed all experiment 21 fixtures with baseline
`.4/.4`, illustrative hysteresis `.7/.3`, and matched controls `.3/.3` and
`.7/.4`, using bathroom-only causal replay (`tau=15 s`, motion 40). The
`.4/.4` run is exactly identical to experiment 21; `.7/.4` is also identical
because initialized footprint scores are at least 1. The `.7/.3` run matches
`.3/.3`, so the lower off threshold only lengthens exit tails while increasing
through-wall false fractions (Sept 15 walk 2.63%→4.38%; stove 9.07%→11.15%).
Older quiet bathroom visits still miss about half their frames. Labels remain
evaluation only and are not independent subsecond truth. Full report:
experiments/22-footprint-hysteresis/report.md.

## 23. Footprint shape similarity versus strength

**Status: done — hypothesis not supported.** A causal normalized cross-gate
shape score was compared with experiment 21's amplitude projection and a
strength-only control. The shape replay retained its template after failed
frames so low-amplitude evidence was genuinely evaluated; a fixed residual
energy guard blocked near-zero noise matches. A high cosine threshold reduced
Sept 15 walk through-wall positives to 7.36% (7.26% on the older mixed
through-wall span), but bathroom misses rose to 7.36% on the walk and 56.43%
on the older toilet visit. Lower thresholds produced 41–77% through-wall
positives. Guard 5 modestly reduced morning bleed but did not change the
tradeoff. The amplitude-only control was worse on older controls. Labels are
evaluation only; no supervised model, timers, production changes, or kitchen
data. Full report: experiments/23-footprint-shape/report.md.

## 24. Causal per-gate temporal coupling

**Status: done — no reliable gain, and the information horizon is too long for
near-imperceptible response.** A fixed bathroom-only statistic used a causal 5 s
history with 2 s exponential decay: the median per-gate Pearson correlation
of motion and still first differences, with a 0.5 s earlier-motion variant and
variance guards. On `labeled-walk-0915`, coupling AUC was .504 at lag 0 and
.537 at 0.5 s, versus .978 for the fixed amplitude control; on
`labeled-loop-0915`, it was .486/.356 versus .972. The critical two-entry walk
had identical coupling medians (.068) for IN and TW. Older labeled sessions
were directionally adverse (IN .049, TW .082). The empty through-wall morning
also had near-zero coupling (TW .027, EMPTY .014), so this is not a wall
signature. The causal prefix check passed. This differs from experiment 17 by
using one fixed per-gate EW first-difference median rather than rolling
whole-window level/variability features and a broad correlation grid. No
occupancy prototype or release rule is supported. Full report:
experiments/24-causal-gate-coupling/report.md.

## 10. Static / very-static evaluation split (HOOD)

Split replay validation scenarios by occupant stillness level; very-still is
where detectors fail and must be its own reported axis.
**Status: idea** — belongs in the validation suite regardless of the rest.

## 28. Strength-scaled new-anchor confirmation

**Status: done — rejects the observed spike, adds unacceptable delay to one arrival.** Fixed40/60/80 bands require3/2/1 frames. Post-deploy kitchen false trigger is rejected; added genuine-entry delays are0,.102,1.528,.158s. No retention dropouts or clear-time changes. The solo visit starts with an isolated motion59 pulse, so confirmation postpones it until a later strong burst. No production changes. Report: experiments/28-strength-confirmation/report.md.

## 32. Anchored gate-band hold

**Status: done — rejected.** On the replacement living-room fixture, a
gate-band hold gave no gain over the exact anchor (28.9% versus 29.0% occupied
while seated). Adding neighboring gates kept the bathroom occupied for 170 s
after a departure into the kitchen. Full stack includes same-gate balance.
Report: experiments/32-anchored-gate-band/report.md.

## 33. Entry-change hold

**Status: done — promising mechanism, insufficient reliability.** The
replacement fixture includes empty-room data before a real living-room entry.
Tracking still energy added at entry increased seated occupancy from 29.0% to
50.9% (40% retention) or 81.1% (20% retention), but the latter still had a
195 s false vacancy. Bathroom departure also lengthened. The full replay with
same-gate balance rejected the new bathroom walk-by. Report:
experiments/33-entry-change-hold/report.md.

## 34. Replacement living-room anchor-loss diagnosis

**Status: done — both baseline contamination and pattern drift matter.** In
fixture replay, still gates 3/4 already had histogram floor 100 before entry,
though an empty interval measured 7/6. The first anchor loss scored .390 just
below .400; shape cosine .701 × amplitude ratio .557. Freezing the floor at
entry had no effect; replacing it with the empty-room values improved seated
occupancy only 29.0%→35.8%. The live state cleared at score3.89 above the
default exit threshold, consistent with exclusive anchor hold. Report:
experiments/34-anchor-loss-diagnosis/report.md.

## 35. Per-gate temporal continuity hold

**Status: done — clear tradeoff.** A three-second low-percentile of the
entry-added still energy scores steady gate support higher than patchy bursts,
with entry still requiring the full balanced motion-anchor stack. At 0.2
retention, seated living-room occupancy rose 29.0%→76.8%, but a 225 s false
vacancy remained and the post-deploy bathroom stayed on for 168 s after exit.
At 0.4, bathroom release stayed near baseline while living-room hold did not
improve. Stable kitchen through-wall signal can also sustain the score.
Report: experiments/35-continuity-hold/report.md.

## 36. Lowest recurring floor with the full balanced stack

**Status: done — promising floor correction, insufficient hold fix.** With
same-gate balance enabled throughout, a causal lowest-supported histogram
peak finds still floors 7/6 instead of 100/100 at the replacement living-room
sensor's gates 3/4. Seated occupancy rises 29.0%→35.8%, and the first false
clear moves 99→127 s after entry. The trusted bathroom visit/departure
measurements, new bathroom walk-by, post-deploy kitchen false-event window,
and cat-only kitchen control are unchanged. No production change. Report:
experiments/36-low-recurring-floor/report.md.

## 37. Raw-gate source separation, independent of stack

**Status: done — simple additive split insufficient.** Offline, unsupervised
rank-two factorization of one sensor's motion/still gates yields a selected
living-room component dominant for 97.8% of the seated interval. On the two
bathroom fixtures it is dominant during 99.6–100% of real visits, but still
dominates 57–87% of the first 30 s after exit into kitchen activity. This
noncausal feasibility probe does not validate a deployable hold rule and
suggests simple additive source separation cannot distinguish the overlapping
bathroom/kitchen profiles. Labels evaluate only. Report:
experiments/37-raw-component-separation/report.md.

## 38. Post-entry still-gate shape

**Status: done — settled shape carries useful continuity, but overlaps through-wall presence.** A 3–12 s shape envelope accepts only 4.2% of later seated living-room frames. A 30–60 s settled shape matches 98.9% of later seated frames, but also 22.7% of the first 30 s after bathroom exit into the kitchen. Report: experiments/38-post-entry-envelope/report.md.

## 39. Settled-shape hold with the full balanced stack

**Status: done — not viable as a sole hold rule.** Causal settled-shape tracking raises living-room occupied coverage 29.0%→81.5%, but a 195 s false vacancy remains. It delays bathroom clearing in `labeled-loop` from 36.9 to 81.6 s. Shorter bathroom visits, the post-deploy false-entry window, and the new bathroom walk-by are unchanged. No production code change. Report: experiments/39-settled-shape-hold/report.md.

## 40. Scale-free gate-shape descriptors

**Status: done — promising independent signal, no occupancy rule yet.** Real bathroom and kitchen through-wall frames differ in still-profile kurtosis (95.7/96.1% pairwise separation across the two trusted fixtures) and motion-profile entropy (86.9/96.1%). The pattern persists in the 30 seconds after bathroom exit. These features compare the gate profile itself rather than similarity to a saved template. A lone-window, calibration-free classifier has not been validated. No production code change. Report: experiments/40-scale-free-shape/report.md.

## 41. Mixed-day living-room shape survey

**Status: done — longer recording supports shape continuity during false clears.** The mixed fixture is wholly unlabeled, but the user reports mostly living-room occupancy before 13:00. From 12:00–13:00 the integration is on only 33% of frames; while it says off, still-profile centroid/kurtosis medians are 4.25/1.88, close to the known occupied interval's 4.15/1.89 and distinct from the known empty interval's 5.19/2.54. At 12:00–12:20 the living-room state flips 14 times with kitchen and bathroom states off throughout; still-profile centroids are 4.18 on and 4.17 off. The 14:00–16:00 signal has a different, quiet-looking shape, but is not ground-truth empty. No production code change. Report: experiments/41-living-room-mixed-shape/report.md.

## 42. Scale-free shape hold in the full balanced stack

**Status: done — rejected.** A z-scored still-profile kurtosis hold rule fixes the living-room known occupied interval (26%→100%) but prolongs `labeled-loop` bathroom clearing (37→137 s) and falsely holds a known empty living-room minute. A strict setting avoids much of this at the cost of almost no living-room improvement. Two- and five-second smoothing do not remove the tradeoff. This is the actual occupancy replay of experiment 40's shape idea, not only a feature-separation diagnostic. No production code change. Report: experiments/42-shape-hold-full-stack/report.md.

## 43. Entry-only anchor with end-of-window shape review

**Status: done — much better decision architecture, single-feature tradeoff remains.** The motion anchor qualifies entry only; afterward, a complete 10–30 s still-shape window is judged at its end, with no per-frame hold refresh. A 30 s review raises replacement living-room occupancy 29%→96%, but leaves a 42 s false vacancy and clears the `labeled-loop` bathroom 43 s after exit, post-deploy bathroom 54 s after exit. A 10 s window clears bathrooms faster but barely improves the living room; requiring three consecutive 10 s clear windows restores living-room coverage but bathroom release rises to 53–64 s. No production code change. Report: experiments/43-end-of-hold-shape-review/report.md.

## 44. Window shape persistence without fixed gate position

**Status: done — single-feature tradeoff remains.** With entry-only anchor and 30 s review, accepting a window when 25% of frames have an occupied-looking still-gate shape keeps replacement living-room occupancy at 99.9%, but delays `labeled-loop` bathroom clearing to 103 s. Requiring 75% of frames brings bathroom clearing to 43 s but living-room coverage falls to 33.5%. No fixed distance or entry profile is assumed. No production code change. Report: experiments/44-window-shape-persistence/report.md.

## 45. Recent post-motion shape references

**Status: done — strong daytime result, overnight control failure.** The anchor does not update on every move, but later stronger motion candidates did update 17/10 times in the trusted bathroom fixtures and 30 times during the replacement living-room labeled interval. Saving the last four post-motion z-scored still profiles and reviewing a 20 s window raised replacement living-room occupancy 29%→99.7%, cleared the `labeled-walk` bathroom exits in 23/17 s, `labeled-loop` in 43 s, and post-deploy in 34 s. The overnight no-human bathroom control then exposed a 461 s episode (70 s with current balanced stack). Do not deploy this version. No production code change. Report: experiments/45-motion-shape-bank/report.md.

## 46. Shape evolution inside the hold window

**Status: done — independent signal, failed post-deploy departure.** Adjacent normalized still-gate profiles change less during trusted occupancy than comparison intervals. A 30 s window rule with a 0.12 shape-path cutoff raises replacement living-room occupancy 29%→98.7%, but holds the post-deploy bathroom 174 s after exit. No production code change. Report: experiments/46-window-shape-evolution/report.md.

## 47. Contrastive post-motion shape changes

**Status: done — rejected.** Comparing hold windows to recent shape changes introduced by credible motion retains replacement living-room occupancy at 96.2% with a 20 s false gap, but the post-deploy bathroom remains occupied for 174 s after exit and `labeled-walk` fails to clear appropriately. No production code change. Report: experiments/47-contrastive-motion-shape/report.md.

## 48. Confirmed bathroom false-clear fixture

**Status: done — recent-shape replay fixes the live mid-visit gap but reveals another false clear.** The live integration was vacant 20:10:38–20:11:31 while the user was in the bathroom, with active gates 2–5 and score 14.67. Replay of the current balanced stack has a 33 s false gap, not the live 53 s gap. Recent-four shape review covers the live-gap interval but goes vacant 29 s before the visit ends; shape evolution covers the visit after initial entry but fails an older through-wall case. Report: experiments/48-bathroom-false-clear/report.md.

## 49. Overnight false-anchor contrast

**Status: done — discriminating these two artifacts is possible, general rule unproven.** Both overnight bathroom false entries had only one balanced motion gate and peaks 40–46; real bathroom entries in these fixtures started at peaks 59–100. A two-gate entry guard rejects both but delays a real entry to 1.91 s and damages the living room. Motion bar 55 rejects both without delaying the known bathroom entries, but damages the living room and was selected from a very small sample. Combined bathroom-only with recent-four 20 s shape review at correlation 0.78, it passes the observed overnight and new false-clear checks, but is not independently validated. No production code change. Report: experiments/49-two-gate-anchor/report.md.
