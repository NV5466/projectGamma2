import json
from pathlib import Path

import pandas as pd

from gamma_core.runner import CaseRunResult
from gamma_core.schema import ReferenceResult, SignatureResult
from gamma_app.results import result_rows
from gamma_app.runner import analyze_path
from gamma_app.threshold_profiles import ThresholdProfile


def test_gamma_app_runner_writes_usable_outputs(tmp_path: Path):
    out_dir = tmp_path / "analysis"
    run = analyze_path(
        "validation/fixtures/three_signature_smoke",
        out_dir,
        threshold_profile_path="configs/default_thresholds.yaml",
        max_cases=1,
    )

    assert len(run.case_results) == 1
    assert (out_dir / "campaign_results.csv").exists()
    assert (out_dir / "campaign_results.json").exists()
    assert (out_dir / "reports").exists()

    frame = pd.read_csv(out_dir / "campaign_results.csv")
    assert {"capture_id", "signature_id", "family", "confidence", "threshold", "evidence_summary"} <= set(frame.columns)
    payload = json.loads((out_dir / "campaign_results.json").read_text(encoding="utf-8"))
    assert payload["threshold_profile"]["name"] == "default"
    assert payload["captures"]
    assert "primary_diagnosis" in payload["captures"][0]
    assert list((out_dir / "reports").glob("*.md"))


def test_conflict_resolution_splits_primary_and_secondary_candidates():
    case = CaseRunResult(
        capture_id="case_conflict",
        truth_label="sig_a",
        winner="sig_a",
        decision="matched",
        ranked_signature_ids=["sig_a", "sig_b"],
        results=[
            SignatureResult(
                signature_id="sig_a",
                matched=True,
                confidence=0.90,
                best_reference="ref_a",
                reference_results=[ReferenceResult("ref_a", True, 0.90)],
            ),
            SignatureResult(
                signature_id="sig_b",
                matched=True,
                confidence=0.89,
                best_reference="ref_b",
                reference_results=[ReferenceResult("ref_b", True, 0.89)],
            ),
            SignatureResult(signature_id="sig_c", matched=True, confidence=0.99),
        ],
    )
    rows = result_rows(
        [case],
        family_by_signature={"sig_a": "digital_timing", "sig_b": "switching_emc", "sig_c": "power_quality"},
        threshold_profile=ThresholdProfile(default_threshold=0.5),
    )

    primary = [row for row in rows if row["candidate_role"] == "primary_diagnosis"]
    secondary = [row for row in rows if row["candidate_role"] == "secondary_candidate"]
    weak_reference = next(row for row in rows if row["signature_id"] == "sig_c")

    assert len(primary) == 1
    assert primary[0]["signature_id"] == "sig_a"
    assert [row["signature_id"] for row in secondary] == ["sig_b", "sig_c"]
    assert weak_reference["required_reference_status"] == "missing_or_not_reported"
    assert "required_reference_evidence_missing_or_weak" in weak_reference["warnings"]
    assert primary[0]["multi_match_ambiguity"] is True
    assert "multiple_high_confidence_signatures_match" in primary[0]["conflict_warning"]
