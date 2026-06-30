# Gamma / ElectroStat Seed Library

This repository is the folder-based seed-library workspace for Gamma / ElectroStat.

Gamma is the wider diagnostic program. ElectroStat is the signal-processing and evidence engine. The repo is organized around seed signatures: named diagnostic hypotheses such as voltage swell, common-mode noise, missed short pulse, and high-speed input bounce.

## What changed in this sorted branch

This branch moves the repo toward a readable seed-library layout instead of leaving the root README as a single swell-worker note.

The original root README described the voltage swell worker. That information has been preserved under:

```text
pq_voltage_swell/README.md
```

The root README is now the map of the whole repo.

## Methodology

The program concept is:

```text
raw waveform captures
  -> metadata / precheck
  -> WC2-style alignment and reference recovery
  -> residual and feature extraction
  -> seed-specific evidence rules
  -> confidence scoring
  -> cautious diagnostic report language
```

Seed signatures are not waveform-shape guesses. Each seed should define:

```text
purpose
expected folder contents
time-domain evidence
spectral evidence
best Gamma/ElectroStat modules
confidence rules
not-equivalent-to boundaries
validation status
```

## Current first-release seed set

Power quality:

```text
pq_voltage_sag
pq_voltage_swell
pq_short_interruption
pq_harmonic_distortion
pq_flicker_am_mod
pq_commutation_notch
pq_impulsive_transient
pq_oscillatory_transient
```

EMI / switching / source-victim:

```text
emi_eft_burst
current_inrush
relay_coil_inductive_kick
ground_loop_hum
common_mode_noise
pwm_vfd_edge_coupled_noise
```

Discrete input timing:

```text
switch_relay_contact_bounce
sensor_threshold_chatter
slow_edge_late_transition
missed_short_pulse
high_speed_input_bounce
```

Machinery:

```text
bearing_fault_vibration_envelope
bearing_fault_current_signature
broken_rotor_bar_sidebands
```

## Current maturity boundary

This repository is still a synthetic / bench-validation research workspace. Do not treat seed output as field-certified root cause. The correct report language is:

```text
Evidence is consistent with <seed> under the supplied capture conditions.
```

not:

```text
This definitely proves the field system failed because of <seed>.
```

## Read first

- `PROGRAM_CONCEPT_REPORT.md`: big-picture explanation of the program concept and methodology.
- `REPO_ANALYSIS_REPORT.md`: repo/progress audit and risk register.
- `seed_registry.yaml`: canonical first-release seed list and maturity notes.
- `<seed_id>/README.md`: per-seed folder guide.

## Physical layout

The sorted branch now uses:

```text
<seed_id>/    seed-owned implementations, validation outputs, and archives
modules/      shared analyzers, reusable methods, and legacy packages
datasets/     shared captures and generated reports
docs/         program-level references
templates/    seed templates
experiments/  exploratory work
sandbox/      scratch/learning material
```

The canonical seed names remain defined by `seed_registry.yaml`.
