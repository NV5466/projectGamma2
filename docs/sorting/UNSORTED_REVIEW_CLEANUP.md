# Unsorted Review Cleanup

Source instruction: `C:\Users\dmaca\Downloads\ProjectGamma2 Unsorted Review Inventory.pdf`.

Applied on `main` after merging `sort/codex-seed-library-layout`.

## Moved

- `_unsorted_review/docs_review/Gamma_ElectroStat_Eight_Module_Mathematical_Development_Report.pdf` -> `docs/reference/legacy_electrostat/`
- `_unsorted_review/docs_review/Seed Signature Library for an In-House Signal and Noise Diagnostic Tool.pdf` -> `docs/reference/seed_library/`
- `_unsorted_review/electrostat_legacy_review/electroStat/phase4test/bibliographySoFarFOrSeeds.txt` -> `docs/reference/electrostat_bibliography/`
- root sorting reports -> `docs/sorting/`
- `_unsorted_review/shared_wc2_review/WaveCompare_2_bundle(1)` -> `shared/wc2/WaveCompare_2_bundle`
- `_unsorted_review/shared_engine_review/RandomExtract_prototype_bundle` -> `shared/engine/random_extract`
- `_unsorted_review/shared_engine_review/raildiag` -> `electrostat/raildiag`
- `_unsorted_review/shared_engine_review/balls` -> `_archive/pending_balls_merge/balls`
- `_unsorted_review/electrostat_legacy_review/electroStat` -> `legacy/electrostat/phase_prototypes/electroStat`
- `_unsorted_review/shared_fixtures_review/FakeScopeData` -> `shared/fixtures/fake_scope/FakeScopeData`
- `_unsorted_review/templates_review/Gamma_ElectroStat_Phase1_Template` -> `templates/gamma_phase1`
- `_unsorted_review/sensor_signal_analyzer_multi_seed_review/*` -> `cross_seed/discrete_input_timing/sensor_signal_analyzer/`
- `_unsorted_review/informal_dih_review/*` -> `_archive/informal_dih/`
- `_unsorted_review/scratch_review/LearningPython` -> `_archive/scratch/LearningPython`

## Deleted After Verification

- `_unsorted_review/duplicates/*` was deleted only after SHA-256 matches against canonical seed copies.
- `_unsorted_review/generated_artifacts_review/*.pyc` was deleted as generated Python cache output.

## Decision Pending

- DIH remains archived because it is an informal nickname and not an official Gamma project name.
- `balls` remains archived for a later RailDiag merge review rather than being filename-merged into production code.
- Sensor analyzer material remains cross-seed until explicit rules are written for chatter, slow-edge, high-speed input bounce, missed pulse, and chain-latency ownership.
