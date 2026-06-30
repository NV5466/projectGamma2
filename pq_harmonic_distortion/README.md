# pq_harmonic_distortion

## Seed purpose

Harmonic distortion is a power-quality seed for steady waveform distortion with repeatable energy at integer multiples of the line fundamental.

## What this folder should contain

- Synthetic harmonic generator
- Voltage/current captures with line-frequency context
- Expected FFT bins and THD values
- Regression plots or JSON output

## Diagnostic markers

- Persistent integer-order spectral lines
- Elevated THD
- Repetitive non-sinusoidal waveform shape
- Current distortion may be stronger than voltage distortion near the source

## Best Gamma/ElectroStat modules

- FFT
- harmonic bins
- THD
- PSD

## Confidence rule

High confidence requires stable integer-order content across repeated captures. Low confidence if the spectrum is broadband smear, leakage, aliasing, or record-length error.

## Not equivalent to

- pq_flicker_am_mod
- random broadband EMI
- bad FFT setup
