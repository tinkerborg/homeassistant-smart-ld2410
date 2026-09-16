# Prior art: learned radar presence detection

Web survey (2026-09-11) of academic, commercial, and community work relevant to
host-side learned presence on LD2410 gate energies. Four problems framed the
search: (1) noise-floor learning during occupancy, (2) through-wall bleed
rejection, (3) motionless person vs empty, (4) zero-setup self-calibration.

## Top finds

**1. Acconeer A121 Presence Detector — closest algorithmic analogue.**
Two parallel per-distance-bin branches: *intra-frame* deviation (fast motion)
and *inter-frame* deviation computed as `√Ns · |ȳ_fast − ȳ_slow|` — the gap
between two exponential filters at different cutoffs, a band-pass tuned to
breathing/slow repositioning. Noise floor estimated **without a calibration
phase** by triple-differentiating across sweeps (isolating high-frequency
content that can't be human) and taking mean absolute deviation, updated
continuously (~10 s time constant). Scores normalized against that floor;
`max_d` gives the score, `argmax_d` the distance. Inter-frame timeout decays
the score to accelerate exit.
Informs (1): a floor estimator structurally immune to occupancy — it measures
sweep-to-sweep high-frequency content, not a time window. Informs (3):
slow/fast filter differencing extracts motionless-person energy without
vital-sign extraction.
https://docs.acconeer.com/en/latest/detectors/a121/presence_detector.html
A111 sparse variant with more math:
https://docs.acconeer.com/en/latest/a111/algo/presence_detection_sparse.html

**2. HOOD: Human Presence and Out-of-Distribution Detection (arXiv 2308.02396).**
Reconstruction autoencoder over macro+micro range-Doppler; frames
"moving/stationary clutter with no human" as an OOD class rather than a
threshold. E-RESPD preprocessing for near-invisible body motion. Dataset:
BGT60TR13C across 28 rooms, static/very-static split.
Informs (3), (4) — and the static/very-static split is the right evaluation
axis. https://arxiv.org/abs/2308.02396 · sibling:
https://arxiv.org/pdf/2302.14192

**3. US12379465 — "Identification of room perimeter using radar" (granted).**
Room boundary from radar statistics alone: high-energy reflectors as convex
corners; mirror/symmetric-motion detection; radar *shadowing* (moving target
occluding a static reflector implies a wall between); long-term velocity
statistics (velocities drop near walls, rise at doorways) with entry/exit
clustering to locate doors. Does not claim using the perimeter to reject
out-of-room detections. The only learned room-boundary work found.
https://patents.google.com/patent/US12379465B1/en

**4. r-mccarty/presence-detection-engine — only host/edge statistical learner
on LD2410 found.** ESP32: MAD-based auto-calibrated baseline, z-score +
hysteresis, debounced 4-state machine, distance windowing. Calibration is a
guided wizard (user vacates room); bed presence, no per-gate decomposition,
no through-wall logic.
https://github.com/r-mccarty/presence-dectection-engine

**5. Gennarelli et al., "CW Doppler Radar as Occupancy Sensor" (Frontiers in
Signal Processing, 2022).** Three detectors on the same 24 GHz CW hardware:
time-domain std-dev, **amplitude histogram**, Doppler-spectrum energy; >96%
accuracy. The histogram detector is a distribution-shape test on exactly the
kind of scalar energy stream the LD2410 emits.
https://www.frontiersin.org/journals/signal-processing/articles/10.3389/frsip.2022.847980/full

## Problem 1 — adaptive noise floor learned while occupied

- Clutter-map literature, "target-in-cell" degradation: per-cell background
  updates degrade when a target persists — the canonical statement of the
  problem, Weibull-background analysis.
  https://www.sciencedirect.com/science/article/abs/pii/S1434841113000058
- CFAR / clutter distribution identification (Metcalf, KU PhD): indoor clutter
  is Weibull/log-normal, not Rayleigh; argues for heavy-tailed per-bin models
  over Gaussian mixtures.
  https://www.ittc.ku.edu/~sdblunt/theses-dissertations/Metcalf%20KU%20PhD%20dissertation.pdf
- Mixture-VAE unsupervised radar detection under complex clutter: clutter as a
  learned mixture, targets as low-likelihood.
  https://www.mdpi.com/2072-4292/14/18/4449
- Adaptive clutter-edge detection: detecting the *transition* between clutter
  regimes — "gate k just changed population" rather than "time passed."
  https://www.sciencedirect.com/science/article/abs/pii/S0165168421001651
- UltraSense: self-calibrating ultrasound occupancy, no user setup; different
  modality, same contract.
  https://www.researchgate.net/publication/317548394_UltraSense_A_Self-Calibrating_Ultrasound-Based_Room_Occupancy_Sensing_System

## Problem 2 — through-wall bleed / adjacent-room rejection

- Building-material attenuation (arXiv 2004.12568): gypsum stud wall ≈ 4.8 dB
  one-way, ~10 dB round trip — quantitative basis for the observed 100 vs
  40–50 amplitude ceiling. https://arxiv.org/pdf/2004.12568
- Through-wall detection with raw ADC + parametric NNs (arXiv 2403.15468):
  what the through-wall signature looks like.
  https://arxiv.org/html/2403.15468v1
- Through-wall heartbeat via single-channel 24 GHz CW: bleed is physics;
  amplitude-vs-material data.
  https://www.ncbi.nlm.nih.gov/pmc/articles/PMC10847523/
- TI Zone Occupancy / People Counting: static clutter removal + 2-pass
  CFAR-CASO; the commercial answer to adjacent rooms is *geometric zones*.
  https://www.ti.com/lit/ug/tiduea7/tiduea7.pdf
- Aqara FP2: user manually marks "edge" zones beyond walls. No learning.
  https://www.aqara.com/wp-content/uploads/2023/06/Presence-Sensor-FP2_User-Manual.pdf
- Everything Presence Lite/One: "set room size no larger than the room";
  penetration through plasterboard acknowledged as inherent.
  https://everythingsmarthome.github.io/everything-presence-lite/tuning.html ·
  https://github.com/EverythingSmartHome/everything-presence-one/issues/2
- HA community canonical false-positive thread (LD2410):
  https://community.home-assistant.io/t/hlk-ld2410-regular-false-positives/816276
- Community physical mitigation — foil/absorber shielding the rear lobe:
  https://community.home-assistant.io/t/my-experience-with-screek-mmwave-motion-presence-detectors-mod-to-block-backward-wave/816096

## Problem 3 — motionless person vs empty

- Lightweight range-angle imaging for quasi-static detection on low-cost FMCW
  (arXiv 2602.14001): continuously-updated background, adaptive thresholds,
  static clutter vs motionless breathing human, runs on a Pi 4.
  https://arxiv.org/pdf/2602.14001
- Simultaneous presence + breathing rate (Sensors 2021): SNR needed at range
  for breathing recovery. https://doi.org/10.3390/s21103529
- Respiration pattern analysis, stationary subject, orientation-independent
  (Biosensors 2025): https://doi.org/10.3390/bios15050273
- Unobtrusive occupancy + vitals (Sci Rep 2023): 60 GHz, >93% accuracy with
  mostly-stationary occupants; threshold = empty mean + 1.5σ — a baseline to
  beat. https://www.nature.com/articles/s41598-023-27425-6
- Infineon macro vs micro motion: two-threshold architecture; micro
  sensitivity costs range.
  https://community.infineon.com/t5/Knowledge-Base-Articles/XENSIV-60-GHz-radar-sensors-Understanding-macro-and-micro-motions/ta-p/761868
- LD2410 static-target absorption, documented: firmware ≥ V2.44 background
  detection absorbs a fully still person ("complete immobility leads to the
  target disappearing").
  https://espeasy.readthedocs.io/en/latest/Plugin/P159.html ·
  https://github.com/esphome/feature-requests/issues/3161

## Problem 4 — learned occupancy without setup

- ORACLE: self-calibrating mmWave radar network, zero-setup deployment.
  https://arxiv.org/pdf/2208.14199
- HMM occupancy without labeled training data (Energy & Buildings):
  two-state occupied/vacant latent over energies.
  https://www.sciencedirect.com/science/article/abs/pii/S0378778821008781
- Physics-informed switching process with Markov regime (arXiv 2409.11743):
  regime-switching rather than time-windowed background inference.
  https://arxiv.org/pdf/2409.11743
- Single-channel CW radar occupancy via deep learning (Sci Rep 2025): 24 GHz
  CW SOTA number to cite against (~92.7%).
  https://www.nature.com/articles/s41598-025-95752-x

## Tooling

- aio-ld2410 (asyncio, engineering mode): https://github.com/morian/aio-ld2410
- mmwave_presence (minimal): https://github.com/mattdm/mmwave_presence
- micropython-ld2410: https://github.com/melastmohican/micropython-ld2410
- ESPHome LD2410 component (manual calibrate-by-eye loop):
  https://esphome.io/components/sensor/ld2410/
- everything-presence-pro-grid (host-side rethink of a commercial radar):
  https://github.com/clintongormley/everything-presence-pro-grid/

## Gap analysis

Host-side self-learning on LD2410 gate energies is effectively novel:

- Nothing found learns per-gate statistics during occupancy; every LD2410
  pipeline calibrates once, in a vacant room. Acconeer alone estimates its
  floor continuously, using raw sweep-rate data the LD2410 doesn't expose.
- Amplitude-ceiling through-wall discrimination appears unpublished. The
  literature measures wall losses or exploits penetration; commercial
  practice is uniformly geometric and manually configured. Needing no angle
  information is what makes the approach available on an LD2410; this is the
  most defensibly novel piece.
- Room-boundary learning from radar statistics exists only as a patent
  (US12379465), on multi-receiver hardware, without the rejection step.
- The LD2410's static-target absorption is treated everywhere as a tuning
  problem; host-side retention of a still target against the sensor's
  internally-drifting background is unaddressed.
- No public dataset of LD2410 engineering-mode gate energies with occupancy
  labels exists; evaluation must be self-collected.

Worth adopting directly: Acconeer's fast/slow exponential-filter difference as
the still-presence statistic (cheap per gate at 10 Hz), and Gennarelli's
amplitude-histogram detector as a distribution-shape alternative to the
quantile floor.
