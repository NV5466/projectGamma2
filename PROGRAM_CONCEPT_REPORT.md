# Program Concept Report: What Am I Reading?

## Purpose of this document

This document is the large orientation README for `projectGamma2`. It explains what the program is trying to become, what methodology has been established so far, what the current repository appears to contain, what documentation was added, and how to think about the seed folders without getting lost in the signal-noise swamp.

The short version:

```text
Gamma / ElectroStat is becoming a seed-based signal and noise diagnostic system.
It takes captured waveforms, extracts defensible evidence, compares that evidence to known seed signatures, and produces cautious diagnostic language.
```

The longer version is the rest of this file.

This is not a field-certified diagnostic standard. This is a research and engineering scaffold for building an internal tool that can grow from synthetic validation into bench validation, then into real capture review.

---

## 1. Repo identity and current state

Repository:

```text
NV5466/projectGamma2
```

Default branch:

```text
main
```

Current documentation branch:

```text
docs/seed-folder-readmes
```

The repo currently looks like a folder-based seed library, not a zip-bundle archive. That means each seed should own its documentation inside its own folder:

```text
<seed_id>/README.md
```

not only inside:

```text
docs/...
```

This branch adds that folder-level README structure.

---

## 2. The current root README says this started as a swell worker

The visible root README identifies the repo as:

```text
Gamma / ElectroStat Swell Seed v0.1.3
```

It describes the current root program as a fully integrated end-to-end swell worker. The visible validation metrics are:

```text
Validation cases: 900
Sensitivity: 0.996667
Specificity: 1.000000
Precision: 1.000000
Balanced accuracy: 0.998333
Runtime: 50.80 s
```

The root README also correctly states:

```text
Synthetic research prototype only; no field calibration claim.
```

That sentence matters. It should not be removed casually. It is the difference between honest engineering and fake certainty cosplay.

### What this means

The repo did not begin as a polished multi-seed production system. It appears to have begun as a successful focused seed worker for voltage swell detection, then expanded conceptually toward a broader diagnostic seed library.

So the repo is currently in a transitional state:

```text
single strong seed worker
  + early multi-spectral source-victim concepts
  + now a full seed-library documentation scaffold
```

That is normal. It just needs structure so the next reader does not open the repo and immediately start seeing static goblins in the rafters.

---

## 3. The actual program concept

Gamma is the broader diagnostic application.

ElectroStat is the math and signal-processing engine inside Gamma.

WaveCompare 2, or WC2, is the waveform reference and residual engine. Its job is not to diagnose everything. Its job is to stabilize the evidence:

```text
align repeated captures
remove nuisance offset, scale, and baseline effects
build a collective reference waveform
produce residuals, spread, fit, and repeatability evidence
```

ElectroStat then takes that stabilized evidence and runs analysis modules:

```text
RMS trends
FFT / PSD
STFT
wavelet or transient windows
edge detection
pulse-width statistics
threshold crossing analysis
coherence
cross-spectrum / CSD
source-victim timing
scope-vs-controller comparison
```

Then Gamma maps the evidence into a seed signature.

A seed is not just a label. A seed is a structured diagnostic hypothesis with:

```text
human explanation
time-domain markers
spectral markers
likely source buckets
best analysis modules
confidence rules
capture metadata expectations
synthetic generator recipe
validation artifacts
report language
not-equivalent-to boundaries
```

The goal is not to make the tool scream a label because a waveform looks spicy. The goal is to make the tool say:

```text
This evidence is consistent with this seed, at this confidence level, under these assumptions, and not consistent with these neighboring explanations.
```

That is the spine of the program.

---

## 4. Methodology established so far

The working methodology has settled into a pipeline:

```text
raw captures
  -> metadata and precheck
  -> WC2 reference / alignment / residual extraction
  -> feature extraction
  -> seed-specific evidence checks
  -> confidence rules
  -> report language
  -> validation output
```

### 4.1 Raw captures

Raw captures are the actual measured or synthetic waveforms.

The tool should never assume physical line identity from shape alone. A waveform can look like a command, sensor, source, victim, or fault line, but shape alone does not prove that identity.

Needed metadata includes:

```text
sample rate
record length
channel names
channel roles
voltage/current scaling
probe type
measurement reference
trigger condition
system state
known command/event timing
```

Without that metadata, Gamma can still compute features, but its report language must stay cautious.

### 4.2 Precheck

Precheck should catch obvious data-quality traps:

```text
bad sample rate
bad record length
clipping
flatline channels
missing time column
irregular time steps
wrong scale
probe/reference suspicion
single-sample artifacts
```

Precheck prevents garbage from dressing up as science.

### 4.3 WC2 reference and residuals

WC2 should be treated as the reference layer:

```text
captures in same condition -> aligned collective reference -> residuals
```

The residuals are where many hidden problems become easier to detect. If the repeatable clean behavior is removed, persistent leftovers can be classified by spectral, timing, or cross-channel structure.

This is why WC2 matters so much. It turns a pile of captures into a stable comparison object.

### 4.4 Feature extraction

Different seeds need different evidence.

Power-quality events care about RMS envelopes, duration, harmonic bins, and transient windows.

Discrete-input timing events care about edges, pulse width, threshold crossings, scan/filter behavior, and controller-vs-scope disagreement.

Source-victim noise cares about timing linkage, coherence, phase, cross-spectrum, and A/B comparisons.

Machinery signatures care about long records, speed/load context, high-resolution spectra, envelope FFT, and trend behavior.

### 4.5 Seed matcher

The seed matcher should not be a single monolithic classifier. It should be a registry of seed entries, each with its own evidence requirements.

A seed should fire only if its required evidence exists. Neighboring seeds should be explicitly rejected or marked as possible alternates.

### 4.6 Confidence rules

Confidence rules should be conservative.

Good confidence language:

```text
Evidence supports voltage swell under the supplied capture conditions.
```

Bad confidence language:

```text
The system definitely has a utility swell problem.
```

The tool can say what the data supports. It should not invent field certainty.

---

## 5. Seed-library source context

The uploaded seed-library PDF defines a practical first release of roughly 20 to 25 seed signatures. The set used here is 22 seeds.

Those seeds cluster into five families:

```text
power-quality disturbances
switching / EMC signatures
discrete-input timing failures
rotating-machine faults
measurement-artifact signatures
```

The PDF also makes a key validation point:

```text
public datasets are strong for power-quality and bearing-fault work,
but weaker for industrial discrete-input and relay-noise cases.
```

That means synthetic unit tests are not optional. For many industrial control seeds, synthetic generation and bench captures are the realistic validation path.

---

## 6. Current seed folders added on this branch

The branch adds README files directly inside the seed folders for all 22 seed IDs:

```text
pq_voltage_sag/README.md
pq_voltage_swell/README.md
pq_short_interruption/README.md
pq_harmonic_distortion/README.md
pq_flicker_am_mod/README.md
pq_commutation_notch/README.md
pq_impulsive_transient/README.md
pq_oscillatory_transient/README.md
emi_eft_burst/README.md
current_inrush/README.md
switch_relay_contact_bounce/README.md
relay_coil_inductive_kick/README.md
ground_loop_hum/README.md
common_mode_noise/README.md
pwm_vfd_edge_coupled_noise/README.md
sensor_threshold_chatter/README.md
slow_edge_late_transition/README.md
missed_short_pulse/README.md
high_speed_input_bounce/README.md
bearing_fault_vibration_envelope/README.md
bearing_fault_current_signature/README.md
broken_rotor_bar_sidebands/README.md
```

Each folder README explains:

```text
seed purpose
what the folder should contain
diagnostic markers
best Gamma/ElectroStat modules
confidence rule
not-equivalent-to boundaries
```

This is not just fluff. These READMEs are guardrails. They prevent a future developer from looking at one symptom and collapsing three different seeds into one sloppy bucket.

---

## 7. What the major seed families mean

### 7.1 Power-quality seeds

Power-quality seeds are mostly about voltage/current behavior relative to line-frequency operation.

Seeds:

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

Core modules:

```text
sliding RMS
cycle RMS
FFT
harmonic bins
THD
PSD
STFT
wavelet/transient windows
event duration logic
```

Core danger:

```text
Do not confuse a short spike, offset edge, clipped capture, or sample artifact with a sustained RMS event.
```

The current root README already shows that this lesson is being applied for swell detection. It says the candidate must have an equivalent rectangular excess duration of at least 2 selected analysis windows. That is exactly the kind of rule that stops moving-window smearing from becoming a false swell.

### 7.2 Switching / EMC / source-victim seeds

These seeds diagnose disturbances that are often caused by switching, reference problems, coupled noise, or source-victim behavior.

Seeds:

```text
emi_eft_burst
current_inrush
relay_coil_inductive_kick
ground_loop_hum
common_mode_noise
pwm_vfd_edge_coupled_noise
```

Core modules:

```text
peak detection
edge counting
burst density
STFT
wavelet
coherence
cross-spectrum / CSD
A/B comparison
differential subtraction
source-victim timing
edge-synchronous averaging
```

Core danger:

```text
Coherence is evidence, not a diagnosis.
```

If two signals are coherent, that means they are related in some measurable way. It does not automatically prove which one caused the other, what physical path exists, or whether the behavior matters downstream.

### 7.3 Discrete-input timing seeds

These are the seeds closest to the industrial control work.

Seeds:

```text
switch_relay_contact_bounce
sensor_threshold_chatter
slow_edge_late_transition
missed_short_pulse
high_speed_input_bounce
```

Core modules:

```text
edge detection
pulse-width histogram
analog-vs-digital comparison
threshold crossing analysis
hysteresis A/B comparison
scope-vs-controller comparison
WC2-style repeated-capture recovery
source-victim timing
consequence model
```

Core danger:

```text
Do not collapse all digital weirdness into bounce.
```

These seeds are different:

```text
switch_relay_contact_bounce:
  mechanical contact creates several transitions before settling

sensor_threshold_chatter:
  analog signal hovers near threshold and the interpreted digital state toggles

slow_edge_late_transition:
  analog edge crosses threshold slowly, causing late or variable interpretation

missed_short_pulse:
  real pulse exists electrically, but normal scan/filter path misses it

high_speed_input_bounce:
  input-caused middle-node response is recovered and can corrupt downstream interpretation
```

### 7.4 Machinery seeds

Machinery seeds require longer records and operating context.

Seeds:

```text
bearing_fault_vibration_envelope
bearing_fault_current_signature
broken_rotor_bar_sidebands
```

Core modules:

```text
envelope FFT
PSD
STFT
high-resolution FFT
order tracking
trend vs load
```

Core danger:

```text
Do not diagnose machine damage from one pretty spectrum without speed/load context.
```

Machinery diagnostics need repeatability and operating-point comparison. A single current or vibration plot is not enough.

---

## 8. The HSIB storyline

High-speed input bounce became its own seed because it is not equivalent to missed short pulse or threshold chatter.

The working definition is:

```text
HSIB = repeated input event
     + repeatable middle-node response recovered from repeated captures
     + localized downstream interpretation risk
```

Important exclusions:

```text
HSIB is not single-waveform shape matching.
HSIB is not just nanosecond offset measurement.
HSIB is not missed short pulse.
HSIB is not threshold chatter.
HSIB is not coherence alone.
HSIB is not source-victim comparison alone.
```

In the related `projectGamma` repo, an HSIB synthetic chunk-recovery trial was built. It expanded to:

```text
131 chunks
100 waveform pairs per chunk
13,100 total waveform pairs
chunks 1-100 are HSIB
chunks 101-131 are genuine-waveform non-HSIB controls
hidden delay increases linearly but is not the classification target
```

That trial matters because it defines the kind of blind recovery work Gamma should do:

```text
Can the system recover the class from repeated noisy captures without cheating on hidden nuisance variables?
```

That is the right question.

---

## 9. The common-mode multi-spectral clue

The initial commit probe surfaced a common-mode multi-spectral validation concept.

The described pipeline was:

```text
remove each channel's WC2 collective waveform
retain residual captures
compute complex FFTs for every residual
average auto-spectra and cross-spectra over capture index
compare residual peak occupancy, proportional gain, coherence, and phase
classify persistent residual frequencies
```

Synthetic injections included:

```text
60 Hz same-polarity disturbance in both channels -> common-mode
180 Hz opposite-polarity disturbance in both channels -> differential / opposite-polarity
310 Hz channel 1 only -> channel 1 local
```

This is a very important idea because it shows a bridge between WC2 and source-victim classification.

The key method is not just FFT. It is repeated residual FFT plus cross-channel structure.

That gives Gamma a way to distinguish:

```text
shared same-polarity residual
shared opposite-polarity residual
local residual
unclassified residual
```

This can feed `common_mode_noise`, `ground_loop_hum`, and `pwm_vfd_edge_coupled_noise`, but it must not replace seed-specific confidence rules.

---

## 10. What the current files mean

### 10.1 Root README.md

The root README currently explains the swell seed worker. It should eventually be replaced or expanded into a repo-level index.

Right now it is useful because it gives real validation metrics and a synthetic-only boundary.

Problem:

```text
It makes the repo look like only a swell seed repo.
```

Future fix:

```text
Make README.md the repo index, then move the swell-specific note into pq_voltage_swell/README.md or pq_voltage_swell/CHANGELOG.md.
```

### 10.2 Seed folder README files

These are newly added on the branch. They define what each seed folder is supposed to contain and how the seed should be interpreted.

They are not implementation files. They are orientation and guardrails.

### 10.3 REPO_ANALYSIS_REPORT.md

This is the previous large repo analysis report. It captures the repo state, what was accomplished, and next recommended steps.

This current file, `PROGRAM_CONCEPT_REPORT.md`, is the more direct reader-facing explanation:

```text
What is this program?
What am I reading?
What is the methodology?
How do the current files fit together?
What has been accomplished?
What should happen next?
```

### 10.4 .gitignore

The visible `.gitignore` excludes LibreOffice lock files and a backup folder:

```text
.~lock.*#
.raildiag_git_backup/
```

This is fine, but the repo will need a stronger Python/data-science ignore file if it starts storing generated outputs locally.

Suggested future ignore entries:

```text
__pycache__/
*.pyc
.venv/
.env
.ipynb_checkpoints/
*.npz
outputs/
plots/
.DS_Store
```

Do not blindly ignore all `.csv` files if fixtures are part of the validation repo.

---

## 11. What has actually been accomplished

### Documentation accomplishments

- Created a seed-folder README for every seed in the PDF's v1 seed list.
- Put README files in the actual seed folder paths for projectGamma2.
- Added a repo analysis report.
- Added this program concept report.
- Established a consistent explanation pattern across seeds.

### Architecture accomplishments

- Clarified Gamma vs ElectroStat vs WC2 responsibilities.
- Established WC2 as reference/residual machinery, not the final judge.
- Established seed signatures as evidence-bound diagnostic hypotheses.
- Established that confidence rules and not-equivalent-to boundaries are required.
- Established HSIB as a distinct seed, not a synonym for missed pulse, chatter, or delay measurement.

### Validation accomplishments

- The root swell seed reports 900 validation cases and strong synthetic metrics.
- Related HSIB work in projectGamma now has a large synthetic chunk-recovery trial.
- Common-mode multi-spectral validation exists conceptually from the initial import probe.

### Methodology accomplishments

The project now has a repeatable mental model:

```text
capture -> precheck -> WC2 -> features -> seed evidence -> confidence -> report
```

That is the big win.

---

## 12. What is still messy

### 12.1 The repo tree still needs a local inventory

The GitHub connector did not provide a clean recursive tree listing. A local clone should be used to inspect the actual file tree.

Run:

```bash
git clone https://github.com/NV5466/projectGamma2.git
cd projectGamma2
git fetch
git checkout docs/seed-folder-readmes
find . -maxdepth 3 -type f | sort
```

On Windows PowerShell:

```powershell
Get-ChildItem -Recurse -File | Select-Object FullName
```

### 12.2 Folders may now exist because READMEs created them

If a seed folder did not previously exist, adding `<seed_id>/README.md` creates it.

That is fine if the repo is intentionally becoming the seed-library repo. It is less fine if there are existing implementation folders with different names.

So the next physical inventory should ask:

```text
Are these the real seed folders?
Or did we create canonical folders next to differently named implementation folders?
```

### 12.3 Root README still has narrow identity

The root README says swell seed. The repo branch now documents a full seed library.

That mismatch should be fixed before a polished merge.

Recommended structure:

```text
README.md                  -> repo-level overview and map
PROGRAM_CONCEPT_REPORT.md  -> long explainer
REPO_ANALYSIS_REPORT.md    -> repo/progress audit
pq_voltage_swell/README.md -> swell seed details
```

### 12.4 Implementation status is unknown for many seeds

The READMEs say what each folder should contain. They do not prove each folder has a working generator, tests, outputs, or metrics.

Next step is implementation inventory.

---

## 13. The missing registry

The repo needs a root registry file.

Suggested file:

```text
seed_registry.yaml
```

Suggested shape:

```yaml
schema: gamma.seed_registry.v1
seeds:
  - seed_id: pq_voltage_swell
    family: power_quality
    folder: pq_voltage_swell
    status: implemented_synthetic
    primary_modules:
      - sliding_RMS
      - STFT
    validation:
      cases: 900
      synthetic_only: true
    confidence_boundary: synthetic research prototype only

  - seed_id: high_speed_input_bounce
    family: discrete_input_timing
    folder: high_speed_input_bounce
    status: scaffolded
    primary_modules:
      - WC2_alignment
      - source_victim_compare
      - threshold_consequence_model
```

This registry would let Gamma know what seeds exist, where they live, and how mature each one is.

Without the registry, the repo is human-readable but not machine-organized.

---

## 14. Recommended folder contract

Each seed folder should eventually use this contract:

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

Not every seed needs all files immediately, but every seed needs a manifest.

A minimal manifest should say:

```json
{
  "seed_id": "pq_voltage_swell",
  "family": "power_quality",
  "implementation_status": "synthetic_prototype",
  "validation_status": "synthetic_only",
  "primary_modules": ["sliding_RMS", "STFT"],
  "not_equivalent_to": ["pq_impulsive_transient", "probe_gain_error"],
  "known_limits": ["no field calibration claim"]
}
```

That one file would prevent a lot of future confusion.

---

## 15. Report language rules

Gamma should use two levels of language:

### Simple language

For technicians and fast review:

```text
The supply voltage rose above normal for a sustained interval.
```

### Technical language

For engineering reports:

```text
Sliding-RMS analysis supports a voltage swell candidate. The candidate exceeds the configured RMS threshold for the required equivalent duration and is not explained by a single-sample spike or offset-edge artifact.
```

### Forbidden energy

Avoid this style:

```text
The equipment definitely failed because of a utility swell.
```

That makes a root-cause claim beyond what the waveform alone can support.

---

## 16. How a new reader should navigate this repo

Start here:

```text
PROGRAM_CONCEPT_REPORT.md
```

Then read:

```text
README.md
REPO_ANALYSIS_REPORT.md
```

Then inspect the seed folder relevant to your problem.

For example, if you are investigating an input event that may be too short for a controller scan:

```text
missed_short_pulse/README.md
```

If you are investigating an input-caused middle-node response that may create false interpretation:

```text
high_speed_input_bounce/README.md
```

If you are investigating common-mode residual behavior after WC2 removal:

```text
common_mode_noise/README.md
```

If you are investigating voltage swell:

```text
pq_voltage_swell/README.md
```

---

## 17. Where Gamma is strong right now

Gamma is already strongest in these areas:

```text
synthetic waveform generation
RMS/event-window classification
seed-boundary thinking
source-victim reasoning
WC2/ref-residual architecture
industrial-control timing concepts
conservative report language
```

The swell worker metrics suggest the first focused seed is already behaving well in synthetic validation.

The HSIB work shows that the methodology can scale from single-event waveform logic into chunk-level repeated-capture recovery.

The common-mode multi-spectral concept shows that WC2 residuals can become a powerful source-victim analysis layer.

That is a real foundation.

---

## 18. Where Gamma is weak right now

Gamma is still weak in these areas:

```text
repo inventory discipline
root-level registry
implementation status tracking
field capture validation
bench validation for industrial-control seeds
clear separation between prototypes and production-facing workers
consistent folder contracts
CI tests
```

The big risk is not that the math is weak. The big risk is that the repo becomes a brilliant junk drawer.

A brilliant junk drawer is still a junk drawer.

The fix is boring but powerful:

```text
registry
manifests
tests
fixtures
expected outputs
versioned confidence rules
```

---

## 19. Immediate next actions

### Action 1: local tree inventory

Create a real file list from a cloned repo.

Output it to:

```text
REPO_FILE_INVENTORY.md
```

### Action 2: seed implementation matrix

Create:

```text
SEED_IMPLEMENTATION_MATRIX.md
```

Columns:

```text
seed_id
folder exists
README exists
generator exists
classifier exists
tests exist
fixtures exist
expected outputs exist
validation status
notes
```

### Action 3: root seed registry

Create:

```text
seed_registry.yaml
```

### Action 4: root README rewrite

Make the root README a map of the whole repo, not only the swell seed.

### Action 5: decide merge strategy

Either:

```text
merge docs/seed-folder-readmes into main
```

or first rename/move README files into actual implementation folders if local inventory finds different folder names.

---

## 20. Final mental model

If someone opens this repo and asks:

```text
what the hell am I reading?
```

The answer is:

```text
You are reading the early seed-library form of Gamma / ElectroStat, an in-house signal and noise diagnostic system.

It is built around a conservative evidence pipeline:
raw waveform captures -> WC2 reference/residual recovery -> signal features -> seed-specific confidence rules -> cautious report language.

The repo began around a voltage swell worker, contains evidence of source-victim residual classification work, and now has documentation scaffolding for the full 22-seed first-release library.

It is not field-certified yet. It is a synthetic and bench-validation research system being organized into a real diagnostic library.
```

That is the whole beast.

Not magic.
Not just FFT.
Not just waveform matching.
Not just AI dust sprinkled on oscilloscope traces.

It is structured evidence, tied to seed signatures, with enough humility to avoid lying.
