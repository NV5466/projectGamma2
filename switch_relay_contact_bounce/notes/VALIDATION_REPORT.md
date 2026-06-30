# Validation Report: Relay Contact Bounce Seed v0.1.0

## Result

```text
Synthetic capture classifications: 108 / 108 matched
Pytest cases:                      114 / 114 passed
SNR calculation:                  disabled by design
```

Synthetic validation population:

```text
A  bounce_present:           48
B  clean_single_transition:  24
T  non_bounce_transient:     12
F  failed_transition:        12
U  uncertain:                12
```

## Test structure

The suite now has two distinct layers.

### 1. Population validation

The worker processes 108 captures together so that population templates,
clean-transition references, support labels, and class separation are tested
as an ensemble.

### 2. Separately reported pytest matrix

Pytest reports 108 randomized classification cases individually:

```text
9 signal/behavior families × 12 acquisition variations = 108 cases
```

The variations rotate through:

- 100 kS/s, 200 kS/s, and 500 kS/s sampling,
- 50 Hz and 60 Hz AC carriers,
- independent noise and phase realizations,
- AC and DC measurements,
- make and break transitions.

Six additional invariant tests bring the pytest total to 114.

## Behaviors exercised

- AC clean make transition
- DC clean make transition
- AC make-bounce
- DC make-bounce
- AC break-bounce
- analog/transient excursions without a full contact-state reversal
- failed transition
- multiple command edges that must not be mislabeled as one bounce cluster
- AC bounce overlapping a source zero crossing

The near-zero-crossing cases remain detectable as bounce, but the worker reports
that the observed edge count is observability-limited and therefore a lower
bound. Electrically hidden state changes are not invented by the math.

## Required invariants verified

1. AC polarity is not averaged into zero.
2. AC measurements are divided into measured half-cycles.
3. Each half-cycle is divided into short subwindows.
4. Every subwindow stores median absolute state derivative and derivative MAD.
5. No signed derivative average is used as the bounce statistic.
6. Full bounce requires reconstructed state reversals after the first intended transition.
7. Transient-only activity is kept separate from full bounce.
8. Failed, transient-only, and uncertain captures cannot enter the clean reference.
9. Repeated command edges are not attributed to one mechanical bounce event.
10. Zero-crossing observability limits are surfaced rather than guessed through.
11. AC and DC make-bounce both retain positive duration and excess-edge counts.
12. A clean transition is never promoted to whole-system health.
13. SNR remains explicitly disabled in v0.1.0.

## Non-claims

This validation does not establish:

- field performance on a specific train, relay, contactor, or switch,
- calibrated false-positive or false-negative rates,
- relay lifetime prediction,
- unique component-level root cause,
- compliance with a relay qualification standard.

The CSV and JSON files in this bundle contain the complete generated outcomes.
