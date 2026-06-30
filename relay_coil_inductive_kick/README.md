# relay_coil_inductive_kick

## Seed purpose

This seed covers relay, solenoid, or coil turn-off transients caused by stored magnetic energy.

## What this folder should contain

- Coil turn-off synthetic generator
- Coil voltage/current captures
- Optional victim-line or suppression-network comparison
- Peak and recovery-time measurements

## Diagnostic markers

- Sharp transient at coil de-energization
- Peak amplitude depends on suppression network
- Release timing may change with diode, TVS, or RC suppression
- Energy can couple into nearby victim wiring

## Best Gamma/ElectroStat modules

- peak detection
- edge trigger
- A/B comparison
- source-victim timing compare

## Confidence rule

High confidence requires the transient to align with coil turn-off and change predictably with suppression. Low confidence if no coil/source channel exists and the event is indistinguishable from generic EMI.

## Not equivalent to

- emi_eft_burst
- pq_impulsive_transient
- unrelated switching noise
