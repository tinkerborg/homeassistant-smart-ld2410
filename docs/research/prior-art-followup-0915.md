# Follow-up literature search: separating concurrent signals

2026-09-15. Compared with `prior-art.md`, the technique inventory, and existing
experiment reports. No implementation or efficacy claim from this survey.

## 1. Temporal blind source separation (SOBI) — first candidate

Belouchrani et al., *A blind source separation technique using second-order
statistics* (1997), separates instantaneous linear mixtures using temporal
coherence and joint diagonalization of covariance matrices. It estimates the
mixing without known source labels. Primary source abstract:
https://researchportal.ip-paris.fr/en/publications/a-blind-source-separation-technique-using-second-order-statistics/
DOI: https://doi.org/10.1109/78.554307

**Proposed application, not a published LD2410 result:** treat bathroom gate
streams as several observations of overlapping sources; test whether different
temporal behavior permits separating components during simultaneous occupancy.
This differs from experiment 17's correlation features fed into a supervised
classifier and experiment 23's similarity to one stored footprint. Correlation
measures association; source separation attempts to recover the components.

Critical limits: this is statistical parameter estimation (often categorized
as unsupervised learning), not a labeled occupancy classifier. The idealized
linear mixing assumption is unverified for clipped, internally processed gate
energies. Gate channels may be redundant, and motion changes mixing patterns.
Even successful decomposition does not identify which component is inside the
bathroom. Similar source dynamics can defeat separation. Estimation requires
history; continuous updates do not establish imperceptible detection of a new
source. None of these sources proves an unlabeled room-assignment rule.

A bounded first experiment should test component stability, reconstruction,
and concurrent-source separability causally, using labels only afterward.
Reject any result needing hand-picked kitchen-only training intervals or
post-hoc selection of the component that matches bathroom labels.

## 2. Robust subspace tracking — second candidate, higher retention risk

GRASTA tracks a changing low-dimensional subspace online despite sparse
outliers. Its original demonstrations include streaming video background /
foreground separation, not this occupancy problem:
https://arxiv.org/abs/1109.3827

Radar-specific precedent: *Low-Rank Matrix Recovery Approach for Clutter
Rejection in Real-Time IR-UWB Radar-Based Moving Target Detection* (2016)
uses low-rank/sparse decomposition with overlapping windows to distinguish
static background and moving targets:
https://pmc.ncbi.nlm.nih.gov/articles/PMC5038687/

**Proposed application:** represent recurring correlated gate variations by a
small number of changing patterns, then inspect unexplained components rather
than subtracting one fixed background vector. This might model a changing
neighbor signal better than experiment 21, but identifying a moving neighbor
as background is an additional assumption, not what the papers establish.
A quiet bathroom occupant can also become background. Multiple people can
violate sparsity; seven usable still gates offer little independent spatial
information. This is not a cure for quiet-person retention by itself.

## 3. Successive cancellation / vital-sign separation — not a direct fit

Chian et al., *Signal Separation and Tracking Algorithm for Multi-Person
Vital Signs by Using Doppler Radar* (2020), separates multiple people's vital
sign trajectories with frequency separation and successive cancellation:
https://discovery.ucl.ac.uk/id/eprint/10122808/

Its single-antenna narrowband radar result is relevant evidence that multiple
people need not imply multiple physical sensors. However, it uses Doppler
observations across time, not LD2410 engineering-mode gate magnitudes. It does
not establish wall rejection or subsecond presence decisions. We should not
transfer its accuracy numbers to our sensor or task.

## Recommendation

SOBI-style temporal separation is the most distinct follow-up found in this
bounded search. Test its assumptions before building another occupancy stack.
Robust subspace tracking is a secondary candidate. Neither is a demonstrated
solution to distinguishing two rooms from the available gate readings.

The ongoing temporal-coupling experiment is separate; this survey neither
changes its predefined comparisons nor supplies a trained decision rule.
