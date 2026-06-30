# current_inrush

## Seed purpose

Current inrush is a seed for a large startup or energization current surge that decays toward normal operation.

## What this folder should contain

- Inrush current synthetic generator
- Current captures with voltage or command context
- Cycle-RMS and peak-current expected values
- STFT or timeline output

## Diagnostic markers

- Large initial current peak
- Decay over cycles or milliseconds
- Alignment with motor start, transformer energization, relay closure, or capacitive charging

## Best Gamma/ElectroStat modules

- cycle RMS
- peak detection
- STFT
- current-vs-command timing

## Confidence rule

High confidence requires a start-linked current surge that decays toward steady state. Low confidence if the event is a short EMI spike or a sustained overload.

## Not equivalent to

- relay_coil_inductive_kick
- pq_voltage_sag
- sustained overcurrent
