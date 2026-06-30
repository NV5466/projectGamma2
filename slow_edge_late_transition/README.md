# slow_edge_late_transition

## Seed purpose

Slow edge / late transition is a discrete-input seed for a slow rising or falling signal edge that causes late, uncertain, or threshold-sensitive digital interpretation.

## What this folder should contain

- Slow-edge synthetic generator
- Analog input and digital interpreted-state captures
- Rise/fall timing histograms
- Schmitt vs non-Schmitt comparison examples

## Diagnostic markers

- Rise or fall time is long relative to the receiver threshold region
- Transition timing varies across captures
- Chatter may appear if hysteresis is insufficient

## Best Gamma/ElectroStat modules

- rise/fall time
- timing histogram
- threshold crossing analysis
- analog-vs-digital compare

## Confidence rule

High confidence requires slow analog transition through the receiver threshold plus late or variable interpreted timing. Low confidence if the edge is clean and the late timing is from scan or software delay.

## Not equivalent to

- sensor_threshold_chatter
- missed_short_pulse
- controller scan delay alone
