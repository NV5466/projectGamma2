# bearing_fault_vibration_envelope

## Seed purpose

Bearing fault vibration envelope is a rotating-machine seed for bearing condition detection from vibration using envelope and spectral methods.

## What this folder should contain

- Bearing vibration sample data or public-dataset replay fixture
- Healthy vs damaged example captures
- Envelope FFT or PSD outputs
- Expected ranking or classification JSON

## Diagnostic markers

- Repetitive impact-like vibration features
- Envelope spectrum shows bearing-characteristic components
- Ranking should separate healthy and damaged conditions

## Best Gamma/ElectroStat modules

- envelope FFT
- PSD
- wavelet
- STFT

## Confidence rule

High confidence requires envelope content that separates from healthy baseline under comparable operating conditions. Low confidence if speed/load context is missing or the features vanish on repeat capture.

## Not equivalent to

- general vibration noise
- imbalance-only vibration
- bearing_fault_current_signature
