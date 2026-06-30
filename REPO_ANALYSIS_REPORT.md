# projectGamma2 Repository Analysis Report

## Scope

This report analyzes the accessible state of `NV5466/projectGamma2`, the recent seed-folder README work, the imported seed-library context, and the related Gamma/ElectroStat work completed in this conversation.

The purpose is to make the repo state legible before the next engineering pass. It is not a field-validation claim. It is a repo and architecture status report.

## Repo identity

- Repository: `NV5466/projectGamma2`
- Visibility: private
- Default branch: `main`
- Working documentation branch: `docs/seed-folder-readmes`

The repo is folder-based rather than zip-based. That means each seed should own its README inside its own folder, not in a detached documentation index.

## Important limitation of this probe

The GitHub connector could fetch known files, compare branches, inspect commits, and write files, but it did not provide a clean recursive tree listing for this private repo. The practical probe therefore used:

1. repository metadata;
2. root README contents;
3. initial commit/diff snippets;
4. branch comparison output;
5. known seed IDs from the uploaded seed-library PDF;
6. direct checks for selected expected paths;
7. the full set of README files added on `docs/seed-folder-readmes`.

So this is a best-effort repository probe from available connector surfaces. It is good enough for the documentation and architecture status, but a local `git clone` plus `tree /F` or `find . -maxdepth` should be used for a perfect physical file inventory.

## High-level repo read

The root README currently identifies the repo as a Gamma / ElectroStat swell seed prototype. The visible README says this is a fully integrated end-to-end swell worker and gives validation performance metrics:

- validation cases: 900
- sensitivity: 0.996667
- specificity: 1.000000
- precision: 1.000000
- balanced accuracy: 0.998333
- runtime: 50.80 s

The root README also states the prototype is synthetic research only and makes no field calibration claim. That boundary is exactly the right posture for Gamma at this stage.

The initial commit probe also surfaced a separate common-mode multi-spectral validation artifact. That artifact describes a paired-channel residual pipeline:

1. remove each channel's WaveCompare 2 collective waveform;
2. retain residual captures;
3. compute complex FFTs;
4. average auto-spectra and cross-spectra over capture index;
5. compare residual peak occupancy, proportional gain, coherence, and phase;
6. classify persistent residual frequencies.

That is important because it confirms that projectGamma2 is not just a single one-off swell prototype. It already contains at least two conceptual tracks:

- a swell seed / PQ event worker;
- a residual multi-spectral source-victim classifier for common-mode and differential behavior.

## Seed-library context remembered

The uploaded PDF defines a first practical seed library for an in-house signal/noise diagnostic tool. It recommends a small but defensible seed set that clusters into five families:

1. power-quality disturbances;
2. switching and EMC signatures;
3. discrete-input timing failures;
4. rotating-machine faults;
5. measurement-artifact signatures.

It also recommends that each signature carry human description, time-domain markers, spectral markers, source buckets, best-fit analysis modules, confidence rules, capture metadata, synthetic generator recipe, and validation references.

The 22 seed IDs used for this README pass are:

- `pq_voltage_sag`
- `pq_voltage_swell`
- `pq_short_interruption`
- `pq_harmonic_distortion`
- `pq_flicker_am_mod`
- `pq_commutation_notch`
- `pq_impulsive_transient`
- `pq_oscillatory_transient`
- `emi_eft_burst`
- `current_inrush`
- `switch_relay_contact_bounce`
- `relay_coil_inductive_kick`
- `ground_loop_hum`
- `common_mode_noise`
- `pwm_vfd_edge_coupled_noise`
- `sensor_threshold_chatter`
- `slow_edge_late_transition`
- `missed_short_pulse`
- `high_speed_input_bounce`
- `bearing_fault_vibration_envelope`
- `bearing_fault_current_signature`
- `broken_rotor_bar_sidebands`

## What was done before this report

### 1. projectGamma HSIB synthetic trial

In `NV5466/projectGamma`, a synthetic HSIB chunk-recovery bundle was added and moved to `main`.

Final shape:

- 131 chunks total
- 100 waveform pairs per chunk
- 13,100 waveform pairs total
- chunks 1-100: HSIB
- chunks 101-131: non-HSIB genuine waveform controls
- hidden nuisance delay increases linearly but is not used as classifier target

The key correction was that chunks 1-7 were not negative controls. They were still HSIB; they were only controls for the intentional nanosecond delay condition. Later the trial was expanded to 100 HSIB chunks and 31 non-HSIB controls.

The HSIB definition was pinned as:

```text
Repeated CH1 digital input event
  -> repeatable CH2 middle-node response after CH1 alignment
  -> localized downstream interpretation risk
```

HSIB was explicitly separated from:

- missed short pulse;
- threshold chatter;
- nanosecond offset measurement;
- single-waveform shape matching;
- coherence alone;
- source-victim comparison alone.

### 2. projectGamma zip README branch

In `NV5466/projectGamma`, branch `docs/zip-readmes` was created. It added a docs index plus one README per seed under:

```text
docs/zip_readmes/<seed_id>/README.md
```

That was correct for a zip/bundle-oriented layout, but not correct for projectGamma2 because projectGamma2 uses actual seed folders.

### 3. projectGamma2 seed-folder README branch

In `NV5466/projectGamma2`, branch `docs/seed-folder-readmes` was created.

The folder-based correction was applied: each README was placed directly under the seed folder path:

```text
<seed_id>/README.md
```

This branch currently adds 22 README files, one for each PDF seed ID.

## Files added on `docs/seed-folder-readmes`

The branch comparison reports these 22 added files:

```text
bearing_fault_current_signature/README.md
bearing_fault_vibration_envelope/README.md
broken_rotor_bar_sidebands/README.md
common_mode_noise/README.md
current_inrush/README.md
emi_eft_burst/README.md
ground_loop_hum/README.md
high_speed_input_bounce/README.md
missed_short_pulse/README.md
pq_commutation_notch/README.md
pq_flicker_am_mod/README.md
pq_harmonic_distortion/README.md
pq_impulsive_transient/README.md
pq_oscillatory_transient/README.md
pq_short_interruption/README.md
pq_voltage_sag/README.md
pq_voltage_swell/README.md
pwm_vfd_edge_coupled_noise/README.md
relay_coil_inductive_kick/README.md
sensor_threshold_chatter/README.md
slow_edge_late_transition/README.md
switch_relay_contact_bounce/README.md
```

This is the correct layout for a folder-based repo.

## What each README now accomplishes

Each seed README follows the same practical skeleton:

1. seed purpose;
2. what the folder should contain;
3. diagnostic markers;
4. best Gamma/ElectroStat modules;
5. confidence rule;
6. not-equivalent-to boundaries.

This makes each seed folder self-describing. A person entering the folder can tell what the seed is, what artifacts belong there, what the classifier should inspect, and what common false equivalences must be rejected.

This is more valuable than a detached docs folder because the docs now travel with the code, fixtures, and outputs for the seed.

## Architectural reading of the seed set

### Power-quality family

Seeds:

- `pq_voltage_sag`
- `pq_voltage_swell`
- `pq_short_interruption`
- `pq_harmonic_distortion`
- `pq_flicker_am_mod`
- `pq_commutation_notch`
- `pq_impulsive_transient`
- `pq_oscillatory_transient`

These should become the cleanest first release family because PQ events have strong standards language and clear signal-processing boundaries.

Recommended common modules:

- sliding RMS;
- duration measurement;
- FFT;
- THD;
- STFT;
- wavelet / transient windows;
- event timeline.

Main risk:

- confusing one-sample artifacts with real PQ events;
- confusing transient events with sustained RMS events;
- letting poor sample rate or bad record length decide the label.

### EMI / switching / source-victim family

Seeds:

- `emi_eft_burst`
- `relay_coil_inductive_kick`
- `ground_loop_hum`
- `common_mode_noise`
- `pwm_vfd_edge_coupled_noise`
- `current_inrush`

These are evidence-heavy and metadata-heavy. They often require source-victim context, A/B comparison, and knowledge of switching state.

Recommended common modules:

- peak detection;
- edge density / burst density;
- STFT;
- wavelet;
- coherence;
- CSD;
- differential subtraction;
- source-victim timing comparison.

Main risk:

- treating coherence as the diagnosis instead of evidence;
- calling a victim symptom without proving source linkage;
- failing to distinguish measurement artifact from physical noise.

### Discrete-input timing family

Seeds:

- `switch_relay_contact_bounce`
- `sensor_threshold_chatter`
- `slow_edge_late_transition`
- `missed_short_pulse`
- `high_speed_input_bounce`

This is the family most connected to the JTA/Gamma work and the door/industrial-control diagnostic direction.

Recommended common modules:

- edge detection;
- pulse-width histogram;
- analog-vs-digital comparison;
- threshold crossing count;
- hysteresis A/B comparison;
- scope-vs-controller comparison;
- WC2-style ensemble alignment;
- downstream consequence model.

Main risk:

- collapsing distinct symptoms into one bucket;
- treating HSIB as missed short pulse;
- treating threshold chatter as contact bounce;
- treating timing offset as the target label.

The correct distinction is:

```text
missed_short_pulse:
  electrical pulse exists but the normal logic path misses it

high_speed_input_bounce:
  input-caused middle-node response is recovered and creates downstream interpretation risk

sensor_threshold_chatter:
  analog signal hovers near threshold and toggles interpreted state

switch_relay_contact_bounce:
  mechanical contact creates several transitions before settling

slow_edge_late_transition:
  analog edge crosses threshold slowly, causing late or variable interpretation
```

### Machinery family

Seeds:

- `bearing_fault_vibration_envelope`
- `bearing_fault_current_signature`
- `broken_rotor_bar_sidebands`

These are longer-record and operating-point-sensitive. They need speed/load context far more than most transient diagnostics.

Recommended common modules:

- envelope FFT;
- PSD;
- STFT;
- high-resolution FFT;
- order tracking where speed varies;
- trend-vs-load comparison.

Main risk:

- over-reading a single spectrum without operating context;
- confusing power harmonics with motor-current fault signatures;
- claiming vibration fault diagnosis without a healthy baseline or comparable load.

## Context memory relevant to Gamma/ElectroStat

The project framing remembered from the working conversation:

- Gamma is the real project/application name.
- DIH is an informal nickname layer, not the official system name.
- ElectroStat is the signal-processing/math diagnostic engine inside Gamma.
- WaveCompare 2 is the canonical waveform/reference layer.
- WC2 aligns repeated captures, removes nuisance scale/offset/baseline, builds collective references, and exposes spread/residual/fit information.
- WC2 is not the final diagnostic judge.
- Seeds should not be based on waveform shape alone.
- Good labels require role-aware evidence, metadata, and confidence boundaries.

Important HSIB memory:

```text
HSIB is not waveform matching.
HSIB is input-conditioned transfer/recovery plus downstream consequence risk.
```

Important measurement philosophy:

```text
Raw waveform -> precheck -> feature extraction -> seed matcher -> confidence rules -> report language.
```

The PDF's library design aligns with that philosophy.

## Accomplishments so far

### Completed

- Established Gamma/ElectroStat naming boundaries.
- Pulled the seed list from the uploaded PDF and treated it as canonical for v1 docs.
- Added HSIB synthetic chunk-recovery experiment to projectGamma main.
- Corrected HSIB/control semantics.
- Expanded HSIB synthetic trial to 131 chunks and 13,100 waveform pairs.
- Created zip-oriented README docs in projectGamma.
- Corrected approach for projectGamma2: README files belong in seed folders.
- Created `docs/seed-folder-readmes` branch in projectGamma2.
- Added 22 seed folder README files in projectGamma2.
- Created this repo analysis report.

### In progress / pending

- Open or merge a PR from `docs/seed-folder-readmes` into `main`.
- Run a local clone to enumerate the complete file tree.
- Verify that every existing seed folder has code/data outputs aligned with its README.
- Identify folders that exist but are not one of the 22 PDF seed IDs.
- Identify seeds from the PDF that have README folders but no implementation yet.
- Add per-seed manifest files once the real folder contents are inspected.

## Recommended next repo operations

### 1. Clone and inspect locally

Run:

```bash
git clone https://github.com/NV5466/projectGamma2.git
cd projectGamma2
git fetch
git checkout docs/seed-folder-readmes
```

Then inventory:

```bash
find . -maxdepth 3 -type f | sort
```

or on Windows PowerShell:

```powershell
Get-ChildItem -Recurse -File | Select-Object FullName
```

### 2. Compare expected seeds to actual folders

Create a simple inventory table:

```text
seed_id | folder_exists | README_exists | generator_exists | tests_exist | outputs_exist | notes
```

### 3. Add per-seed manifest files

Suggested file:

```text
<seed_id>/seed_manifest.json
```

Suggested fields:

```json
{
  "seed_id": "...",
  "family": "...",
  "implemented": false,
  "synthetic_generator": null,
  "validation_cases": null,
  "expected_outputs": [],
  "known_limits": [],
  "not_equivalent_to": []
}
```

### 4. Split research prototypes from production-ish workers

Use clear folders:

```text
<seed_id>/prototype/
<seed_id>/tests/
<seed_id>/fixtures/
<seed_id>/outputs/
<seed_id>/docs/
```

Do not let generated plots and research scratch files blur the main seed worker.

### 5. Add a root seed registry

Suggested file:

```text
seed_registry.yaml
```

It should list the 22 seed IDs, family, folder path, implementation status, and validation status.

## Risk register

### Risk 1: Docs overrun implementation

The README set is now ahead of confirmed implementation. This is acceptable as scaffolding, but the next pass must mark implementation status honestly.

### Risk 2: Seed equivalence errors

Several seeds overlap in symptoms. The README `Not equivalent to` sections are important. Keep them.

### Risk 3: Synthetic-only confidence

Synthetic validation is valuable, especially for industrial signatures with weak public datasets, but report language must stay conservative until bench or field captures exist.

### Risk 4: Hidden folder mismatch

Because the connector could not provide a perfect recursive tree, folder names may differ from the seed IDs. A local inventory is needed before final merge if exact folder placement matters.

### Risk 5: Root README mismatch

The root README currently reads like a swell-only repo even though the repo appears to contain broader seed work. Eventually the root README should become a repo-level index rather than a single-seed note.

## Recommendation

Merge the branch only after one local file-tree pass confirms folder placement. If the folders do not actually exist yet, these README commits will create them. That may be fine if projectGamma2 is intended to become the seed-library repo. If the folders already exist under slightly different names, move the README files into those real folders before merge.

The most important next move is not more classifier code. It is inventory discipline:

```text
seed ID -> folder -> generator -> fixtures -> tests -> outputs -> confidence boundary
```

Once that map exists, Gamma/ElectroStat stops being a pile of promising prototypes and becomes a real diagnostic library.
