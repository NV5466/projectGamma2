# Gamma Repository Timeline Audit and Integration Repair

Date: 2026-07-02

Source: `C:\Users\dmaca\Downloads\ProjectGamma2 Repository Timeline Study and Branch Audit.docx`

## Executive Summary

The public `NV5466/projectGamma2` remote had a provenance fault around Gamma v0.1: the Gamma Core implementation and the `ball_500_v0_1` stress campaign were published on sibling branches rather than one parent-child line. That made the statement "Gamma Core v0.1 scored 76.2% on 500 cases" historically ambiguous in the public repository until an integrated branch could rerun or explicitly preserve the outputs with provenance.

This repair does not rewrite public history. It creates a clean integrated line:

```text
main @ 068deea
  -> Gammav0.1 @ ee8b1f8
      -> gamma/v0.1-integrated
          -> ball_500_v0_1 harness
          -> ball_500_v0_1 outputs produced from integrated branch
          -> timeline audit document
```

No classifier, scoring, signature adapter, or seed algorithm logic was changed during this timeline repair.

## Verified Branch Graph

The verified public branch tips were:

```text
main @ 068deea
  Add relay coil inductive kick seed v2

Gammav0.1 @ ee8b1f8
  Build Gamma Core v0.1 tournament engine

Gammatest1branch @ ed8e1cf
  Add Gamma v0.1 ball 500 stress campaign
```

The merge bases verified locally were:

```text
git merge-base origin/main origin/Gammav0.1
068deeac83ffa18e63adf511d08626c73b7fc5c2

git merge-base origin/main origin/Gammatest1branch
068deeac83ffa18e63adf511d08626c73b7fc5c2

git merge-base origin/Gammav0.1 origin/Gammatest1branch
068deeac83ffa18e63adf511d08626c73b7fc5c2
```

Therefore `Gammav0.1` and `Gammatest1branch` were siblings off `main @ 068deea`, not a parent-child sequence.

## What Each Branch Contained

`main @ 068deea` already contained `relay_coil_inductive_kick` seed v2. The timeline repair did not reimplement that seed.

`Gammav0.1 @ ee8b1f8` added Gamma Core v0.1 tournament integration, including:

- `gamma_core/`
- root `tests/`
- `scripts/gamma_campaign.py`
- `scripts/gamma_run.py`
- three wrapped signature adapters
- `validation/fixtures/three_signature_smoke/`
- `validation/campaigns/three_signature_smoke/`

`Gammatest1branch @ ed8e1cf` added:

- `scripts/ball_500_v0_1_campaign.py`
- `validation/campaigns/ball_500_v0_1/`

Publicly, `Gammatest1branch` did not contain `gamma_core/`, and `Gammav0.1` did not contain `validation/campaigns/ball_500_v0_1/`.

## Uploaded Archive Finding

The supplied `Gammav0.1.zip` archive was a mixed local workspace snapshot. It contained both Gamma Core files and `ball_500_v0_1` harness/output artifacts, plus local build artifacts such as `__pycache__/` and `.pyc` files. Its internal timestamps indicated Gamma Core files were created earlier on July 2, then the ball-500 harness and outputs were created later.

That archive was evidence that an integrated local workspace existed, but the public remote did not preserve that integrated state as a single branch tip before this repair.

## Repair Procedure

The integrated branch was created from Gamma Core v0.1, not from `main` and not from `Gammatest1branch`:

```powershell
git checkout -B gamma/v0.1-integrated origin/Gammav0.1
git cherry-pick -n ed8e1cf
git restore --staged validation\campaigns\ball_500_v0_1
git restore validation\campaigns\ball_500_v0_1
git commit -m "Add ball_500_v0_1 campaign harness on top of Gamma Core v0.1"
```

Because the generated output folder became untracked after unstaging, it was removed from the worktree and regenerated later from the integrated branch.

The campaign harness was then patched only to record audit provenance in `run_config.json` and `summary.json`. That metadata is not used by classification, scoring, ranking, or signature logic.

## Provenance Fields

The regenerated campaign output includes provenance fields:

- `campaign_id`
- `producing_branch`
- `producing_commit`
- `intended_base_branch`
- `intended_base_commit`
- `source_main_commit`
- `campaign_harness_commit`
- `random_seed`
- `python_version`
- `platform`
- `command`
- `cwd`
- `generated_at`

For the integrated rerun, the output recorded:

```text
producing_branch: gamma/v0.1-integrated
producing_commit: 8765d6a01f8d5b4dc01384acd694352e63962e83
intended_base_branch: Gammav0.1
intended_base_commit: ee8b1f8
source_main_commit: 068deea
random_seed: 546601
```

## Reproduction Commands and Results

Topology and content verification:

```powershell
git fetch --all --tags
git branch -a -vv
git log --graph --decorate --oneline --all --max-count=100
git show --summary 068deea
git show --summary ee8b1f8
git show --summary ed8e1cf
git merge-base origin/main origin/Gammav0.1
git merge-base origin/main origin/Gammatest1branch
git merge-base origin/Gammav0.1 origin/Gammatest1branch
git diff --name-status origin/main...origin/Gammav0.1
git diff --name-status origin/main...origin/Gammatest1branch
git diff --name-status origin/Gammav0.1...origin/Gammatest1branch
git diff --name-status origin/Gammatest1branch...origin/Gammav0.1
```

Validation before campaign rerun:

```powershell
python -m pytest -q tests relay_coil_inductive_kick\tests
python -m compileall -q gamma_core scripts missed_short_pulse high_speed_input_bounce relay_coil_inductive_kick tests
```

Results:

```text
19 passed in 3.11s
compileall succeeded
```

Campaign rerun:

```powershell
python scripts\ball_500_v0_1_campaign.py
```

## Integrated Campaign Metrics

The integrated branch rerun produced:

```text
total_cases: 500
random_seed: 546601
failed_cases: 0
signature runtime/schema failures: 0
overall accuracy: 0.762
correct cases: 381
wrong/no-match cases: 119
```

Per-signature accuracy:

| signature | correct | total | accuracy |
| --- | ---: | ---: | ---: |
| high_speed_input_bounce | 152 | 167 | 0.9101796407185628 |
| missed_short_pulse | 110 | 166 | 0.6626506024096386 |
| relay_coil_inductive_kick | 119 | 167 | 0.7125748502994012 |

Top confusion/no-match pairs:

| truth_label | winner | count |
| --- | --- | ---: |
| missed_short_pulse | pred_none | 41 |
| relay_coil_inductive_kick | pred_none | 39 |
| high_speed_input_bounce | pred_none | 15 |
| missed_short_pulse | relay_coil_inductive_kick | 15 |
| relay_coil_inductive_kick | missed_short_pulse | 9 |

Only the three currently wrapped signatures loaded:

- `relay_coil_inductive_kick`
- `high_speed_input_bounce`
- `missed_short_pulse`

The unwrapped scaffold manifest failures were recorded in output metadata rather than silently ignored.

## Archived vs Rerun Comparison

The archived `Gammatest1branch` / zip metrics were:

```text
overall accuracy: 0.762
correct cases: 381
wrong/no-match cases: 119
no-match decisions: 95
high_speed_input_bounce: 152/167 = 91.0%
missed_short_pulse: 110/166 = 66.3%
relay_coil_inductive_kick: 119/167 = 71.3%
```

The integrated branch rerun matched those headline metrics. Differences are expected in timestamped provenance fields and hash manifests because the integrated branch output was regenerated later from a different branch tip.

## Audit Tags

Local audit tags were created for current public tips and related branch points:

```text
audit/main-2026-07-02 -> 068deea
audit/gammav0.1-2026-07-02 -> ee8b1f8
audit/gammatest1branch-2026-07-02 -> ed8e1cf
audit/sort-unsorted-review -> d7308f0
audit/sort-codex-layout -> 181940b
audit/sort-main-layout -> 8995b54
audit/docs-seed-folder-readmes -> ff2c0fd
```

These tags were not pushed as part of this repair.

## Recommendations

Preserve old public branches as audit references until this PR is reviewed. Do not delete `Gammav0.1` or `Gammatest1branch` immediately.

Future experiment-output policy should require:

- committed campaign outputs include provenance metadata
- `run_config.json` and `summary.json` include branch, commit, platform, Python version, command, working directory, and generation timestamp
- `sha256_manifest.txt` is regenerated with each output commit
- benchmark branches declare their intended base branch and commit
- harness code and generated output artifacts are committed separately
- `__pycache__/`, `.pyc`, and other local build artifacts are never committed

## Final Statement

This repair creates a provenance-clean integrated branch without rewriting public history. It clarifies that `main` already contained relay coil inductive kick seed v2, `Gammav0.1` added Gamma Core tournament integration, and `Gammatest1branch` added a stress campaign from the wrong base. The new `gamma/v0.1-integrated` line preserves the intended historical order and reruns the campaign from the integrated branch.
