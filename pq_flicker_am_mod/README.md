# pq_flicker_am_mod

## Seed purpose

Flicker / low-frequency amplitude modulation is a power-quality seed for slow envelope modulation of a voltage waveform.

## What this folder should contain

- AM/flicker synthetic generator
- Voltage captures with RMS trend data
- Sideband or STFT examples
- Expected confidence output

## Diagnostic markers

- RMS envelope varies slowly
- Sidebands appear around the line fundamental
- Disturbance is modulated rather than a one-time sag or swell

## Best Gamma/ElectroStat modules

- RMS trend
- sideband detection
- STFT
- envelope analysis

## Confidence rule

High confidence requires repeatable low-frequency modulation of the waveform envelope. Low confidence if the record is too short to distinguish flicker from drift or a one-off voltage event.

## Not equivalent to

- pq_voltage_sag
- pq_voltage_swell
- slow probe/reference drift
