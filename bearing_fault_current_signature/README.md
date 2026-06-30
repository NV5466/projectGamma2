# bearing_fault_current_signature

## Seed purpose

Bearing fault current signature is a rotating-machine seed for bearing condition detection from motor current features rather than direct vibration.

## What this folder should contain

- Motor current sample data or replay fixture
- Healthy vs damaged examples
- FFT, PSD, STFT, or coherence outputs
- Expected feature ranking JSON

## Diagnostic markers

- Subtle current modulation linked to mechanical condition
- Fault-related spectral components may depend on speed and load
- Current evidence is often weaker than direct vibration evidence

## Best Gamma/ElectroStat modules

- FFT
- PSD
- STFT
- coherence

## Confidence rule

High confidence requires repeatable current features that separate healthy from damaged states under comparable operating points. Low confidence if line harmonics, VFD effects, or load changes explain the spectrum better.

## Not equivalent to

- bearing_fault_vibration_envelope
- broken_rotor_bar_sidebands
- generic motor current harmonics
