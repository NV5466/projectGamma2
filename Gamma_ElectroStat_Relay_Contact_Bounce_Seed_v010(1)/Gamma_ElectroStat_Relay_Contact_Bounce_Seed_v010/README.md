# Gamma / ElectroStat Relay Contact Bounce Seed v0.1.0

## Purpose

This worker identifies the specific temporal anatomy of mechanical relay,
contactor, and switch bounce:

```text
one validated switching command
→ first intended contact transition
→ finite cluster of unintended reversals or partial excursions
→ stable commanded final state
```

It supports AC and DC contact measurements.

## Population geometry

```text
A = full contact bounce present
B = clean single transition
T = transition completed with transient-only activity, no full reversal
F = failed or incomplete transition
U = uncertain or unusable
```

Only `A` builds the bounce model. Only `B` builds the clean-transition
reference. A `B` capture is negative only for this seed and is not a claim that
the rest of the waveform or system is healthy.

## AC analysis

AC polarity must not be naïvely averaged. The worker instead:

1. obtains the AC carrier from a measured source/reference channel or a fitted
   stable source-present contact region,
2. divides the waveform into measured half-cycles,
3. masks locally unobservable regions near carrier zero crossings,
4. normalizes the contact signal into a closed-state coordinate,
5. divides each half-cycle into short derivative windows,
6. computes both:

```text
median |d(state)/dt|
MAD(|d(state)/dt|)
```

No signed derivative average is used. Positive and negative bounce edges would
cancel and produce a very confident zero while the contact is tap-dancing.

## Bounce evidence

Full bounce requires actual reconstructed contact-state reversals after the
first intended transition. Derivative activity without a full reversal is kept
separate as `non_bounce_transient`.

Per-capture features include:

- command-to-first-contact latency,
- first intended contact time,
- final settle time,
- bounce duration,
- extra edge count,
- full state-reversal count,
- shortest, longest, and median false-state dwell,
- runt excursion count,
- transient-only derivative window count,
- zero-crossing/low-observability edge count,
- pre-contact unobservable gap and an edge-count-lower-bound flag,
- make-bounce versus break-bounce morphology.

## Recommended channels

```text
CH1: source/reference voltage for AC phase and observability
CH2: load-side voltage, voltage across the contact, or contact current
CH3: command or coil signal
```

A command channel is strongly preferred because it separates mechanical delay,
contact bounce, and repeated intentional commands.

## Main entry point

```python
result = analyze_relay_contact_bounce(
    time_s,
    contact_captures,
    contexts,
    measurement_metadata,
    source_reference_captures=source_captures,
    command_captures=command_captures,
    config=RelayBounceConfig(),
)
```

Important outputs:

- `result.capture_classification`
- `result.bounce_features`
- `result.window_features`
- `result.normalized_state_trajectories`
- `result.bounce_state_template`
- `result.clean_state_reference`
- `result.bounce_minus_clean_template`
- `result.population_summary`
- `result.evidence`

## v0.1.0 confidence policy

SNR is deferred:

```text
snr_evaluated: false
confidence_status: final_confidence_unavailable_snr_deferred
```

Support labels are categorical and provisional.

## Synthetic validation scope

The included validation covers:

- AC clean make,
- DC clean make,
- AC make-bounce,
- DC make-bounce,
- AC break-bounce,
- partial/transient-only activity,
- failed transition,
- repeated command ambiguity,
- AC bounce near a zero crossing.

Synthetic success validates implementation behavior only. It is not relay
qualification, field validation, or standards certification.

## Validation volume

The revised bundle contains two complementary layers:

```text
Synthetic population captures: 108 / 108 classified as designed
Pytest cases:                 114 / 114 passed
```

The 114 pytest cases include 108 separately reported randomized classification
cases across all nine behavior families. Those cases rotate through 100 kS/s,
200 kS/s, and 500 kS/s acquisition and both 50 Hz and 60 Hz AC carriers. Six
additional invariant tests verify reference-population exclusion, derivative
median/MAD construction, repeated-command rejection, zero-crossing
observability reporting, AC/DC bounce features, and the rule that clean does
not mean globally healthy.
