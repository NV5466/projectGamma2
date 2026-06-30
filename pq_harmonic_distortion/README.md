# Gamma / ElectroStat Harmonic Distortion Seed v0.1.0

## Core architecture

WaveCompare 2 supplies the singular expected waveform.

The HD seed extracts:

    h_expected
    h_measured
    delta_h = h_measured - h_expected

For order n:

    h_n = A_n / A_1

The full vector h is the primary diagnostic measurement.

THD is derived afterward:

    THD = sqrt(sum(h_n^2))

## Method

1. Remove DC and linear trend.
2. Estimate f0 by harmonic-summed spectral search.
3. Refine f0 using harmonic least-squares error.
4. Fit sine/cosine coefficients directly at n*f0.
5. Normalize amplitudes to the fundamental.
6. Compare harmonic order by harmonic order.

Direct sinusoidal regression avoids requiring exact FFT-bin alignment.

## Historical captures

Every old capture may be analyzed and stored.

The v0.1.0 field:

    used_in_fault_score = false

is deliberate. Historical fingerprints are preserved for the later
machine-specific normal-variation layer, but they do not currently decide
whether a deviation is acceptable.

## Preserved outputs

- expected and measured f0
- h_expected, h_measured, and delta_h
- per-order uncertainty and significance
- expected, measured, and delta THD
- odd/even harmonic energy
- shift-invariant relative phase
- harmonic reconstruction
- non-harmonic residual
- optional historical fingerprint table

Relative phase is supporting evidence and is not part of the v0.1.0
primary magnitude-vector decision.

## Synthetic validation

Cases: 270
Sensitivity: 1.000000
Specificity: 1.000000
Precision: 1.000000
Balanced accuracy: 1.000000
Runtime: 20.93 seconds

The equal-THD test uses:

    expected: 10% third harmonic
    measured: 6% second + 8% fifth

Both have approximately 10% THD, but the seed detects the changed
harmonic vector.

This is a synthetic research prototype, not field calibration.
