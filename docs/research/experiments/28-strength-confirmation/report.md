# 28. Strength-scaled confirmation for new motion anchors

Fixed rule proposed before replay:
- Current motion peak 80+: admit immediately.
- Current peak 60–79: require two consecutive frames >=40.
- Current peak 40–59: require three consecutive frames >=40.
- Below40, backwards time, or gap>.55s resets pending confirmation.

Confirmation affects NEW templates only. Existing template updates, still
retention and release math are unchanged. Same gate2–8 peak as the original
anchor; no requirement that each frame peaks in the same gate. No live changes.

Reuses experiment26's exact scorer/suppression/energy-filter classes and its
experimental histogram baseline adapter. Both variants have no extra release
timer, isolating creation behavior. Labels only evaluate results. This is not
an exact reconstruction of the deployed baseline state/configuration, which
was not exported. Post-deploy labels are approximate reconstructed annotations.

## Results

| Visit | Original entry after label | Scaled entry after label | Added delay |
|---|---:|---:|---:|
| Labeled walk first | 1.693 s | 1.693 s | 0 |
| Labeled walk second | .016 s | .118 s | .102 s |
| Labeled solo loop | .385 s | 1.913 s | **1.528 s** |
| Post-deploy brief visit | .713 s | .872 s | .158 s |

No post-detection dropouts in either variant; clear times identical for every
visit. The post-deploy false-entry window (22:36:44–22:38:40) changes from
984 occupied frames in the baseline simulation to **zero** under confirmation.
The recorded45→42→36 burst cannot establish a new anchor under the rule.

The longer solo delay is not three-frame computational latency: its initial
motion peak59 at label+.385s is followed by15,6,23 and other subthreshold
readings. The next qualifying run is55 at+1.811s then100 at+1.913s. Confirmation
rejects a genuine isolated early movement along with the false burst.

Thus the fixed80/60/40 scheme blocks this false entry but does not preserve
near-imperceptible detection for all recorded arrivals. No thresholds were
retuned to erase the tradeoff. Differences between algorithms on identical
frames are measurable; label offsets are not independent physical latency.

## Reproduction

`.venv/bin/python docs/research/experiments/28-strength-confirmation/analyze.py`

Outputs: `results.json`. Each fixture is processed from its full available
prefix with no label-selected calibration. Prefix causality checks pass.
Fixed-rule sanity checks confirm two borderline frames rejected, three
borderline accepted, moderate second-frame accepted, and strong immediate
entry. All inference uses only bathroom readings.
