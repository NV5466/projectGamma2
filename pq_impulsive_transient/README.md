# pq_impulsive_transient

## Seed purpose

Impulsive transient is a seed for a short high-amplitude spike-like disturbance on a power or signal line.

## What this folder should contain

- Impulse/spike synthetic generator
- Example transient captures
- Peak and duration measurements
- Wavelet or STFT output

## Diagnostic markers

- Very short event duration
- High peak relative to baseline
- Broadband spectral content
- May appear once or in sparse isolated events

## Best Gamma/ElectroStat modules

- peak detection
- wavelet
- STFT
- transient event windows

## Confidence rule

High confidence requires a real short-duration peak with sufficient sample rate and no clipping ambiguity. Low confidence if it is a single bad sample, ADC glitch, or probe artifact.

## Not equivalent to

- emi_eft_burst
- pq_oscillatory_transient
- single-sample corruption
