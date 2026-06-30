# pq_voltage_swell

## Seed purpose

Voltage swell is a power-quality seed for RMS voltage rising above nominal for a bounded event window.

## Current worker note preserved from original root README

This repository originally opened with:

```text
Gamma / ElectroStat Swell Seed v0.1.3
```

The worker was described as a fully integrated end-to-end swell worker.

Changes from v0.1.2:

```text
- residual energy classifies clean versus distorted behavior;
- residual energy does not erase supported swell evidence;
- a candidate must have an equivalent rectangular excess duration of
  at least 2.0 selected analysis windows.
```

That last rule prevents moving-window smearing from promoting a short spike or one offset-edge artifact into a sustained swell.

Original visible validation metrics:

```text
Validation cases: 900
Sensitivity: 0.996667
Specificity: 1.000000
Precision: 1.000000
Balanced accuracy: 0.998333
Runtime: 50.80 s
```

Boundary:

```text
Synthetic research prototype only; no field calibration claim.
```

## What this folder should contain

- Swell synthetic generator or fixture data
- Voltage captures with pre-event and post-event context
- Sliding-RMS measurements
- Expected report output, metrics, or regression JSON

## Diagnostic markers

- Sliding RMS envelope steps upward
- Fundamental remains dominant unless distortion is also present
- Event lasts long enough to be more than a spike or offset-edge artifact

## Best Gamma/ElectroStat modules

- sliding RMS
- FFT / THD
- STFT
- event duration check

## Confidence rule

High confidence requires a sustained RMS increase with sane probe scaling and enough pre/post record. Low confidence if the waveform is clipped, saturated, or only one channel shows an impossible level change.

## Not equivalent to

- pq_impulsive_transient
- pq_harmonic_distortion
- probe gain error
