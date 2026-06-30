# Sorted Main Notes

## Branch

```text
sort/main-seed-layout
```

## What this branch does

This branch starts from `main` and turns the repo into a clearer seed-library layout without touching `main`.

## Changes made

1. Rewrote the root `README.md` into a repo-level index.
2. Preserved the original swell-worker README content inside `pq_voltage_swell/README.md`.
3. Added `seed_registry.yaml` as the canonical first-release seed list and maturity map.

## Physical sort status

The local inventory pass has now been run on this branch. Files with clear seed ownership were moved into canonical `seed_registry.yaml` folders, and cross-seed assets were moved into support buckets.

Top-level layout is now:

```text
<seed_id>/                 canonical seed folders from seed_registry.yaml
datasets/                  shared fake-scope captures and generated reports
docs/                      program-level PDFs and reports
experiments/               exploratory work that is not yet one canonical seed
modules/                   shared analyzers, legacy packages, and reusable methods
sandbox/                   learning/scratch material
templates/                 seed and inference templates
```

Per-seed ZIPs were kept with their owning seed under `archive/`. Shared ZIPs were kept with the matching module, template, or experiment.

## Sorting principle

Every seed should eventually own this shape:

```text
<seed_id>/
  README.md
  seed_manifest.json
  generator.py
  classifier.py
  tests/
  fixtures/
  expected_outputs/
  plots/
  notes.md
```

Do not move files by vibes. Move them only after inventory confirms what they are.

The remaining deliberately unsorted work is scaffold creation for registry entries that do not yet have confirmed implementation files in this checkout.
