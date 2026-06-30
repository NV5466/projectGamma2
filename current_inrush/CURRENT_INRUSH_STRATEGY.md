# Current Inrush Strategy v0.1.0

## Seed question

The seed does not ask whether the whole system is healthy. It asks:

> Across repeated captures of the same expected transition, which captures
> contain current inrush, what does that inrush envelope look like, and does
> the post-inrush state return to the valid no-inrush population?

## Population split

For `N` captures:

```text
N = A + B + F + U

A = inrush present
B = valid completed transition, no inrush
F = failed or incomplete transition
U = uncertain or unusable
```

Only `A` builds the inrush model. Only validated `B` captures build the
no-inrush reference. `F` and `U` never contaminate either population.

## Double measurement

Each `A` capture produces two connected measurements:

```text
pre-event -> during inrush -> post-inrush / recovery
                 |                    |
           event morphology      recovery morphology
```

### During inrush

- onset time
- peak current envelope
- peak-to-post ratio
- duration
- total and excess `I²t`
- exponential decay time constant
- ring frequency when supported
- retrigger count

### Post inrush

- recovery time
- recovery confirmed or unresolved
- post-event median envelope
- difference from the no-inrush reference
- altered settled state
- sustained elevation

## Envelope

The default implementation uses sliding RMS over one line cycle. For
inverter-fed current, the caller must provide an explicit envelope window.
The seed will not assume a 50/60 Hz cycle where none exists.

## Morphology labels

- `monotonic_or_normal_recovery`
- `oscillatory_recovery`
- `repeated_or_retriggered`
- `sustained_elevated_current`
- `altered_post_event_state`
- `inrush_without_confirmed_recovery`

These labels describe dynamics. They do not name a unique failed component.

## Confidence policy

SNR is deferred in v0.1.0. The worker reports categorical provisional support
from population repeatability, bootstrap stability, and the availability of a
validated no-inrush reference.
