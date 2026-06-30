# switch_relay_contact_bounce

## Seed purpose

This seed covers mechanical switch or relay bounce: several rapid state changes before the contact reaches its final stable state.

## What this folder should contain

- Contact-bounce synthetic generator
- Logic or contact-voltage captures
- Optional coil or command channel
- Edge timing and pulse-width statistics

## Diagnostic markers

- Cluster of toggles during the settling window
- Unstable state before final settle
- Possible extra counts or multiple interpreted events
- Edge timing is more useful than long-record FFT

## Best Gamma/ElectroStat modules

- edge detection
- runt or glitch trigger
- pulse-width statistics
- command/contact timing compare

## Confidence rule

High confidence requires multiple transitions within a settling interval that improve with debouncing or filter changes. Low confidence if the behavior looks like threshold chatter or fast EMI instead.

## Not equivalent to

- sensor_threshold_chatter
- emi_eft_burst
- clean single edge
