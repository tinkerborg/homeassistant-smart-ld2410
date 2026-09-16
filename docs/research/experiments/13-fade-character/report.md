# Experiment 13: fade-character discrimination

Question: does per-event amplitude-fade character (Rician shallow fades
in-room vs Rayleigh deep fades through-wall) separate classes on LD2410
gate energies at 10 Hz? Scripts: e13_*.py; 52,693-window feature table.

## Verdict

**Doesn't separate — the 10 Hz chip-side smoothing destroyed the
substrate**, the same failure mode as the frame-to-frame floor
(experiments 1-2). Falsifies prediction #2 of
[through-wall-filtering.md](../../through-wall-filtering.md); its #1
(transition/dwell histograms) and #3 (backplane shielding) are untouched.

Three independent nails:

1. **No fading structure reaches the API.** Move channel lag-1
   autocorrelation ≈ 0 (decorrelated noise); still channel ≈ 0.7-1.0
   with mean |Δ|/median 1.7% (heavily filtered slow level). Neither is
   an envelope, so Rician-vs-Rayleigh has nothing to operate on.
2. **What weakly separates points the WRONG way** (in-room shows higher
   CV, lower K — it's proximity/motion-richness, not fade character),
   and its sign flips between channels and sensors (still-channel CV AUC
   0.448-0.640 across pairings). Cross-fixture AUC 1.6x within-fixture:
   mostly recording identity.
3. **Through-wall is indistinguishable from empty** on fade features
   (AUC 0.549) — they never see the through-wall person.

Hard cases: the 40-58 overlap band doesn't exist on the move channel
(through-wall move max 19.6); on the still channel the band's best AUC is
0.65 pooled and 0.41 (reversed) within-fixture. Amplitude-matched
same-gate windows: AUC 0.49 at energies 8-12 (chance); separation appears
only above 16 where through-wall barely exists. Per-event classifier:
classes overlap with negative margin (lowest in-room CV 0.420 below
highest through-wall 0.427).

Per-gate accumulation recovers no room structure — CV is flat 0.44-0.47
across all active gates on every sensor; the only clean CV separation is
signal-vs-noise-floor, which the energy test already provides.
