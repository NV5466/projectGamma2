# Gamma Phase-1 Template Bundle

This bundle contains the first deliberately restrained implementation step after WaveCompare 2.

## Files

- `gamma_inference_template.py` — graph, measurement, healthy residual-space, seed-library, forward-backend, scoring, multi-location fusion, and next-measurement interfaces.
- `gamma_template_spec.md` — mathematical specification, development gates, and guardrails.
- `seed_library_schema.json` — schema for the later researched seed catalogue. It contains no allowed-location field.
- `example_backbone.json` — neighborhood-map example containing only roads and intersections.
- `test_gamma_template.py` — architecture smoke tests using a toy backend. The toy backend validates plumbing only, not physical diagnosis.

## What this phase does not do

- no complete system circuit model;
- no SPICE integration yet;
- no researched seed values yet;
- no real fault claims;
- no model-family/location preassignment.

## Run tests

```bash
cd gamma_phase1_template
python -m unittest -v test_gamma_template.py
```
