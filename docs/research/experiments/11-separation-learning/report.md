# Experiment 11: separation learning (leading-edge enablement)

Question: can a sensor learn label-free whether leading-gate separation
exists (spec 24 §1's per-room enablement), via confirmed-dwell vs fizzled
episode leading-gate histograms? Data: all sensors, all history (9.1M
frames). Scripts: sep_ep.py, sep_an.py.

## Verdict

**Not learnable with this proxy — structural failure, not lack of data.**
The feature is real (genuine 22:04 entry leads g0; both through-wall
latches lead g2), but the proxy label is broken: "confirmed dwell ≥60s"
is DOMINATED by through-wall activity (cooking sustains 60s as reliably
as a bathroom visit — 65% of D0:6E's confirmed episodes lead g2). True
entries are a ~15-20% minority inside their own class, separated from the
majority exactly along the axis being learned. Every sensor returns
"disable" (overlaps 0.6-0.87); P(confirmed | near lead) = 0.12 vs 0.09 —
noise. Excising the known bleed hour doesn't help (contamination is
diurnal, not episodic). Self-training on the shipped detector's own
latches would reinforce the false mode.

Method notes: episodes must be cut on suppressed (not raw) residuals;
onset horizon matters (FD:68 re-entry reaches lead ≤1 only ~40s in) —
scored at 3/10/20/30s, verdict unchanged. The 09-09 label events are too
coarse to arbitrate (6 usable episodes).

## Paths forward (untested)

- Replace the outcome proxy with a departure-side signature the
  through-wall class can't satisfy.
- Two-component mixture fit on the confirmed histogram requiring a
  gap-separated near mode (D0:6E shows a g0 spike with an empty g1), but
  g0 is also 11-20% of the fizzled class (gate-0 chatter) — would need a
  support/amplitude term.

## Spec impact

Spec 24 §1's enablement-by-separation-histograms and acceptance §8 are
invalidated as designed; until a valid proxy exists, leading-edge
enablement stays global (lead_gate_max option), which is correct for this
house and unproven elsewhere.
