# Repo Analysis Report

This branch starts from `main` and creates a defensible Gamma / ElectroStat seed-library layout.

## What Was Confidently Assigned

Seed folders were populated only when filename, README context, source names, and output names agreed with a canonical seed. The main implemented synthetic groups are sag, swell, short interruption, harmonic distortion, EMI/EFT burst, current inrush, switch/relay contact bounce, common-mode noise, missed short pulse, PWM/VFD edge-coupled noise, commutation notch, oscillatory transient, and HSIB experiment evidence.

## What Was Not Forced

Shared engine material, WC2 experiments, ElectroStat legacy phase work, fake scope data, DIH-named experiments, sensor analyzer bundles spanning multiple sensor seeds, templates, scratch learning files, duplicate root copies, and legacy PDFs were preserved under `_unsorted_review/`.

## Risk Register

- Some moved test imports needed path shims because seed code now lives in `src/`.
- Sensor analyzer files likely support multiple discrete-input seeds and need a focused follow-up split.
- WC2 and ElectroStat shared layers should probably become explicit top-level support packages later, but that is separate from seed ownership.
- Source archives were preserved under seed `fixtures/source_archives/` rather than deleted.
