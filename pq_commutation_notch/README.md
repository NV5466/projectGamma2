# pq_commutation_notch

## Seed purpose

Commutation notch is a power-quality seed for narrow recurring depressions in an AC waveform, often associated with converter commutation.

## What this folder should contain

- Notched sine synthetic generator
- Example voltage captures
- Notch timing measurements
- FFT or wavelet evidence output

## Diagnostic markers

- Narrow repetitive waveform depressions
- Timing repeats at predictable phase locations
- Higher-frequency content appears around notch edges

## Best Gamma/ElectroStat modules

- edge detection
- FFT
- wavelet
- phase-locked event timing

## Confidence rule

High confidence requires notches that repeat at consistent phase/timing locations. Low confidence if the apparent notch is clipping, missing samples, ADC artifact, or isolated impulsive noise.

## Not equivalent to

- pq_impulsive_transient
- sample dropout
- clipped waveform
