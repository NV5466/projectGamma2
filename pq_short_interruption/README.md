# pq_short_interruption

## Seed purpose

Short interruption is a power-quality seed for voltage collapsing or nearly collapsing for a short bounded interval.

## What this folder should contain

- Synthetic interruption generator or fixture data
- Voltage captures with pre/post context
- Duration measurements
- Optional load/current channel examples

## Diagnostic markers

- Sliding RMS drops near zero or a very low per-unit value
- Event duration is central evidence
- Recovery may include secondary transient content

## Best Gamma/ElectroStat modules

- sliding RMS
- duration measurement
- STFT
- event timeline

## Confidence rule

High confidence requires a true low-voltage interval over a measurable duration. Low confidence if the apparent interruption is a dropped probe, missing sample block, bad reference lead, or capture artifact.

## Not equivalent to

- pq_voltage_sag
- unplugged probe
- data dropout
