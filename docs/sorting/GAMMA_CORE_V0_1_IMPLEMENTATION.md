# Gamma Core v0.1 Implementation

Source design: `C:\Users\dmaca\Downloads\Gamma Core v0.1 Design.pdf`.

Branch: `Gammav0.1`.

## Implemented

- `gamma_core/schema.py` with `CaptureRecord`, `ReferenceResult`, and `SignatureResult`.
- Multi-reference capture model with legacy `secondary` compatibility.
- Registry discovery for `seed_manifest.json` files with non-fatal manifest load failures.
- Deterministic ranking and campaign runner.
- NPZ capture loading with `references_json`, `reference_*` arrays, and legacy `secondary`.
- Evidence/stat writers for:
  - `per_case_signature_scores.csv`
  - `reference_comparison.csv`
  - `signature_summary.csv`
  - `campaign_summary.json`
  - `ranked_results.jsonl`
  - `confusion_matrix.csv`
  - `overlap_matrix.csv`
  - `feature_stats_by_signature.csv`
  - `reference_summary.csv`
  - `sha256_manifest.txt`
- CLI scripts:
  - `scripts/gamma_campaign.py`
  - `scripts/gamma_run.py`
- Initial adapters for:
  - `relay_coil_inductive_kick`
  - `high_speed_input_bounce`
  - `missed_short_pulse`
- Three-case smoke campaign under `validation/fixtures/three_signature_smoke`.

## Validation

- `python -m pytest -q tests relay_coil_inductive_kick\tests`
- `python -m compileall -q gamma_core relay_coil_inductive_kick high_speed_input_bounce missed_short_pulse scripts tests`
- `python scripts\gamma_campaign.py --capture-dir validation\fixtures\three_signature_smoke --registry-root . --out validation\campaigns\three_signature_smoke`

The smoke campaign loads the three v0.1 target signatures and produces the required evidence files, including `reference_comparison.csv`.
