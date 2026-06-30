# Gamma / ElectroStat Short Interruption Seed v0.1.1

This worker reuses the sag event architecture while changing the
classification gate to retained local RMS below 0.1 pu.

The v0.1.1 correction removes an invalid confidence veto. A waveform
that is below 0.1 pu for the required duration is an interruption by
the configured magnitude-duration rule even when it lies close to the
0.1 pu boundary. Confidence is still reported, but it does not overrule
the classification itself.

Magnitude regions:

- sag: 0.1 to 0.9 pu retained RMS
- interruption: below 0.1 pu retained RMS

Duration labels:

- instantaneous: 0.5 cycle through 30 cycles
- momentary: above 30 cycles through 3 seconds
- temporary: above 3 seconds through 60 seconds
- sustained: above 60 seconds

Synthetic cases: 330
Sensitivity: 1.000000
Specificity: 1.000000
Precision: 1.000000
Balanced accuracy: 1.000000
Runtime: 17.45 seconds

This is a synthetic research prototype, not field calibration.
