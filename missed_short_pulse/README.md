# missed_short_pulse

## Seed purpose

Missed short pulse is a discrete-input seed for a real electrical pulse that exists on the wire but is not reliably registered by the normal scan, filter, or software path.

## What this folder should contain

- Short-pulse synthetic generator
- Scope pulse captures
- Optional controller image bit, latch, or timestamp channel
- Pulse-width histogram and scope-vs-controller comparison outputs

## Diagnostic markers

- Scope sees a valid narrow pulse
- Controller status misses some or all events
- Pulse width is below the effective scan/filter/capture window

## Best Gamma/ElectroStat modules

- pulse-width histogram
- scope-vs-controller compare
- event latch review
- timing report

## Confidence rule

High confidence requires electrical evidence of the pulse plus missed logical registration. Low confidence if the event is absent electrically or the width exceeds configured capture limits with margin.

## Not equivalent to

- high_speed_input_bounce
- slow_edge_late_transition
- absent sensor event
