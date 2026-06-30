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

## Why this is not a full physical sort yet

The GitHub connector still did not expose a clean recursive tree listing. Because of that, this branch avoids blind file moves. It creates the sorted structure and metadata safely, but does not relocate unknown implementation files.

The next local step is:

```bash
git checkout sort/main-seed-layout
find . -maxdepth 3 -type f | sort
```

Then compare the physical inventory against `seed_registry.yaml`.

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
