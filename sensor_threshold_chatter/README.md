# sensor_threshold_chatter

## Seed purpose

Threshold chatter is a discrete-input seed for a signal hovering near a receiver threshold and repeatedly toggling the interpreted digital state.

## What this folder should contain

- Analog threshold/chatter synthetic generator
- Analog signal and interpreted digital state captures
- Edge timing and threshold crossing reports
- Hysteresis comparison examples

## Diagnostic markers

- Analog signal stays near the decision threshold
- Digital state toggles repeatedly without a clean physical event
- Hysteresis or added threshold margin reduces toggling

## Best Gamma/ElectroStat modules

- edge timing
- analog-vs-digital compare
- threshold crossing count
- hysteresis A/B compare

## Confidence rule

High confidence requires analog evidence near the threshold plus matching digital toggles. Low confidence if the toggles are caused by contact bounce or fast EMI bursts instead.

## Not equivalent to

- switch_relay_contact_bounce
- emi_eft_burst
- slow_edge_late_transition
