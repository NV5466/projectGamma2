# broken_rotor_bar_sidebands

## Seed purpose

Broken rotor bar sidebands is a motor-current seed for induction motor rotor-cage damage indicated by slip-related sidebands around the supply fundamental.

## What this folder should contain

- Motor current synthetic generator or replay fixture
- Phase-current captures with steady-load context
- High-resolution FFT output
- Optional speed/load metadata

## Diagnostic markers

- Subtle current modulation
- Sidebands around line frequency
- Sideband spacing should match slip-related expectation
- Sideband level may trend with severity and load

## Best Gamma/ElectroStat modules

- high-resolution FFT
- order tracking if speed varies
- trend vs load
- MCSA feature extraction

## Confidence rule

High confidence requires persistent sidebands with spacing consistent with slip-derived physics and strengthened evidence under load. Low confidence if the spacing is inconsistent or disappears under repeat capture.

## Not equivalent to

- bearing_fault_current_signature
- pq_harmonic_distortion
- generic load modulation
