# pq_oscillatory_transient

## Seed purpose

Oscillatory transient is a seed for a short transient followed by damped ringing.

## What this folder should contain

- Damped sinusoid transient generator
- Example ringing captures
- Ring frequency and decay estimates
- STFT or wavelet outputs

## Diagnostic markers

- Burst of oscillation after an event edge
- Ring frequency is measurable
- Energy decays over time
- Event is localized rather than steady periodic content

## Best Gamma/ElectroStat modules

- STFT
- wavelet
- ring-frequency estimation
- decay or Q estimation

## Confidence rule

High confidence requires a localized ring with stable frequency and measurable decay. Low confidence if the oscillation is continuous steady-state content or probe-induced ringing.

## Not equivalent to

- pq_harmonic_distortion
- emi_eft_burst
- probe resonance artifact
