# Motion-anchored still-energy tracking

The default stage stack includes `motion_anchor` after `energy_floor`.
Entry requires the ordinary score/energy filters and a supported motion anchor.
The anchor uses gates 2–8, still residuals normalized by baseline floor/spread,
a raw motion threshold of 40, and a retained template fraction of 0.4.
Strong motion captures or strengthens the motion-weighted still template.
Loss of template support starts the detector's existing configurable `hold_s`
countdown; recovery cancels that countdown. No additional timer is introduced.
While enabled, anchor support supplies hold refresh instead of other hold stages.
The anchor is transient and reacquires after restart. Cold-start baseline
passthrough is unchanged. Removing the stage restores the other selected hold
mechanisms. Timestamp reversal or a frame gap above 0.55 s discards its template.
