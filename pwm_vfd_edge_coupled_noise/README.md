# pwm_vfd_edge_coupled_noise

## Seed purpose

PWM or VFD edge-coupled noise is a source-victim seed for victim-line disturbance synchronized to inverter or PWM switching edges.

## What this folder should contain

- PWM source and victim-line synthetic generator
- Source/victim capture pairs
- Cross-correlation and coherence outputs
- Edge-synchronous averaging examples

## Diagnostic markers

- Victim spikes or ringing repeat at PWM edges
- Disturbance changes or disappears when the drive/source is disabled
- Switching-frequency families and harmonics may appear

## Best Gamma/ElectroStat modules

- cross-correlation
- coherence
- STFT
- edge-synchronous averaging

## Confidence rule

High confidence requires victim disturbance to stay synchronized to PWM edges and change materially with shielding, routing, or source state. Low confidence if timing drifts relative to the PWM carrier.

## Not equivalent to

- common_mode_noise
- emi_eft_burst
- unrelated periodic noise
