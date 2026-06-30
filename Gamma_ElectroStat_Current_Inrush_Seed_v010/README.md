# Gamma / ElectroStat Current Inrush Seed v0.1.0

## Purpose

This worker treats current inrush as a population problem across repeated,
event-aligned captures.

```text
A = inrush present
B = valid completed transition, no inrush
F = failed or incomplete transition
U = uncertain or unusable
```

Only `A` captures build the inrush model. Only validated `B` captures build the
no-inrush reference. A `B` capture is not declared globally healthy. It is only
negative for the `current_inrush` seed.

## Double measurement

Every inrush capture is measured in two connected regions:

1. **during-inrush envelope**
2. **post-inrush / recovery envelope**

The post-inrush envelope is compared against the validated no-inrush reference.
This supports morphology labels such as monotonic recovery, oscillatory
recovery, retriggering, sustained elevation, or an altered post-event state.
Those are dynamic descriptions, not unique component diagnoses.

## Envelope construction

The default envelope is sliding RMS over one line cycle:

```math
E(t)=\sqrt{\operatorname{mean}_{T}\{i^2(t)\}}
```

For inverter-fed or non-line-periodic current, provide `envelope_window_s`
explicitly. The seed refuses to invent an envelope time scale.

## Main entry point

```python
result = analyze_current_inrush(
    time_s,
    captures_a,
    contexts,
    probe_metadata,
    InrushConfig(line_frequency_hz=60.0),
)
```

Important outputs:

- `result.capture_classification`
- `result.inrush_features`
- `result.envelopes`
- `result.no_inrush_reference_envelope_a`
- `result.inrush_template_envelope_a`
- `result.population_summary`
- `result.evidence`

## Measurement separation

The current-clamp operating procedure belongs to the measurement SOP. The seed
still records probe scaling, bandwidth, current limit, AC/DC capability,
conductor identity, scope model, and scope bandwidth as acquisition metadata.

## v0.1.0 confidence policy

SNR is deferred:

```text
snr_evaluated: false
confidence_status: final_confidence_unavailable_snr_deferred
```

Support labels are categorical and provisional.

## Synthetic validation families

- monotonic inrush
- oscillatory recovery
- retriggered inrush
- sustained elevated current
- altered post-event state
- validated no-inrush transition
- failed transition
- uncertain transition

Synthetic success validates implementation behavior only. It does not replace
bench validation with a real current probe and train subsystem captures.
