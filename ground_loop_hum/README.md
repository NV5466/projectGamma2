# ground_loop_hum

## Seed purpose

Ground-loop hum is a measurement/noise seed for low-frequency line-related interference caused by ground potential differences or reference wiring problems.

## What this folder should contain

- Ground-loop hum synthetic generator
- Suspect-node and reference-node captures
- Differential vs single-ended comparison examples
- FFT and coherence outputs

## Diagnostic markers

- Strong 50/60 Hz component and possible harmonics
- Sinusoidal hum riding on a quiet signal
- Improvement under proper differential measurement supports the label

## Best Gamma/ElectroStat modules

- FFT
- coherence
- differential A/B compare
- RMS

## Confidence rule

High confidence requires line-frequency content tied to the measurement reference path and reduced by correct differential probing. Low confidence if the frequency is unrelated to facility power or remains under isolated measurement.

## Not equivalent to

- common_mode_noise
- real process modulation
- probe/reference wiring error alone
