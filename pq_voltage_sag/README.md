# pq_voltage_sag

## Seed purpose

Voltage sag is a power-quality seed for RMS voltage dropping below nominal for a bounded event window.

## What this folder should contain

- Synthetic sag generator or fixture data
- Example voltage captures
- Optional current channel showing inrush or upstream response
- Expected report output, metrics, or regression JSON

## Diagnostic markers

- Sliding RMS envelope steps downward
- Fundamental waveform often remains mostly preserved
- Event duration matters more than one isolated sample
- Corroborating current behavior can strengthen confidence

## Best Gamma/ElectroStat modules

- sliding RMS
- FFT / THD
- STFT
- event timeline

## Confidence rule

High confidence requires a measurable RMS drop over a valid event interval. Low confidence if the event is a single-sample excursion, clipped capture, bad probe reference, or appears on only one questionable setup.

## Not equivalent to

- pq_short_interruption
- pq_impulsive_transient
- probe scaling error
