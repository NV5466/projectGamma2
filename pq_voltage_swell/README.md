# pq_voltage_swell

## Seed purpose

Voltage swell is a power-quality seed for RMS voltage rising above nominal for a bounded event window.

## What this folder should contain

- Synthetic swell generator or fixture data
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
