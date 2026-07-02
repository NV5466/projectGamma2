import numpy as np

from gamma_core.evidence import write_evidence_outputs
from gamma_core.registry import SignatureSpec
from gamma_core.runner import run_capture
from gamma_core.schema import CaptureRecord, ReferenceResult, SignatureResult


class FakeSpec:
    seed_id = "fake_signature"
    family = "test"
    status = "implemented"
    validation_status = "test"
    entrypoint = "fake:analyze"
    manifest_path = None
    metadata = {}

    def analyze(self, _capture):
        return SignatureResult(
            signature_id=self.seed_id,
            matched=True,
            confidence=0.8,
            best_reference="ref_a",
            reference_results=[
                ReferenceResult("ref_a", True, 0.8, features={"fit_r2": 0.9}),
                ReferenceResult("ref_b", False, 0.2, features={"fit_r2": 0.1}),
            ],
            features={"fit_r2": 0.9},
            evidence=["fake evidence"],
        )


def test_evidence_files_written(tmp_path):
    capture = CaptureRecord(
        sample_rate_hz=1000.0,
        primary=np.zeros(1000),
        references={"ref_a": np.zeros(1000), "ref_b": np.zeros(1000)},
        capture_id="case_001",
        truth_label="fake_signature",
    )
    case = run_capture(capture, [FakeSpec()])  # type: ignore[list-item]
    written = write_evidence_outputs([case], tmp_path)
    expected = {
        "per_case_signature_scores.csv",
        "reference_comparison.csv",
        "signature_summary.csv",
        "campaign_summary.json",
        "ranked_results.jsonl",
        "confusion_matrix.csv",
        "overlap_matrix.csv",
        "feature_stats_by_signature.csv",
        "reference_summary.csv",
        "sha256_manifest.txt",
    }
    assert expected.issubset(set(written))
    for name in expected:
        assert (tmp_path / name).exists()
