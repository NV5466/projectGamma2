# Gamma / ElectroStat Seed Library

Gamma is the overall diagnostic project.

ElectroStat is the signal-processing and evidence engine.

WC2 is the waveform reference, alignment, and residual layer.

DIH is only an informal nickname. It is not the official project name for this repository.

## Methodology

```text
raw captures
  -> metadata / precheck
  -> WC2 alignment and reference recovery
  -> residual / feature extraction
  -> seed-specific evidence rules
  -> confidence scoring
  -> cautious report language
```

## Repository Shape

This repository organizes confirmed seed-owned files into canonical seed folders. Shared, legacy, reference, template, and cross-seed materials are kept in explicit ownership areas such as `shared/`, `electrostat/`, `legacy/`, `templates/`, `cross_seed/`, and `docs/`.

Each seed folder moves toward:

```text
<seed_id>/
  README.md
  seed_manifest.json
  src/
  tests/
  fixtures/
  expected_outputs/
  plots/
  notes.md
```

Read first:

- `PROGRAM_CONCEPT_REPORT.md`
- `docs/sorting/REPO_ANALYSIS_REPORT.md`
- `docs/sorting/REPO_FILE_INVENTORY.md`
- `SEED_IMPLEMENTATION_MATRIX.md`
- `seed_registry.yaml`
- `docs/sorting/UNSORTED_REVIEW.md`
- `docs/sorting/UNSORTED_REVIEW_CLEANUP.md`

The old root swell-worker README content is preserved in `pq_voltage_swell/README.md`.
