# Through-wall filtering: focused survey

Follow-up dig (2026-09-12) on filtering through-wall events specifically —
how a wall-transmitted signature differs from a direct one beyond raw
amplitude, plus mitigation. Complements [prior-art.md](prior-art.md).

## Headline findings

1. **Dispersion/delay is a dead end at this bandwidth.** Drywall adds
   ~1.4 cm two-way path vs a 75 cm gate; FDTD studies (Amin/Ram) show
   walls change *magnitude* (attenuation + fading) while leaving Doppler
   essentially intact. The compensable — hence detectable — quantity is
   amplitude fading, not range smear.
   https://ieeexplore.ieee.org/document/5404249/ ·
   https://arxiv.org/pdf/2404.08739
2. **The bleed likely arrives via the back lobe.** For an in-wall sensor
   the adjacent room is *behind* the PCB, and HLK's own manual states the
   back lobe may detect moving objects behind the radar and prescribes a
   metal shielding cover/backplane. No published LD2410 front/back ratio
   exists — measurable by rotating a module 180° against a fixed walker.
   https://seengreat.com/upload/file/86/HLK+LD2410+Life+Presence+Sensor+Module+Manual+V1.03(220629).pdf
3. **IMEC EP3525002A1 — unsupervised boundary learning ("intent
   mapping").** Per-region velocity-direction histograms; regions whose
   histograms stay empty are walls/no-go, because targets move along or
   away from barriers, never through. Collapses to 1-D gate indices.
   Family: US20190250262A1, JP7376240B2.
   https://patents.google.com/patent/EP3525002A1/en

## Signal-shape / statistics

- Wall multipath produces delayed weaker "ghost" replicas at greater
  range moving with the primary → lagged cross-gate correlation feature.
  https://www.researchgate.net/publication/319987846_Through-the-Wall_Radar_Imaging_A_Review
- Scintillation framing: in-room ≈ Rician (dominant specular, shallow
  fades); through-wall trends Rayleigh (deep frequent fades) at the same
  mean amplitude — exactly the 40-58 band the amplitude ceiling can't
  resolve. https://en.wikipedia.org/wiki/Scintillation_(radar)
- Standard UWB per-bin feature set (skewness, kurtosis, entropy, energy);
  wavelet entropy separates human echo from clutter and works under
  shadowing, directly computable at 10 Hz.
  https://asp-eurasipjournals.springeropen.com/counter/pdf/10.1186/s13634-021-00738-2.pdf ·
  https://doi.org/10.3390/s17102255
- Cross-bin correlation/periodicity instead of energy (near targets
  dominate far): https://www.mdpi.com/1424-8220/16/11/1793

## Trajectory / velocity patents

- US10055958/10319205/10438471: "destination motion" (long path,
  sustained Doppler/duration) vs "local motion" (random in-place) for CW
  occupancy — the marches-vs-flickers discriminator, patented; check
  claims before building on it.
- US12379465 (room perimeter) has a live continuation US 19/249,570 —
  watch for a rejection-step claim.

## Hardware mitigation

- 24 GHz absorber (graphite/carbon-micro-coil silicone), 99.3% absorption
  at 0.85 mm: https://ieeexplore.ieee.org/document/6422782
- Commercial elastomer absorber sheets with PSA (3PB automotive):
  https://www.3pbsolutions.com/rf-absorbers-automotive-radar/
- Metamaterial absorber loading: −15 dB back radiation, +2.7 dB forward
  gain: https://www.ncbi.nlm.nih.gov/pmc/articles/PMC7085057/

## Vendors

Aqara FP2 auto-learning runs only on vacant rooms; TI/Novelda are
configured zones/range limits; Infineon's answer is ceiling mounting;
Acconeer names the revealed-wall failure and offers only range limiting.
Nothing learns the wall while occupied.

## Ranked: three new things to try on gate energies

1. **Per-gate transition histograms (intent mapping, 1-D).** Track
   argmax-gate over time; accumulate signed gate-transition and dwell
   histograms per gate. In-room motion marches through contiguous gates
   both directions; through-wall parks in a fixed band with near-zero net
   transitions, and gates between sensor and wall stay empty of inward
   crossings. Learns the wall's gate index label-free; composes with the
   leading-edge test.
2. **Fade statistics per gate.** 1-3 s sliding window: coefficient of
   variation, deep-fade rate, envelope kurtosis/entropy. Prediction:
   in-room shallow fades, through-wall deep fades at equal mean — the
   overlap case amplitude can't split. Histogram-shape detection is
   already validated on this hardware class (Gennarelli).
3. **Metal backplane + thin absorber behind the module**, after measuring
   the front/back ratio (rotate module against a fixed walker). If the
   in-wall bleed is back-lobe, a few dollars of shielding lifts every
   software discriminator's margin and bounds what software must solve.

Runner-up: shadowing asymmetry — an in-room person occludes gates behind
them; a through-wall person can't occlude anything nearer than the wall.
"Post-peak gate deficit" is free to compute; physics confirmed, no
published 1-D statistic.
