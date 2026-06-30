# Common-mode multi-spectral validation

This controlled test feeds two aligned channel ensembles into the same basic
pipeline proposed for Gamma:

1. Remove each channel's WaveCompare 2 collective waveform.
2. Retain every residual capture.
3. Compute a complex FFT for every residual.
4. Average auto-spectra and cross-spectra over capture index.
5. Compare residual peak occupancy, proportional gain, coherence, and phase.
6. Classify each persistent residual frequency.

Synthetic injections:

- 60 Hz: proportional same-polarity disturbance in both channels
- 180 Hz: opposite-polarity disturbance in both channels
- 310 Hz: channel 1 only

Observed output:

- 60 Hz: common-mode
- 180 Hz: differential / opposite-polarity
- 310 Hz: channel 1 local

This uses the exact known repeatable waveforms as WC2 inputs so the test isolates
the classifier. Real validation must use actual WC2 output and paired measured
captures.
