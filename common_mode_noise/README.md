# common_mode_noise

## Seed purpose

Common-mode noise is a source-victim/measurement seed for disturbances appearing similarly on multiple conductors relative to a reference.

## What this folder should contain

- Common-mode synthetic generator
- Paired channel captures
- Differential subtraction examples
- Cross-spectrum and coherence outputs

## Diagnostic markers

- Similar disturbance appears on both conductors relative to reference
- Differential subtraction reduces the disturbance
- Source-victim timing may show coupled high-frequency behavior

## Best Gamma/ElectroStat modules

- differential subtraction
- CSD
- coherence
- A/B measurement comparison

## Confidence rule

High confidence requires the disturbance to be shared across conductors and reduced by differential measurement. Low confidence if the same feature remains as true differential signal.

## Not equivalent to

- ground_loop_hum
- true differential sensor signal
- pwm_vfd_edge_coupled_noise
