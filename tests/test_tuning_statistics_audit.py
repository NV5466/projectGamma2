from __future__ import annotations

import csv
import json
from pathlib import Path

import pandas as pd

from gamma_app.threshold_profiles import ThresholdProfile, save_threshold_profile
from gamma_app.tuning_statistics import analyze_tuning_statistics, load_manifest_table, stratified_split_manifest


def test_stratified_split_is_deterministic_and_balanced():
    manifest = load_manifest_table("validation/generated/massive_1900/dataset_manifest.csv")
    split_a = stratified_split_manifest(manifest, seed=1337)
    split_b = stratified_split_manifest(manifest, seed=1337)

    assert split_a["split"].tolist() == split_b["split"].tolist()
    assert split_a["split"].value_counts().to_dict() == {"train": 1140, "dev": 380, "test": 380}

    for signature_id, group in split_a.groupby("signature_id"):
        counts = group["split"].value_counts().to_dict()
        assert counts == {"train": 60, "dev": 20, "test": 20}, signature_id

    for split in ["train", "dev", "test"]:
        split_frame = split_a[split_a["split"] == split]
        assert split_frame["noise_tier"].value_counts().to_dict() == {"normal": split_frame["noise_tier"].tolist().count("normal"), "high": split_frame["noise_tier"].tolist().count("high")}


def test_analyze_tuning_statistics_writes_full_report_set(tmp_path: Path):
    manifest_path = tmp_path / "manifest.csv"
    results_path = tmp_path / "results.csv"
    baseline_path = tmp_path / "baseline.yaml"
    tuned_path = tmp_path / "tuned.yaml"
    out_dir = tmp_path / "audit"

    manifest_rows = [
        {
            "capture_id": "case_1",
            "signature_id": "relay_coil_inductive_kick",
            "family": "switching_emc",
            "truth_label": "positive",
            "expected_fault_present": True,
            "noise_tier": "normal",
            "variant": "true_to_form",
        },
        {
            "capture_id": "case_2",
            "signature_id": "relay_coil_inductive_kick",
            "family": "switching_emc",
            "truth_label": "negative",
            "expected_fault_present": False,
            "noise_tier": "high",
            "variant": "wrong_family_waveform",
        },
        {
            "capture_id": "case_3",
            "signature_id": "high_speed_input_bounce",
            "family": "digital_timing",
            "truth_label": "positive",
            "expected_fault_present": True,
            "noise_tier": "normal",
            "variant": "true_to_form",
        },
        {
            "capture_id": "case_4",
            "signature_id": "high_speed_input_bounce",
            "family": "digital_timing",
            "truth_label": "negative",
            "expected_fault_present": False,
            "noise_tier": "high",
            "variant": "near_miss_waveform",
        },
    ]
    pd.DataFrame(manifest_rows).to_csv(manifest_path, index=False)

    result_rows = [
        {"capture_id": "case_1", "signature_id": "relay_coil_inductive_kick", "confidence": 0.95, "raw_matched": True, "reference_evidence_score": 1.0, "rank": 1},
        {"capture_id": "case_1", "signature_id": "high_speed_input_bounce", "confidence": 0.20, "raw_matched": True, "reference_evidence_score": 1.0, "rank": 2},
        {"capture_id": "case_2", "signature_id": "relay_coil_inductive_kick", "confidence": 0.30, "raw_matched": True, "reference_evidence_score": 1.0, "rank": 1},
        {"capture_id": "case_2", "signature_id": "high_speed_input_bounce", "confidence": 0.15, "raw_matched": True, "reference_evidence_score": 1.0, "rank": 2},
        {"capture_id": "case_3", "signature_id": "high_speed_input_bounce", "confidence": 0.91, "raw_matched": True, "reference_evidence_score": 1.0, "rank": 1},
        {"capture_id": "case_3", "signature_id": "relay_coil_inductive_kick", "confidence": 0.18, "raw_matched": True, "reference_evidence_score": 1.0, "rank": 2},
        {"capture_id": "case_4", "signature_id": "high_speed_input_bounce", "confidence": 0.25, "raw_matched": True, "reference_evidence_score": 1.0, "rank": 1},
        {"capture_id": "case_4", "signature_id": "relay_coil_inductive_kick", "confidence": 0.12, "raw_matched": True, "reference_evidence_score": 1.0, "rank": 2},
    ]
    pd.DataFrame(result_rows).to_csv(results_path, index=False)

    save_threshold_profile(
        ThresholdProfile(
            name="baseline",
            signature_thresholds={
                "relay_coil_inductive_kick": 0.5,
                "high_speed_input_bounce": 0.5,
            },
        ),
        baseline_path,
    )
    save_threshold_profile(
        ThresholdProfile(
            name="tuned",
            based_on="baseline",
            created_for="smoke",
            signature_thresholds={
                "relay_coil_inductive_kick": 0.4,
                "high_speed_input_bounce": 0.6,
            },
        ),
        tuned_path,
    )

    report = analyze_tuning_statistics(
        manifest_path=manifest_path,
        results_path=results_path,
        baseline_profile_path=baseline_path,
        tuned_profile_path=tuned_path,
        out_dir=out_dir,
        split_seed=1337,
        bootstrap=25,
    )

    expected = [
        "split_manifest.csv",
        "split_summary.csv",
        "split_summary.json",
        "baseline_vs_tuned_metrics.csv",
        "baseline_vs_tuned_metrics.json",
        "bootstrap_confidence_intervals.csv",
        "bootstrap_confidence_intervals.json",
        "per_analyzer_metrics.csv",
        "per_test_case_metrics.csv",
        "per_waveform_intent_metrics.csv",
        "per_noise_tier_metrics.csv",
        "threshold_ablation_metrics.csv",
        "overfit_diagnostics.csv",
        "README.md",
    ]
    for name in expected:
        assert (out_dir / name).exists(), name

    split_summary = json.loads((out_dir / "split_summary.json").read_text(encoding="utf-8"))
    assert split_summary["objective_name"] == "balanced_default"
    assert split_summary["recommended_profile"] in {"baseline", "tuned"}
    assert report["split_summary_csv"].exists()
    assert report["per_test_case_metrics_csv"].exists()

    bootstrap = pd.read_csv(out_dir / "bootstrap_confidence_intervals.csv")
    assert not bootstrap.empty
    assert {"metric", "estimate", "ci_low", "ci_high", "n_bootstrap", "split"} <= set(bootstrap.columns)

    compare = pd.read_csv(out_dir / "baseline_vs_tuned_metrics.csv")
    assert not compare.empty
    assert {"split", "metric", "baseline", "tuned", "delta"} <= set(compare.columns)

    ablation = pd.read_csv(out_dir / "threshold_ablation_metrics.csv")
    assert not ablation.empty
    assert {"signature_id", "split", "delta_accuracy", "delta_precision", "delta_recall"} <= set(ablation.columns)

    overfit = pd.read_csv(out_dir / "overfit_diagnostics.csv")
    assert not overfit.empty
    assert {"diagnostic", "severity", "details"} <= set(overfit.columns)

