ElectroStat Ensemble Hankel / Matrix-Pencil Seed

This module analyzes every aligned measurement independently, compares the pole
outcomes across captures, clusters repeated modes, then refines each repeated
cluster by horizontally stacking valid Hankel matrices.

It never stitches raw captures end-to-end. That would create artificial boundary
jumps and fake poles.

Pipeline
1. Use the explicit WaveCompare 2 waveform as the repeatable reference.
2. residual_i = capture_i - reference
3. Detect physical event windows independently in every residual.
4. Apply matrix pencil to each event window.
5. Cluster similar real or complex poles across captures.
6. Stack Hankel matrices from matching event windows to refine shared poles.
7. Report occurrence rate, pole spread, refined pole, and captures where absent.

Current mode labels
- oscillatory: stable complex-conjugate mode, represented by its positive-frequency pole.
- real_decay: stable nearly real decay pole. The later impulsive classifier will fit
  the rise and tail explicitly.

Synthetic validation
- 24 captures total
- Persistent distorted/notched waveform in all captures
- 8 sparse damped oscillatory events
- 5 sparse double-exponential events
- 11 captures with no injected transient

CLI
python electrostat_ensemble_hankel.py capture_01.csv capture_02.csv ...     --reference wavecompare2_reference.csv     --output-prefix electrostat_ensemble

Capture CSV columns: time_s, voltage_v
