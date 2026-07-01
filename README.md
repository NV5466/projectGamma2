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

This branch organizes confirmed seed-owned files into canonical seed folders and shared ownership domains. Former `_unsorted_review/` material has been sorted into `docs/`, `shared/`, `electrostat/`, `legacy/`, `templates/`, `cross_seed/`, and `_archive/` areas where seed ownership was not the right boundary.

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

The old root swell-worker README content is preserved in `pq_voltage_swell/README.md`.
