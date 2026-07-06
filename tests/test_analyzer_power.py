from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from gamma_app.analyzer_power import (
    analyze_analyzer_power,
    beta_credible_interval,
    beta_posterior,
    load_objective_profile,
)
from gamma_app.registry import validate_registry_families
from gamma_app.threshold_profiles import ThresholdProfile, save_threshold_profile


def test_beta_posterior_and_interval_math():
    alpha, beta, mean = beta_posterior(3, 1, prior_alpha=1, prior_beta=1)
    assert alpha == 4.0
    assert beta == 2.0
    assert mean == 4.0 / 6.0
    low, high = beta_credible_interval(alpha, beta, credible_interval=0.95)
    assert 0.0 <= low <= high <= 1.0


def test_objective_profile_loads_from_repo_config():
    profile = load_objective_profile("balanced_default")
    assert profile.name == "balanced_default"
    assert profile.mode in {"balanced_validation_distribution", "field_weighted_distribution"}
    assert "posterior_mean_success" in profile.weights


def test_analyzer_power_smoke_outputs(tmp_path: Path):
    assert validate_registry_families("seed_registry.yaml") == []

    manifest_path = tmp_path / "manifest.csv"
    results_path = tmp_path / "results.csv"
    threshold_path = tmp_path / "thresholds.yaml"
    out_dir = tmp_path / "power"
    split_manifest_path = tmp_path / "split_manifest.csv"

    manifest_rows = [
        {
            "capture_id": "case_1",
            "signature_id": "relay_coil_inductive_kick",
            "family": "switching_emc",
            "truth_label": "positive",
            "expected_fault_present": True,
            "noise_tier": "normal",
            "waveform_intent": "true_to_form",
            "test_id": "case_1",
            "target_rule_or_feature": "relay_rule",
        },
        {
            "capture_id": "case_2",
            "signature_id": "relay_coil_inductive_kick",
            "family": "switching_emc",
            "truth_label": "negative",
            "expected_fault_present": False,
            "noise_tier": "high",
            "waveform_intent": "near_miss",
            "test_id": "case_2",
            "target_rule_or_feature": "relay_rule",
        },
        {
            "capture_id": "case_3",
            "signature_id": "high_speed_input_bounce",
            "family": "digital_timing",
            "truth_label": "positive",
            "expected_fault_present": True,
            "noise_tier": "normal",
            "waveform_intent": "true_to_form",
            "test_id": "case_3",
            "target_rule_or_feature": "bounce_rule",
        },
        {
            "capture_id": "case_4",
            "signature_id": "high_speed_input_bounce",
            "family": "digital_timing",
            "truth_label": "negative",
            "expected_fault_present": False,
            "noise_tier": "high",
            "waveform_intent": "wrong_family",
            "test_id": "case_4",
            "target_rule_or_feature": "bounce_rule",
        },
    ]
    pd.DataFrame(manifest_rows).to_csv(manifest_path, index=False)
    pd.DataFrame(
        [
            {"capture_id": "case_1", "split": "train"},
            {"capture_id": "case_2", "split": "dev"},
            {"capture_id": "case_3", "split": "test"},
            {"capture_id": "case_4", "split": "test"},
        ]
    ).to_csv(split_manifest_path, index=False)

    result_rows = [
        {
            "capture_id": "case_1",
            "signature_id": "relay_coil_inductive_kick",
            "confidence": 0.95,
            "rank": 1,
            "is_selected": True,
            "raw_matched": True,
            "threshold_pass": True,
            "reference_evidence_score": 1.0,
            "required_reference_status": "best_reference_available",
            "warnings": "",
            "conflict_warning": "",
        },
        {
            "capture_id": "case_1",
            "signature_id": "high_speed_input_bounce",
            "confidence": 0.25,
            "rank": 2,
            "is_selected": False,
            "raw_matched": True,
            "threshold_pass": False,
            "reference_evidence_score": 0.8,
            "required_reference_status": "matched_reference_available",
            "warnings": "",
            "conflict_warning": "",
        },
        {
            "capture_id": "case_2",
            "signature_id": "relay_coil_inductive_kick",
            "confidence": 0.30,
            "rank": 2,
            "is_selected": False,
            "raw_matched": True,
            "threshold_pass": False,
            "reference_evidence_score": 1.0,
            "required_reference_status": "best_reference_available",
            "warnings": "",
            "conflict_warning": "",
        },
        {
            "capture_id": "case_2",
            "signature_id": "high_speed_input_bounce",
            "confidence": 0.90,
            "rank": 1,
            "is_selected": True,
            "raw_matched": True,
            "threshold_pass": True,
            "reference_evidence_score": 1.0,
            "required_reference_status": "best_reference_available",
            "warnings": "",
            "conflict_warning": "",
        },
        {
            "capture_id": "case_3",
            "signature_id": "relay_coil_inductive_kick",
            "confidence": 0.18,
            "rank": 2,
            "is_selected": False,
            "raw_matched": True,
            "threshold_pass": False,
            "reference_evidence_score": 0.7,
            "required_reference_status": "matched_reference_available",
            "warnings": "",
            "conflict_warning": "",
        },
        {
            "capture_id": "case_3",
            "signature_id": "high_speed_input_bounce",
            "confidence": 0.91,
            "rank": 1,
            "is_selected": True,
            "raw_matched": True,
            "threshold_pass": True,
            "reference_evidence_score": 1.0,
            "required_reference_status": "best_reference_available",
            "warnings": "",
            "conflict_warning": "",
        },
        {
            "capture_id": "case_4",
            "signature_id": "relay_coil_inductive_kick",
            "confidence": 0.22,
            "rank": 1,
            "is_selected": True,
            "raw_matched": True,
            "threshold_pass": True,
            "reference_evidence_score": 1.0,
            "required_reference_status": "best_reference_available",
            "warnings": "",
            "conflict_warning": "multiple_high_confidence_signatures_match: relay_coil_inductive_kick, high_speed_input_bounce",
        },
        {
            "capture_id": "case_4",
            "signature_id": "high_speed_input_bounce",
            "confidence": 0.20,
            "rank": 2,
            "is_selected": False,
            "raw_matched": True,
            "threshold_pass": False,
            "reference_evidence_score": 0.6,
            "required_reference_status": "matched_reference_available",
            "warnings": "",
            "conflict_warning": "multiple_high_confidence_signatures_match: relay_coil_inductive_kick, high_speed_input_bounce",
        },
    ]
    pd.DataFrame(result_rows).to_csv(results_path, index=False)

    save_threshold_profile(
        ThresholdProfile(
            name="smoke",
            signature_thresholds={
                "relay_coil_inductive_kick": 0.5,
                "high_speed_input_bounce": 0.5,
            },
        ),
        threshold_path,
    )

    report = analyze_analyzer_power(
        manifest_path=manifest_path,
        results_path=results_path,
        threshold_profile_path=threshold_path,
        out_dir=out_dir,
        objective="balanced_default",
        split_manifest_path=split_manifest_path,
        bootstrap=25,
    )

    expected_files = [
        "analyzer_success_distribution.csv",
        "analyzer_success_distribution.json",
        "analyzer_power_ranking.csv",
        "analyzer_power_ranking.json",
        "analyzer_bucket_metrics.csv",
        "analyzer_bucket_metrics.json",
        "analyzer_noise_stability.csv",
        "analyzer_noise_stability.json",
        "analyzer_conflict_resistance.csv",
        "analyzer_conflict_resistance.json",
        "analyzer_false_positive_concentration.csv",
        "analyzer_false_positive_concentration.json",
        "analyzer_worst_buckets.csv",
        "analyzer_worst_buckets.json",
        "analyzer_recommended_status.csv",
        "analyzer_recommended_status.json",
        "objective_weights.json",
        "power_summary.json",
        "README.md",
        "analyzer_power_bootstrap.csv",
        "analyzer_power_bootstrap.json",
    ]
    for name in expected_files:
        assert (out_dir / name).exists(), name

    success = pd.read_csv(out_dir / "analyzer_success_distribution.csv")
    assert {"analyzer_id", "condition_bucket", "posterior_mean", "credible_low", "credible_high", "power_score"} <= set(success.columns)
    assert {"overall", "split", "noise_tier", "waveform_intent", "truth_label", "reference_status", "conflict_state"} <= set(success["condition_bucket"])

    ranking = pd.read_csv(out_dir / "analyzer_power_ranking.csv")
    assert list(ranking["analyzer_id"])[:2] == ["relay_coil_inductive_kick", "high_speed_input_bounce"]
    assert {"rank", "recommended_status", "recommended_action", "mean_power", "lower_bound_power"} <= set(ranking.columns)

    summary = json.loads((out_dir / "power_summary.json").read_text(encoding="utf-8"))
    assert summary["objective_name"] == "balanced_default"
    assert summary["total_analyzers"] == 2
    assert summary["strongest_analyzer_by_mean"]["analyzer_id"] == "relay_coil_inductive_kick"

