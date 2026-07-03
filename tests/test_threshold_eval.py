import json

import pandas as pd

from gamma_core.thresholds import (
    THRESHOLD_COLUMNS,
    evaluate_thresholds,
    select_deployable_thresholds,
    write_threshold_outputs,
)


def _scores():
    return pd.DataFrame(
        [
            {"capture_id": "case_1", "truth_label": "sig_a", "signature_id": "sig_a", "confidence": 0.90},
            {"capture_id": "case_1", "truth_label": "sig_a", "signature_id": "sig_b", "confidence": 0.20},
            {"capture_id": "case_2", "truth_label": "sig_b", "signature_id": "sig_a", "confidence": 0.70},
            {"capture_id": "case_2", "truth_label": "sig_b", "signature_id": "sig_b", "confidence": 0.80},
            {"capture_id": "case_3", "truth_label": "sig_b", "signature_id": "sig_a", "confidence": 0.10},
            {"capture_id": "case_3", "truth_label": "sig_b", "signature_id": "sig_b", "confidence": 0.60},
        ]
    )


def test_threshold_metrics_are_one_vs_rest():
    results = evaluate_thresholds(
        _scores(),
        ["sig_a", "sig_b"],
        [0.50],
        min_required_tpr=0.90,
        max_allowed_fpr=0.05,
    )
    assert list(results.columns) == THRESHOLD_COLUMNS

    sig_a = results[results["signature_id"] == "sig_a"].iloc[0]
    assert sig_a["TP"] == 1
    assert sig_a["FP"] == 1
    assert sig_a["TN"] == 1
    assert sig_a["FN"] == 0
    assert sig_a["TPR"] == 1.0
    assert sig_a["FPR"] == 0.5
    assert sig_a["precision"] == 0.5
    assert sig_a["deployable"] == False  # noqa: E712

    sig_b = results[results["signature_id"] == "sig_b"].iloc[0]
    assert sig_b["TP"] == 2
    assert sig_b["FP"] == 0
    assert sig_b["TN"] == 1
    assert sig_b["FN"] == 0
    assert sig_b["deployable"] == True  # noqa: E712


def test_selects_highest_deployable_threshold():
    results = evaluate_thresholds(
        _scores(),
        ["sig_b"],
        [0.50, 0.70],
        min_required_tpr=0.90,
        max_allowed_fpr=0.05,
    )
    selected = select_deployable_thresholds(results)
    assert len(selected) == 1
    assert selected.iloc[0]["signature_id"] == "sig_b"
    assert selected.iloc[0]["selected_threshold"] == 0.50


def test_writes_threshold_outputs_from_campaign_dir(tmp_path):
    campaign_dir = tmp_path / "campaign"
    campaign_dir.mkdir()
    _scores().to_csv(campaign_dir / "per_case_signature_scores.csv", index=False)
    pd.DataFrame({"signature_id": ["sig_a", "sig_b"]}).to_csv(campaign_dir / "signature_summary.csv", index=False)
    (campaign_dir / "campaign_summary.json").write_text(
        json.dumps({"signatures_loaded": ["sig_a", "sig_b"], "signatures_failed_to_load": []}),
        encoding="utf-8",
    )

    threshold_results, deployable = write_threshold_outputs(
        campaign_dir,
        thresholds=[0.50],
        min_required_tpr=0.90,
        max_allowed_fpr=0.05,
    )

    assert len(threshold_results) == 2
    assert len(deployable) == 1
    assert (campaign_dir / "threshold_evaluation.csv").exists()
    assert (campaign_dir / "deployable_thresholds.csv").exists()
