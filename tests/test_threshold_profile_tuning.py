from __future__ import annotations

import csv
import json
from pathlib import Path

from gamma_app.threshold_profiles import load_threshold_profile
from scripts.sweep_threshold_profiles import main as sweep_threshold_profiles_main


def test_tuned_threshold_profile_loads_canonically():
    profile = load_threshold_profile(Path("configs/threshold_profiles/gamma_1900_tuned_v1.yaml"))

    assert profile.name == "gamma_1900_tuned_v1"
    assert profile.signature_thresholds["emi_eft_burst"] == 0.05
    assert profile.baseline_metrics["tp"] == 855
    assert profile.tuned_metrics["tp"] == 905
    assert any("synthetic corpus tuning" in note.lower() for note in profile.notes)


def test_threshold_sweep_utility_runs_on_smoke_campaign(tmp_path: Path):
    campaign_dir = tmp_path / "campaign"
    out_dir = tmp_path / "out"
    campaign_dir.mkdir()

    with (campaign_dir / "campaign_results.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "capture_id",
                "signature_id",
                "raw_matched",
                "confidence",
                "reference_evidence_score",
                "rank",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "capture_id": "case_1",
                "signature_id": "sig_a",
                "raw_matched": "True",
                "confidence": "0.95",
                "reference_evidence_score": "1.0",
                "rank": "1",
            }
        )
        writer.writerow(
            {
                "capture_id": "case_1",
                "signature_id": "sig_b",
                "raw_matched": "True",
                "confidence": "0.20",
                "reference_evidence_score": "1.0",
                "rank": "2",
            }
        )
        writer.writerow(
            {
                "capture_id": "case_2",
                "signature_id": "sig_a",
                "raw_matched": "True",
                "confidence": "0.30",
                "reference_evidence_score": "1.0",
                "rank": "2",
            }
        )
        writer.writerow(
            {
                "capture_id": "case_2",
                "signature_id": "sig_b",
                "raw_matched": "True",
                "confidence": "0.92",
                "reference_evidence_score": "1.0",
                "rank": "1",
            }
        )

    with (campaign_dir / "per_case_signature_scores.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["capture_id", "truth_label", "signature_id", "confidence"],
        )
        writer.writeheader()
        writer.writerow({"capture_id": "case_1", "truth_label": "sig_a", "signature_id": "sig_a", "confidence": "0.95"})
        writer.writerow({"capture_id": "case_1", "truth_label": "sig_a", "signature_id": "sig_b", "confidence": "0.20"})
        writer.writerow({"capture_id": "case_2", "truth_label": "sig_b", "signature_id": "sig_a", "confidence": "0.30"})
        writer.writerow({"capture_id": "case_2", "truth_label": "sig_b", "signature_id": "sig_b", "confidence": "0.92"})

    (campaign_dir / "signature_summary.csv").write_text(
        "signature_id\nsig_a\nsig_b\n",
        encoding="utf-8",
    )
    (campaign_dir / "campaign_summary.json").write_text(
        json.dumps({"signatures_loaded": ["sig_a", "sig_b"], "signatures_failed_to_load": []}),
        encoding="utf-8",
    )
    (campaign_dir / "summary.json").write_text(json.dumps({"signatures_loaded": ["sig_a", "sig_b"]}), encoding="utf-8")
    (tmp_path / "manifest.csv").write_text(
        "capture_id,signature_id,truth_label\n"
        "case_1,sig_a,positive\n"
        "case_2,sig_b,positive\n",
        encoding="utf-8",
    )

    exit_code = sweep_threshold_profiles_main(
        [
            "--campaign-dir",
            str(campaign_dir),
            "--manifest",
            str(tmp_path / "manifest.csv"),
            "--out-dir",
            str(out_dir),
            "--thresholds",
            "0.25,0.50,0.75",
            "--min-precision",
            "0.50",
            "--target-recall",
            "0.50",
            "--profile-name",
            "smoke_profile",
            "--created-for",
            "smoke test",
        ]
    )
    assert exit_code == 0
    assert (out_dir / "sweep_results.csv").exists()
    assert (out_dir / "sweep_results.json").exists()
    assert (out_dir / "recommended_threshold_profile.yaml").exists()
    assert (out_dir / "sweep_results_summary.json").exists()

    summary = json.loads((out_dir / "sweep_results_summary.json").read_text(encoding="utf-8"))
    assert summary["profile_name"] == "smoke_profile"
    assert "baseline_metrics" in summary
    assert "tuned_metrics" in summary
