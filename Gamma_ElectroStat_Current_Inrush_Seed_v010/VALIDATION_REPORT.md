# Validation Report: Current Inrush Seed v0.1.0

## Result

- Synthetic cases: **24**
- Capture-class matches: **24/24**
- Unit tests: **4/4 passed**
- SNR evaluated: **false**

Synthetic class counts:

```text
inrush_present:    15
no_inrush:          3
failed_transition:  3
uncertain:           3
```

The synthetic morphology families separated as intended:

- monotonic inrush -> `monotonic_or_normal_recovery`
- damped envelope oscillation -> `oscillatory_recovery`
- secondary surge -> `repeated_or_retriggered`
- persistently high post-event current -> `sustained_elevated_current`
- different recovered level -> `altered_post_event_state`

The injected exponential decay constants were recovered closely in the
synthetic cases. The 4 Hz oscillatory case was estimated near 4.5 Hz after the
one-cycle RMS envelope operation, so envelope-window bias remains a known
bench-validation target.

## Intended behavior confirmed

1. Every capture is classified independently.
2. Failed and uncertain transitions stay out of the no-inrush reference.
3. Every inrush capture receives a during-event measurement.
4. Every inrush capture receives a post-event/recovery measurement.
5. Recovery is compared against the validated no-inrush population when it exists.
6. Explicit envelopes and both population templates are preserved.
7. SNR remains disabled in v0.1.0.

## Non-claims

This validation does not establish field sensitivity, field specificity,
IEEE compliance, a unique failed component, calibrated probability, or probe
fitness beyond the supplied metadata. Real current-probe captures are still
required.
